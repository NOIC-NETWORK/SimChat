"""MOD 专属会话：把声明了 desktop.chat_card 的 MOD 映射到唯一一段会话。

会话数据仍由 SessionStore 落盘，本模块只做三件事：
  - 读取「启用中且声明了 desktop.chat_card」的 MOD 卡片清单
  - 按固定规则生成会话 id（mod-<id>）与归属标记（mod:<id>）
  - 首次访问时创建该 MOD 的唯一会话（进程内按 MOD 加锁，避免并发重复处理）

不引入额外存储，也不执行任何 MOD 代码。
"""

import re
import threading

from . import mods_index

# 会话 id 只允许字母数字与 -_（与 SessionStore._path 的过滤规则一致）
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


class ChatCardError(Exception):
    """MOD 卡片不存在 / 不合法；由 Web 路由映射成 4xx。"""

    def __init__(self, message, code="invalid_chat_card", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def origin_for(mod_id):
    return "mod:%s" % mod_id


def session_id_for(mod_id):
    return "mod-%s" % mod_id


def _card_of(item):
    """从 mods_index 条目中取出可用的 chat_card 声明；不可用返回 None。"""
    if not isinstance(item, dict) or not item.get("enabled"):
        return None
    if item.get("status") == "err":
        return None
    desktop = item.get("desktop")
    if not isinstance(desktop, dict):
        return None
    card = desktop.get("chat_card")
    return card if isinstance(card, dict) else None


def _matched_cards(mods_dir=None):
    out = []
    for item in mods_index.scan(mods_dir):
        card = _card_of(item)
        if not card:
            continue
        mod_id = str(item.get("id") or "")
        if not _ID_RE.match(mod_id):
            continue
        out.append((item, card))
    return out


def list_cards(store, mods_dir=None):
    """返回侧边栏卡片清单；附带该会话的只读摘要（可能尚未创建）。"""
    cards = []
    for item, card in _matched_cards(mods_dir):
        mod_id = item["id"]
        sid = session_id_for(mod_id)
        sess = store.get(sid) or {}
        cards.append({
            "mod_id": mod_id,
            "name": item.get("name") or mod_id,
            "label": card.get("label") or item.get("name") or mod_id,
            "description": card.get("description") or "",
            "origin": origin_for(mod_id),
            "session_id": sid,
            "session_exists": bool(sess),
            "title": sess.get("title") or "",
            "message_count": len(sess.get("messages") or []),
            "updated_at": sess.get("updated_at"),
            "is_deleteable": _deleteable_of(card, sess),
        })
    return cards


def _deleteable_of(card, sess=None):
    """删除能力由会话字段决定；MOD 未声明时按 true。"""
    if sess is not None and "is_deleteable" in sess:
        return sess.get("is_deleteable") is not False
    return card.get("is_deleteable") is not False


def _lock_for(mod_id):
    with _LOCKS_GUARD:
        lock = _LOCKS.get(mod_id)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[mod_id] = lock
        return lock


def ensure_session(store, mod_id, mods_dir=None):
    """取该 MOD 的唯一会话；不存在时创建（标题沿用「新对话 + 首条消息自动生成」）。"""
    mod_id = str(mod_id or "").strip()
    if not _ID_RE.match(mod_id):
        raise ChatCardError("非法的 MOD id", code="invalid_mod_id", status=400)

    matched = None
    for item, card in _matched_cards(mods_dir):
        if item["id"] == mod_id:
            matched = (item, card)
            break
    if matched is None:
        raise ChatCardError(
            "MOD 不存在、未启用或未声明 desktop.chat_card",
            code="chat_card_not_found",
            status=404,
        )

    _item, card = matched
    deleteable = card.get("is_deleteable") is not False
    system = str(card.get("system") or "").strip()
    greeting = str(card.get("greeting") or "").strip()
    sid = session_id_for(mod_id)
    with _lock_for(mod_id):
        sess = store.get(sid)
        if sess is None:
            sess = store.get_or_create(
                sid, mode="chat", origin=origin_for(mod_id),
                is_deleteable=deleteable, system=system or None,
            )
            # 初始化欢迎语：assistant 角色，不触发标题生成（只有 user 消息才自动取标题）
            if greeting:
                sess = store.append(sid, "assistant", greeting) or sess
        else:
            changed = False
            if not sess.get("origin"):
                # 固定 id 命名空间已由 MOD 占用：补齐归属标记
                sess["origin"] = origin_for(mod_id)
                changed = True
            if sess.get("is_deleteable") is not deleteable:
                sess["is_deleteable"] = deleteable
                changed = True
            if system and sess.get("system") != system:
                sess["system"] = system
                changed = True
            if changed:
                store.save(sess)
            # 历史遗留的空会话补写一次欢迎语，两端共用同一份数据
            if greeting and not sess.get("messages"):
                sess = store.append(sid, "assistant", greeting) or sess
        return sess
