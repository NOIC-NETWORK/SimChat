"""SimChat 本体会话存储（朴素落盘实现）。

会话文件：simchat/data/sessions/<sid>.json
结构：{id, title, mode, created_at, updated_at, messages: [{role, content, ts}], overrides, origin?}
mode 为会话来源标识：chat（对话模式）/ agent（Agent 模式），用于两类会话区分。
origin 为可选归属标记（如 "mod:kirara"），空/缺失表示普通用户会话。
定位：裸壳四件套之"朴素记忆"——会话内滑动窗口 + 简单落盘。
不替代 Hippo / Rigard SessionManager，宿主接入时各行其是。
"""

import json
import os
import threading
import time
import uuid

DEFAULT_TITLE = "新对话"
SESSION_MODES = ("chat", "agent")


def normalize_mode(mode):
    return mode if mode in SESSION_MODES else "chat"


class SessionStore:
    def __init__(self, root, max_history=40):
        self.root = root
        self.max_history = max_history
        os.makedirs(self.root, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, sid):
        safe = "".join(c for c in sid if c.isalnum() or c in "-_")
        if not safe or safe != sid:
            raise ValueError("非法 session_id")
        return os.path.join(self.root, f"{safe}.json")

    # per-session 可覆盖的运行参数；不在列表里的字段一律忽略
    _OVERRIDE_KEYS = ("thinking", "verbose", "reasoning")
    # 合法值集合；None / "inherit" 表示不覆盖，使用全局设置
    _OVERRIDE_VALUES = {
        "thinking": ("inherit", "low", "medium", "high"),
        "verbose": ("inherit", "low", "medium", "high"),
        "reasoning": ("inherit", "off", "low", "medium", "high"),
    }

    def _new_session(self, sid, title=DEFAULT_TITLE, mode="chat", origin=None,
                     is_deleteable=True, system=None):
        now = time.time()
        sess = {
            "id": sid, "title": title, "mode": normalize_mode(mode),
            "created_at": now, "updated_at": now, "messages": [],
            "overrides": {},
            # 会话是否允许删除；MOD 托管会话可声明为 False（服务端拒绝删除）
            "is_deleteable": is_deleteable is not False,
        }
        # origin 标记会话归属（如 "mod:kirara"）；普通会话不写该字段，保持旧文件结构
        if origin:
            sess["origin"] = str(origin)
        # system 为该会话使用的 system 触发词（如 JRVS 的 "Kirara"），仅 MOD 会话声明
        if system:
            sess["system"] = str(system)
        return sess

    def create(self, title=DEFAULT_TITLE, mode="chat", origin=None, is_deleteable=True,
               system=None):
        sid = uuid.uuid4().hex[:12]
        sess = self._new_session(sid, title, mode, origin=origin,
                                 is_deleteable=is_deleteable, system=system)
        self.save(sess)
        return sess

    def get(self, sid):
        try:
            path = self._path(sid)
        except (ValueError, TypeError):
            return None
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                sess = json.load(f)
        except Exception:
            return None
        sess.setdefault("mode", "chat")  # 兼容旧会话文件
        sess.setdefault("is_deleteable", True)  # 旧会话默认允许删除
        return sess

    def get_or_create(self, sid=None, mode="chat", origin=None, is_deleteable=True,
                      system=None):
        """取会话；显式 sid 不存在时按该 sid 建会话（否则后续 append 会落空）。"""
        if sid:
            sess = self.get(sid)
            if sess:
                return sess
            try:
                self._path(sid)  # 校验 sid 合法性，非法时退回随机 id
            except (ValueError, TypeError):
                return self.create(mode=mode, origin=origin,
                                   is_deleteable=is_deleteable, system=system)
            sess = self._new_session(sid, DEFAULT_TITLE, mode, origin=origin,
                                     is_deleteable=is_deleteable, system=system)
            self.save(sess)
            return sess
        return self.create(mode=mode, origin=origin, is_deleteable=is_deleteable,
                           system=system)

    def save(self, sess):
        with self._lock:
            self._write(sess)

    def _write(self, sess):
        """无锁落盘：调用方必须已持有 self._lock（save / append 共用）。"""
        sess["updated_at"] = time.time()
        path = self._path(sess["id"])
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sess, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def append(self, sid, role, content):
        # 读-改-写整体持锁，避免同一进程内两轮对话并发 append 时互相覆盖
        with self._lock:
            sess = self.get(sid)
            if not sess:
                return None
            sess["messages"].append({"role": role, "content": content, "ts": time.time()})
            if len(sess["messages"]) > self.max_history:
                sess["messages"] = sess["messages"][-self.max_history:]
            if sess.get("title") == DEFAULT_TITLE and role == "user":
                title = content.strip().split("\n")[0][:30]
                sess["title"] = title or DEFAULT_TITLE
            self._write(sess)
        return sess

    @staticmethod
    def _estimate_tokens(messages):
        """粗略 token 估算：中文字符约 1 token，英文/数字/标点约 4 字符 = 1 token。

        不追求精确——用于控制台展示的量级感知，标注"估算"。
        """
        total_chars = 0
        cjk_chars = 0
        for msg in messages or []:
            content = (msg.get("content") or "") if isinstance(msg, dict) else ""
            total_chars += len(content)
            # CJK 统一汉字 + 假名 + 谚文 + 全角标点的粗略覆盖
            for ch in content:
                cp = ord(ch)
                if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
                        or 0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF
                        or 0xFF00 <= cp <= 0xFFEF):
                    cjk_chars += 1
        ascii_chars = max(0, total_chars - cjk_chars)
        return int(cjk_chars + ascii_chars / 4)

    def list(self):
        out = []
        for name in os.listdir(self.root):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.root, name), "r", encoding="utf-8") as f:
                    s = json.load(f)
                messages = s.get("messages") or []
                overrides_raw = s.get("overrides") or {}
                # 兼容旧会话文件：没有 overrides 字段 → 不回显
                overrides = {
                    k: overrides_raw[k]
                    for k in self._OVERRIDE_KEYS
                    if overrides_raw.get(k) in self._OVERRIDE_VALUES.get(k, ())
                }
                out.append({
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "mode": normalize_mode(s.get("mode")),
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": len(messages),
                    "tokens_estimated": self._estimate_tokens(messages),
                    "overrides": overrides,
                    # 会话归属：空串 = 普通用户会话；"mod:kirara" = 由 MOD 托管的会话
                    "origin": s.get("origin") or "",
                    # 缺失按 true 处理（兼容旧会话文件）
                    "is_deleteable": s.get("is_deleteable") is not False,
                })
            except Exception:
                continue
        out.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
        return out

    def update_overrides(self, sid, overrides):
        """安全地更新 per-session overrides：只白名单字段 + 合法值。"""
        sess = self.get(sid)
        if not sess:
            return None
        current = dict(sess.get("overrides") or {})
        changed = False
        if isinstance(overrides, dict):
            for key in self._OVERRIDE_KEYS:
                if key in overrides:
                    val = overrides[key]
                    allowed = self._OVERRIDE_VALUES.get(key, ())
                    if val in allowed:
                        if current.get(key) != val:
                            current[key] = val
                            changed = True
        if changed or not sess.get("overrides"):
            sess["overrides"] = current
            self.save(sess)
        return sess.get("overrides") or {}

    def delete(self, sid):
        try:
            path = self._path(sid)
        except (ValueError, TypeError):
            return False
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
