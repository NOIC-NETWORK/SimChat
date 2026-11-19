"""SimChat 本体模型 Provider 抽象（Apache-2.0）。

三层关系：
  - Transport（本模块的类）：ollama / openai_compat / anthropic，负责请求与流式解析；
  - Vendor（厂牌）：见 runtime/vendors.py，决定默认端点、鉴权方式与参数方言；
  - Account：一期由旧配置块承载，resolve_target() 归一化后交给 create_provider()。

统一接口：stream_chat(messages, ...) -> 迭代产出增量文本（str）。
所有后端异常统一抛 ProviderError，由核心层转成 error 事件。
"""

import json
import logging

import requests

logger = logging.getLogger("simchat.providers")

try:
    import ollama as _ollama
    OLLAMA_AVAILABLE = True
except Exception:
    _ollama = None
    OLLAMA_AVAILABLE = False


class ProviderError(Exception):
    pass


class OllamaProvider:
    """本地 Ollama 后端（裸壳默认）。"""

    name = "ollama"

    def __init__(self, cfg):
        cfg = cfg or {}
        self.model = cfg.get("model") or "televideo-ai/JRVS-7B-1.2.2:latest"
        self.keep_alive = cfg.get("keep_alive", "30m")
        self.extra_options = cfg.get("options") or {}

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=1024,
                    top_p=None, repetition_penalty=None):
        if not OLLAMA_AVAILABLE:
            raise ProviderError("ollama Python 库不可用")
        options = {
            "temperature": temperature,
            "top_p": 0.9 if top_p is None else top_p,
            "num_ctx": 8192,
            "num_predict": max_tokens,
            "repeat_penalty": 1.15 if repetition_penalty is None else repetition_penalty,
        }
        options.update(self.extra_options)
        try:
            stream = _ollama.chat(
                model=model or self.model,
                messages=messages,
                stream=True,
                keep_alive=self.keep_alive,
                options=options,
            )
            for chunk in stream:
                piece = (chunk.get("message") or {}).get("content") or ""
                if piece:
                    yield piece
        except Exception as e:
            raise ProviderError(f"Ollama 调用失败: {e}")


class OpenAICompatProvider:
    """OpenAI 兼容端点（百炼 / 火山 / 千帆 / Azure / 自建），stream SSE 逐行解析。

    厂牌方言通过 conf 传入：
      auth         "bearer"（默认）或 "api-key"（Azure）
      api_version  非空时作为 api-version query 追加（Azure）
      params       额外参数（按 Transport 白名单过滤，未知键丢弃并告警）
    """

    name = "openai_compat"

    # OpenAI 兼容协议允许透传的参数；协议关键字段（messages/model/stream）禁止覆盖。
    PARAM_KEYS = frozenset({
        "temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty",
        "seed", "stop", "stream_options", "response_format", "tools", "tool_choice",
        "parallel_tool_calls", "enable_thinking", "thinking", "reasoning_effort",
        "logprobs", "top_logprobs",
    })

    def __init__(self, cfg):
        cfg = cfg or {}
        self.api_base = (cfg.get("api_base") or "").rstrip("/")
        self.api_key = cfg.get("api_key") or ""
        self.model = cfg.get("model_name") or ""
        self.auth = str(cfg.get("auth") or "bearer").strip().lower()
        self.api_version = str(cfg.get("api_version") or "").strip()
        self.params = dict(cfg.get("params") or {})
        self.extra_headers = dict(cfg.get("headers") or {})
        self.dropped_params = []

    def _check(self):
        if not (self.api_base and self.api_key and self.model):
            raise ProviderError("OpenAI 兼容端点未配置（api_base/api_key/model_name）")

    def _endpoint(self):
        if self.api_base.endswith("/chat/completions"):
            return self.api_base
        return self.api_base + "/chat/completions"

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.auth == "api-key":
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = "Bearer " + self.api_key
        headers.update(self.extra_headers)
        return headers

    def _apply_params(self, payload):
        """按白名单合并厂牌参数；未知键丢弃并记录，不中断请求。"""
        for key, value in self.params.items():
            if key == "extra_body" and isinstance(value, dict):
                for inner_key, inner_value in value.items():
                    self._apply_one(payload, inner_key, inner_value)
                continue
            self._apply_one(payload, key, value)

    def _apply_one(self, payload, key, value):
        key = str(key or "").strip()
        if not key or key in ("messages", "model", "stream"):
            return
        if key in self.PARAM_KEYS:
            payload[key] = value
        elif key not in self.dropped_params:
            self.dropped_params.append(key)
            logger.warning("OpenAI 兼容传输忽略不认识的参数: %s", key)

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=1024,
                    top_p=None, repetition_penalty=None):
        self._check()
        url = self._endpoint()
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if repetition_penalty is not None:
            # OpenAI 兼容协议没有 repeat_penalty：映射到 frequency_penalty（0~2）
            payload["frequency_penalty"] = round(max(0.0, repetition_penalty - 1.0), 3)
        self._apply_params(payload)
        params = {"api-version": self.api_version} if self.api_version else None
        try:
            resp = requests.post(url, headers=self._headers(), json=payload,
                                 params=params, stream=True, timeout=120)
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                piece = ((choices[0].get("delta") or {}).get("content")) or ""
                if piece:
                    yield piece
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"OpenAI 兼容端点调用失败: {e}")


