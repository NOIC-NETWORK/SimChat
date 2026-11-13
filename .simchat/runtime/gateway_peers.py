"""网关节点（其他 SimChat 实例）的注册与探活。

网关连接界面用它维护一份「已知节点」清单：
  - 每个节点保存 name / url / token（token 只用于探活请求，不参与展示）
  - probe() 通过 GET {url}/api/health 判断对端是否在线，并记录延迟与进程信息
  - 数据落在 data/state/gateway_peers.json，可由用户随时删除

说明：这不是 IM 网关握手协议，只是实例发现 + 连通性检查的最小闭环。
真正的节点互联（消息转发 / 会话代理）仍需要后续协议支持。
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

from simchat.runtime import crypto

_WRITE_LOCK = threading.Lock()
_PROBE_TIMEOUT = 4


def _state_dir(data_root):
    return os.path.join(data_root, "state")


def _path(data_root):
    return os.path.join(_state_dir(data_root), "gateway_peers.json")


def _load(data_root):
    try:
        with open(_path(data_root), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        peers = data.get("peers")
        return peers if isinstance(peers, list) else []
    except Exception:
        return []


def _save(data_root, peers):
    path = _path(data_root)
    tmp = path + ".tmp"
    with _WRITE_LOCK:
        os.makedirs(_state_dir(data_root), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"peers": peers}, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def normalize_url(url):
    url = str(url or "").strip().rstrip("/")
    if not url:
        raise ValueError("节点地址不能为空")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def list_peers(data_root):
    """返回节点列表（附带上次探活结果）。"""
    peers = _load(data_root)
    result = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        result.append({
            "id": peer.get("id") or "",
            "name": peer.get("name") or "",
            "url": peer.get("url") or "",
            "note": peer.get("note") or "",
            "created_at": peer.get("created_at") or "",
            "last_probe": peer.get("last_probe"),
        })
    return result


def add_peer(data_root, payload):
    name = str(payload.get("name") or "").strip()[:60]
    url = normalize_url(payload.get("url"))
    token = str(payload.get("token") or "").strip()
    note = str(payload.get("note") or "").strip()[:200]
    if not name:
        name = url

    peers = _load(data_root)
    for peer in peers:
        if isinstance(peer, dict) and peer.get("url") == url:
            raise ValueError("该节点地址已存在：%s" % url)

    peer = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "url": url,
        "token": crypto.encrypt(token, data_root) if token else "",
        "note": note,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_probe": None,
    }
    peers.append(peer)
    _save(data_root, peers)
    return _public(peer)


def update_peer(data_root, peer_id, payload):
    peers = _load(data_root)
    for peer in peers:
        if not isinstance(peer, dict) or peer.get("id") != peer_id:
            continue
        if "name" in payload:
            name = str(payload.get("name") or "").strip()[:60]
            if name:
                peer["name"] = name
        if "url" in payload:
            peer["url"] = normalize_url(payload.get("url"))
        if "token" in payload:
            token = str(payload.get("token") or "").strip()
            peer["token"] = crypto.encrypt(token, data_root) if token else ""
        if "note" in payload:
            peer["note"] = str(payload.get("note") or "").strip()[:200]
        _save(data_root, peers)
        return _public(peer)
    raise ValueError("节点不存在: %s" % peer_id)


def remove_peer(data_root, peer_id):
    peers = _load(data_root)
    remain = [p for p in peers if not (isinstance(p, dict) and p.get("id") == peer_id)]
    if len(remain) == len(peers):
        raise ValueError("节点不存在: %s" % peer_id)
    _save(data_root, remain)
    return True


def _public(peer):
    return {
        "id": peer.get("id"),
        "name": peer.get("name"),
        "url": peer.get("url"),
        "note": peer.get("note"),
        "created_at": peer.get("created_at"),
        "last_probe": peer.get("last_probe"),
        "token_configured": bool(peer.get("token")),
    }


def probe_peer(data_root, peer_id):
    peers = _load(data_root)
    for peer in peers:
        if isinstance(peer, dict) and peer.get("id") == peer_id:
            raw_token = peer.get("token") or ""
            token = crypto.decrypt(raw_token, data_root) if crypto.is_encrypted(raw_token) else raw_token
            result = probe(peer.get("url"), token)
            peer["last_probe"] = result
            _save(data_root, peers)
            return result
    raise ValueError("节点不存在: %s" % peer_id)


def probe(url, token=None):
    """请求对端 /api/health，返回探活结果（不抛异常）。"""
    try:
        target = normalize_url(url)
    except ValueError as error:
        return {"ok": False, "error": str(error), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    health_url = target.rstrip("/") + "/api/health"
    request = urllib.request.Request(health_url, method="GET")
    request.add_header("Accept", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + str(token))

    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=_PROBE_TIMEOUT) as response:
            raw = response.read().decode("utf-8", "replace")
            latency = int((time.time() - started) * 1000)
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {}
            return {
                "ok": bool(payload.get("ok", True)),
                "latency_ms": latency,
                "app": payload.get("app") or "",
                "pid": payload.get("pid"),
                "health": "online",
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
    except urllib.error.HTTPError as error:
        return {
            "ok": False,
            "status": error.code,
            "error": "HTTP %s" % error.code,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
