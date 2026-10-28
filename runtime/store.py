"""SimChat 本体会话存储（朴素落盘实现）。

会话文件：simchat/data/sessions/<sid>.json
结构：{id, title, created_at, updated_at, messages: [{role, content, ts}]}
定位：裸壳四件套之"朴素记忆"——会话内滑动窗口 + 简单落盘。
不替代 Hippo / Rigard SessionManager，宿主接入时各行其是。
"""

import json
import os
import threading
import time
import uuid

DEFAULT_TITLE = "新对话"


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

    def create(self, title=DEFAULT_TITLE):
        sid = uuid.uuid4().hex[:12]
        now = time.time()
        sess = {"id": sid, "title": title, "created_at": now, "updated_at": now, "messages": []}
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
                return json.load(f)
        except Exception:
            return None

    def get_or_create(self, sid=None):
        if sid:
            sess = self.get(sid)
            if sess:
                return sess
        return self.create()

    def save(self, sess):
        sess["updated_at"] = time.time()
        with self._lock:
            tmp = self._path(sess["id"]) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sess, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path(sess["id"]))

    def append(self, sid, role, content):
        sess = self.get(sid)
        if not sess:
            return None
        sess["messages"].append({"role": role, "content": content, "ts": time.time()})
        if len(sess["messages"]) > self.max_history:
            sess["messages"] = sess["messages"][-self.max_history:]
        if sess.get("title") == DEFAULT_TITLE and role == "user":
            title = content.strip().split("\n")[0][:30]
            sess["title"] = title or DEFAULT_TITLE
        self.save(sess)
        return sess

    def list(self):
        out = []
        for name in os.listdir(self.root):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.root, name), "r", encoding="utf-8") as f:
                    s = json.load(f)
                out.append({
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": len(s.get("messages") or []),
                })
            except Exception:
                continue
        out.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
        return out

    def delete(self, sid):
        try:
            path = self._path(sid)
        except (ValueError, TypeError):
            return False
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
