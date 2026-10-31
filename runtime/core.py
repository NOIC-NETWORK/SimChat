"""SimChat 本体对话核心（液压系统的承压层）。

独立于任何宿主：不 import rigard/kirara，不依赖 ModLoader。
职责：配置加载 → 会话取/建 → 拼 messages → provider 流式 → 落盘 → SSE 事件。
事件契约见 simchat/spec/events.md §6。
"""

import json
import os

from . import (
    provider_config,
    settings as settings_mod,
    profile as profile_mod,
    workspace as workspace_mod,
)
from .providers import OllamaProvider, OpenAICompatProvider, ProviderError
from .store import SessionStore

DEFAULT_CONFIG = {
    "provider": "auto",
    "ollama": {"model": "televideo-ai/JRVS-7B-1.2.2:latest", "keep_alive": "30m", "options": {}},
    "openai_compat": {"api_base": "", "api_key": "", "model_name": ""},
    "system_prompt": "",
    "max_history": 40,
    "agent": {
        "max_turns": 10,
        "workdir": "",
        "approval_ttl": 600,
        "shell_enabled": False,
        "shell_timeout": 10,
    },
}


class SimChatCore:
    def __init__(self, root=None):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # simchat/
        self.data_root = root or os.path.join(base, "data")
        os.makedirs(self.data_root, exist_ok=True)
        self.config_path = os.path.join(self.data_root, "config.json")
        self.config = self._load_config()
        self.store = SessionStore(
            os.path.join(self.data_root, "sessions"),
            max_history=self.config.get("max_history", 40),
        )

    def _load_config(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg["ollama"] = dict(DEFAULT_CONFIG["ollama"])
        cfg["openai_compat"] = dict(DEFAULT_CONFIG["openai_compat"])
        cfg["agent"] = dict(DEFAULT_CONFIG["agent"])
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user = json.load(f)
                for k, v in user.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
        except Exception as e:
            print(f"[SimChat] 配置加载失败，使用默认值: {e}")
        return cfg

    def _provider(self, name):
        if name == "openai_compat":
            return OpenAICompatProvider(self.config.get("openai_compat"))
        return OllamaProvider(self.config.get("ollama"))

    def resolve_provider(self, preferred=None):
        """解析本次实际使用的服务商；返回 (provider_id, error_message)。

        `preferred` 为 None 时读配置里的首选（可能是 auto）。
        没有任何可用服务商、或显式指定的服务商不可用时返回 (None, 原因)。
        """
        status = provider_config.summarize(self.config)
        # 只统计真实服务商；auto 是虚拟项，由 status["resolved"] 决定实际调用谁
        available = [
            item
            for item in status["providers"]
            if item["available"] and item["id"] != provider_config.AUTO_ID
        ]
        if not available:
            return None, "尚未配置可用的服务商，请先完成服务商配置。"

        chosen = preferred or self.config.get("provider") or provider_config.AUTO_ID
        if chosen == provider_config.AUTO_ID or chosen not in [item["id"] for item in available]:
            # Auto Model 或首选不可用：交给 summarize 给出的「当前最优」服务商
            resolved = status.get("resolved") or available[0]["id"]
            if preferred and preferred != provider_config.AUTO_ID and preferred != resolved:
                return None, "服务商不可用: %s" % preferred
            chosen = resolved
        return chosen, None

    # ---------------- 会话 CRUD ----------------

    def list_sessions(self):
        return self.store.list()

    def create_session(self):
        return self.store.create()

    def get_session(self, sid):
        return self.store.get(sid)

    def delete_session(self, sid):
        return self.store.delete(sid)

    # ---------------- 服务商 ----------------

    def provider_status(self):
        """重新读取磁盘配置并检测可用服务商。"""
        self.config = self._load_config()
        return provider_config.summarize(self.config)

    def has_available_provider(self):
        return bool(self.provider_status().get("available"))

    def save_provider(self, provider, payload, activate=True):
        self.config = provider_config.save(
            self.data_root, provider, payload, self.config, activate=activate
        )
        return provider_config.summarize(self.config)

    def test_provider(self, provider, payload):
        result = provider_config.test(provider, payload, self.config)
        if result.get("ok"):
            # 记住「已验证」，预检抖动时不把配好的服务商误判为不可用
            self.config = provider_config.mark_verified(
                self.data_root, provider, self.config
            )
        return result

    def discover_provider(self, provider, payload):
        """手动触发模型列表发现。用于前端填完 API Base + Key 后拉模型下拉。"""
        return provider_config.discover_models(provider, payload, self.config)

    # ---------------- 用户档案 ----------------

    def has_profile(self):
        """是否已有用户档案。启动时前端据此决定是否进注册页。"""
        return profile_mod.has_profile(self.data_root)

    def load_profile(self):
        return profile_mod.load_profile(self.data_root)

    def save_profile(self, payload):
        try:
            return profile_mod.save_profile(self.data_root, payload)
        except ValueError as e:
            raise ValueError(str(e))

    # ---------------- 基础设置 ----------------

    def load_settings(self):
        return settings_mod.load(self.data_root)

    def save_settings(self, updates):
        return settings_mod.save(self.data_root, self.load_settings(), updates)

    def reset_settings(self, scope="settings"):
        return settings_mod.reset(self.data_root, scope=scope)

    # ---------------- 工作目录（workspace） ----------------

    def workspace_status(self):
        return workspace_mod.load(self.data_root)

    def save_workspace(self, path):
        return workspace_mod.save(self.data_root, path)

    def clear_workspace(self):
        return workspace_mod.clear(self.data_root)

    def browse_workspace(self, path=None):
        return workspace_mod.browse(path)

    def is_workspace_ready(self):
        """已选择工作目录且目录仍存在，才允许对话 / Agent 运行。"""
        status = self.workspace_status()
        return bool(status["configured"] and status["exists"])

    # ---------------- Agent 支持 ----------------

    def agent_options(self):
        """Agent 运行参数（config.json 的 agent 段；全部有安全边界）。"""
        self.config = self._load_config()
        raw = self.config.get("agent") or {}

        def _int(value, default, low, high):
            try:
                return max(low, min(int(value), high))
            except (TypeError, ValueError):
                return default

        workdir = str(raw.get("workdir") or "").strip()
        if workdir and not os.path.isabs(workdir):
            # 相对路径锚定到 simchat 根（runtime/core.py 上两级）
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            workdir = os.path.abspath(os.path.join(base, workdir))

        # 工作目录与 Agent 沙箱耦合：用户在前端选择的 workspace 优先作为工具根目录
        ws = workspace_mod.load(self.data_root)
        if ws["configured"] and ws["exists"]:
            workdir = ws["path"]

        return {
            "max_turns": _int(raw.get("max_turns"), 10, 1, 25),
            "workdir": workdir,
            "approval_ttl": _int(raw.get("approval_ttl"), 600, 30, 86400),
            "shell_enabled": bool(raw.get("shell_enabled")),
            "shell_timeout": _int(raw.get("shell_timeout"), 10, 1, 30),
        }

    def generate(self, prompt, system_msg=None, provider=None, model=None,
                 temperature=0.7, max_tokens=1024):
        """Agent 模式使用的一次性生成：收集流式增量后返回完整文本。"""
        self.config = self._load_config()
        chosen, error = self.resolve_provider(provider)
        if error:
            raise ProviderError(error)

        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})

        prov = self._provider(chosen)
        pieces = [
            piece
            for piece in prov.stream_chat(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        ]
        text = "".join(pieces).strip()
        if not text:
            raise ProviderError("模型返回为空")
        return text

    # ---------------- 对话 ----------------

    def chat_stream(self, message, session_id=None, provider=None, model=None,
                    system=None, temperature=0.7, max_tokens=1024,
                    regenerate=False):
        """生成 SSE 事件 dict：chat_started → token* → final | error。"""
        self.config = self._load_config()  # 热加载，改配置免重启

        chosen, error = self.resolve_provider(provider)
        if error:
            yield {
                "event": "error",
                "code": "provider_unavailable",
                "message": error,
            }
            return

        sess = self.store.get_or_create(session_id, mode="chat")
        # 会话模式隔离：对话模式不复用 Agent 会话，避免两种上下文互相污染
        if sess.get("mode") != "chat":
            sess = self.store.create(mode="chat")
        sid = sess["id"]
        if regenerate:
            self.store.trim_last_assistant(sid)
        yield {"event": "chat_started", "schema": 1, "session_id": sid}

        history = [{"role": m["role"], "content": m["content"]}
                   for m in sess.get("messages", [])]
        messages = []
        sys_text = system if system is not None else (self.config.get("system_prompt") or "")
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        prov = self._provider(chosen)
        pieces = []
        try:
            for piece in prov.stream_chat(messages, model=model,
                                          temperature=temperature, max_tokens=max_tokens):
                pieces.append(piece)
                yield {"event": "token", "content": piece}
        except ProviderError as e:
            yield {"event": "error", "message": str(e)}
            return
        except Exception as e:
            yield {"event": "error", "message": f"本体对话异常: {e}"}
            return

        full = "".join(pieces).strip()
        if not full:
            yield {"event": "error", "message": "模型返回为空"}
            return

        self.store.append(sid, "user", message)
        self.store.append(sid, "assistant", full)
        yield {"event": "final", "content": full, "session_id": sid}
