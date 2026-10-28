"""SimChat 本体模型 Provider 抽象（Apache-2.0）。

本体只认两种后端：本地 Ollama、OpenAI 兼容端点。
统一接口：stream_chat(messages, ...) -> 迭代产出增量文本（str）。
所有后端异常统一抛 ProviderError，由核心层转成 error 事件。
"""

import json

import requests

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

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=1024):
        if not OLLAMA_AVAILABLE:
            raise ProviderError("ollama Python 库不可用")
        options = {
            "temperature": temperature,
            "top_p": 0.9,
            "num_ctx": 8192,
            "num_predict": max_tokens,
            "repetition_penalty": 1.15,
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
    """OpenAI 兼容端点（DashScope 等），stream SSE 逐行解析。"""

    name = "openai_compat"

    def __init__(self, cfg):
        cfg = cfg or {}
        self.api_base = (cfg.get("api_base") or "").rstrip("/")
        self.api_key = cfg.get("api_key") or ""
        self.model = cfg.get("model_name") or ""

    def _check(self):
        if not (self.api_base and self.api_key and self.model):
            raise ProviderError("OpenAI 兼容端点未配置（api_base/api_key/model_name）")

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=1024):
        self._check()
        url = self.api_base + "/chat/completions"
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
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