class AnthropicProvider:
    """Anthropic Messages 端点，stream SSE 逐行解析。"""

    name = "anthropic"
    DEFAULT_BASE = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    # Messages API 允许透传的参数；不认识的键丢弃并告警。
    PARAM_KEYS = frozenset({"temperature", "top_p", "max_tokens", "stop_sequences", "thinking", "metadata"})

    def __init__(self, cfg):
        cfg = cfg or {}
        self.api_base = (cfg.get("api_base") or self.DEFAULT_BASE).rstrip("/")
        self.api_key = cfg.get("api_key") or ""
        self.model = cfg.get("model_name") or ""
        self.params = dict(cfg.get("params") or {})

    def _messages_url(self):
        if self.api_base.endswith("/v1"):
            return self.api_base + "/messages"
        return self.api_base + "/v1/messages"

    def _check(self):
        if not (self.api_key and self.model):
            raise ProviderError("Anthropic 端点未配置（api_key/model_name）")

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=1024,
                    top_p=None, repetition_penalty=None):
        self._check()
        system_parts = []
        chat_messages = []
        for message in messages or []:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue
            if role not in ("user", "assistant"):
                continue
            chat_messages.append({"role": role, "content": content})

        payload = {
            "model": model or self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if top_p is not None:
            payload["top_p"] = top_p
        # Messages API 没有 repeat_penalty / frequency_penalty 对应项，忽略该参数。
        for key, value in self.params.items():
            if key in self.PARAM_KEYS:
                payload[key] = value
            elif key != "extra_body":
                logger.warning("Anthropic 传输忽略不认识的参数: %s", key)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                self._messages_url(), headers=headers, json=payload, stream=True, timeout=120
            )
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        piece = delta.get("text") or ""
                        if piece:
                            yield piece
                elif event_type == "error":
                    detail = event.get("error") or {}
                    raise ProviderError(
                        "Anthropic 调用失败: %s" % (detail.get("message") or detail)
                    )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Anthropic 端点调用失败: {e}")


_TRANSPORTS = {
    "ollama": OllamaProvider,
    "openai_compat": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
}


def create_provider(transport, conf=None):
    """按传输协议创建 Provider 实例；bedrock 为规划项，明确报错不做假实现。"""
    name = str(transport or "").strip().lower()
    if name == "bedrock":
        raise ProviderError("AWS Bedrock 传输尚未实现（规划中）")
    cls = _TRANSPORTS.get(name)
    if cls is None:
        raise ProviderError("未知传输协议: %s" % (transport or "（空）"))
    return cls(conf)
