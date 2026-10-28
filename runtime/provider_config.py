"""服务商检测与配置 —— 本体核心机制，MOD 不可修改。

职责：
  1. 检测哪些服务商当前「可用」（ollama 服务可达且模型已安装 / openai_compat 配置齐全）
  2. 校验并保存服务商配置到 simchat/data/config.json
  3. 提供连接测试
  4. ollama 已安装但服务未启动时自动拉起（ollama serve）
  5. Auto Model：按「本地优先」挑选当前最优可用服务商

对话门禁由 SimChatCore 使用 summarize()["available"] 决定：
没有任何可用服务商时，聊天流直接返回 provider_unavailable 错误事件。

MOD 只能通过 simchat.runtime.ui_blocks 覆盖配置界面方块的「材质」，
不得绕过本模块的检测、校验、保存逻辑。
"""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time

import requests

from .providers import OLLAMA_AVAILABLE

OLLAMA_DEFAULT_BASE = "http://127.0.0.1:11434"

# Auto Model：不绑定具体服务商，按优先级自动选择当前最优的一个。
AUTO_ID = "auto"
REAL_PROVIDER_IDS = ("ollama", "openai_compat")
PROVIDER_IDS = (AUTO_ID,) + REAL_PROVIDER_IDS
PROVIDER_RANK = {"ollama": 0, "openai_compat": 1}

_save_lock = threading.Lock()
_status_lock = threading.Lock()
_status_cache = {}
_STATUS_TTL = 5.0

# 自动拉起 ollama 的状态：同一进程只尝试一次，失败后进入冷却，避免反复引爆进程。
_serve_lock = threading.Lock()
_serve_state = {"process": None, "attempt_at": 0.0, "error": ""}
_SERVE_COOLDOWN = 20.0
_SERVE_WAIT = 8.0

# 连接测试通过后，预检抖动时的「记忆」窗口。
_VERIFIED_WINDOW = 30 * 60.0

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "::1")


def _short(text, limit=160):
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _ollama_base(cfg):
    base = (cfg.get("ollama") or {}).get("base_url") or os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_BASE
    base = str(base).strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base


def _is_local_base(base):
    host = base.split("://", 1)[-1].split("/", 1)[0]
    host = host.rsplit(":", 1)[0] if ":" in host else host
    return host.lower() in _LOCAL_HOSTS


def _ollama_tags(cfg, timeout=1.5):
    """返回 (模型名列表, 错误消息)。服务不可达时列表为 None。"""
    try:
        resp = requests.get(_ollama_base(cfg) + "/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as error:
        return None, _short(error)

    names = []
    for item in data.get("models") or []:
        name = item.get("name") or item.get("model")
        if name and name not in names:
            names.append(name)
    names.sort()
    return names, ""


def _ollama_executable():
    """定位 ollama 可执行文件：PATH 优先，其次各平台常见安装位置。"""
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Programs", "Ollama", "ollama.exe"))
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(os.path.join(program_files, "Ollama", "ollama.exe"))
    candidates.extend(["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama", "/usr/bin/ollama"])
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _spawn_ollama_serve(exe):
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NO_WINDOW：不弹黑窗，SimChat 退出后继续服务
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen([exe, "serve"], **kwargs)


def ensure_ollama_serving(cfg, wait=None):
    """有 ollama 就自动拉起。返回 (ok, message)。"""
    models, _ = _ollama_tags(cfg, timeout=1.0)
    if models is not None:
        return True, "Ollama 服务已在运行"

    if not _is_local_base(_ollama_base(cfg)):
        return False, "Ollama 服务不可达（%s）" % _ollama_base(cfg)

    exe = _ollama_executable()
    if not exe:
        return False, "未找到 ollama 可执行文件（请先安装 Ollama）"

    wait = _SERVE_WAIT if wait is None else wait
    with _serve_lock:
        models, _ = _ollama_tags(cfg, timeout=0.8)
        if models is not None:
            return True, "Ollama 服务已在运行"

        process = _serve_state.get("process")
        if process is None or process.poll() is not None:
            now = time.monotonic()
            if now - _serve_state.get("attempt_at", 0.0) >= _SERVE_COOLDOWN:
                try:
                    _serve_state["process"] = _spawn_ollama_serve(exe)
                    _serve_state["attempt_at"] = now
                    _serve_state["error"] = ""
                except Exception as error:
                    _serve_state["error"] = "拉起 Ollama 失败（%s）" % _short(error)
                    return False, _serve_state["error"]
            elif _serve_state.get("error"):
                return False, _serve_state["error"]

        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            models, _ = _ollama_tags(cfg, timeout=1.0)
            if models is not None:
                return True, "已自动拉起 Ollama 服务"
            time.sleep(0.35)
    return False, "Ollama 启动超时（可手动运行 ollama serve）"


def _model_installed(configured, installed):
    """ollama 的标签省略时等价于 :latest。"""
    if not configured:
        return False
    if configured in installed:
        return True
    return (configured + ":latest") in installed


def mask_key(key):
    key = str(key or "")
    if not key:
        return ""
    if len(key) <= 8:
        return "已保存"
    return key[:4] + "…" + key[-4:]


def _ollama_fields(conf, models):
    model = str(conf.get("model") or "").strip()
    keep_alive = str(conf.get("keep_alive") or "").strip()
    return [
        {
            "name": "model",
            "label": "模型",
            "type": "text",
            "required": True,
            "value": model or (models[0] if models else ""),
            "placeholder": "例如 qwen3:8b",
            "options": list(models),
            "hint": "Ollama 中已安装的模型会出现在下拉建议里",
        },
        {
            "name": "keep_alive",
            "label": "会话保活",
            "type": "text",
            "required": False,
            "value": keep_alive or "30m",
            "placeholder": "30m",
            "hint": "模型在内存中保留的时长",
        },
    ]


def detect_ollama(cfg):
    conf = dict(cfg.get("ollama") or {})
    model = str(conf.get("model") or "").strip()
    status = {
        "id": "ollama",
        "label": "Ollama（本地）",
        "configured": bool(model),
        "available": False,
        "detail": "",
        "models": [],
        "fields": _ollama_fields(conf, []),
        "values": {"model": model, "keep_alive": conf.get("keep_alive") or ""},
    }

    if not OLLAMA_AVAILABLE:
        status["detail"] = "未安装 ollama Python 库（pip install ollama）"
        return status

    models, error = _ollama_tags(cfg)
    auto_message = ""
    if models is None:
        # 服务没起来但本机装了 ollama：自动拉起，避免「配置过却失效」
        started, auto_message = ensure_ollama_serving(cfg)
        if started:
            models, error = _ollama_tags(cfg)
    if models is None:
        status["detail"] = "无法连接 Ollama 服务（%s）" % (auto_message or error)
        return status

    status["models"] = models
    status["fields"] = _ollama_fields(conf, models)

    if not models:
        status["detail"] = "Ollama 服务已连接，但还没有安装任何模型"
        return status
    if not model:
        status["detail"] = "Ollama 服务已连接，请选择要使用的模型"
        return status
    if _model_installed(model, models):
        status["available"] = True
        status["detail"] = "Ollama 已连接，模型 %s 可用" % model
        if auto_message:
            status["detail"] += "（%s）" % auto_message
    else:
        status["detail"] = "Ollama 已连接，但未安装模型 %s" % model
    return status


def _openai_probe(api_base, api_key, timeout=2.0):
    """轻量连通性预检：GET /models。

    返回 (ok, kind, message)，kind ∈ ok / auth / unsupported / unreachable / http。
    """
    try:
        resp = requests.get(
            api_base.rstrip("/") + "/models",
            headers={"Authorization": "Bearer " + api_key},
            timeout=timeout,
        )
    except Exception as error:
        return False, "unreachable", "无法连接 API 端点（%s）" % _short(error)
    if resp.status_code < 300:
        return True, "ok", "API 端点可访问"
    if resp.status_code in (401, 403):
        return False, "auth", "API Key 无效或权限不足（HTTP %s）" % resp.status_code
    if resp.status_code in (404, 405):
        return True, "unsupported", "配置完整（端点不支持连接预检）"
    return False, "http", "API 端点返回 HTTP %s" % resp.status_code


def _verified_recently(conf):
    try:
        stamp = float(conf.get("verified_at") or 0)
    except (TypeError, ValueError):
        stamp = 0.0
    return bool(stamp) and (time.time() - stamp) < _VERIFIED_WINDOW


def detect_openai_compat(cfg):
    conf = dict(cfg.get("openai_compat") or {})
    api_base = str(conf.get("api_base") or "").strip()
    api_key = str(conf.get("api_key") or "").strip()
    model_name = str(conf.get("model_name") or "").strip()

    missing = []
    if not api_base:
        missing.append("api_base")
    if not api_key:
        missing.append("api_key")
    if not model_name:
        missing.append("model_name")

    available = not missing
    detail = "配置完整" if available else "缺少 " + "、".join(missing)
    if available:
        available, kind, detail = _openai_probe(api_base, api_key)
        if not available and kind == "unreachable" and _verified_recently(conf):
            # 连接测试刚通过过：预检抖动不当作「配置丢失」
            available = True
            detail = "已通过连接测试，预检暂时超时（稍后自动重试）"

    return {
        "id": "openai_compat",
        "label": "OpenAI 兼容",
        "configured": bool(api_base or api_key or model_name),
        "available": available,
        "detail": detail,
        "models": [],
        "has_api_key": bool(api_key),
        "fields": [
            {
                "name": "api_base",
                "label": "API Base",
                "type": "text",
                "required": True,
                "value": api_base,
                "placeholder": "https://api.openai.com/v1",
                "hint": "兼容 /chat/completions 的端点地址",
            },
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": not bool(api_key),
                "value": "",
                "placeholder": "已保存，留空保持不变" if api_key else "sk-...",
                "hint": "仅保存在本地 config.json",
            },
            {
                "name": "model_name",
                "label": "模型名称",
                "type": "text",
                "required": True,
                "value": model_name,
                "placeholder": "gpt-4o-mini",
                "hint": "以服务商实际提供的模型 ID 为准",
            },
        ],
        "values": {"api_base": api_base, "model_name": model_name, "api_key": mask_key(api_key)},
    }


def _rank(provider_id):
    return PROVIDER_RANK.get(provider_id, 99)


def _best_available(providers):
    available = [item for item in providers if item["available"]]
    if not available:
        return None
    available.sort(key=lambda item: _rank(item["id"]))
    return available[0]


def detect_auto(cfg, providers):
    """Auto Model 虚拟服务商：只描述「当前会选谁」，真正的调用仍走 detect 出来的服务商。"""
    best = _best_available(providers)
    configured = str(cfg.get("provider") or "").strip().lower() == AUTO_ID
    if best:
        detail = "自动选择当前最优服务商：%s（%s）" % (best["label"], best["detail"])
    elif any(item["configured"] for item in providers):
        detail = "暂无可用的服务商；配置恢复后 Auto Model 会自动接管"
    else:
        detail = "还没有配置任何服务商"
    return {
        "id": AUTO_ID,
        "label": "Auto Model",
        "configured": configured,
        "available": bool(best),
        "detail": detail,
        "models": [],
        "fields": [],
        "values": {},
        "resolved": best["id"] if best else None,
        "candidates": [
            {"id": item["id"], "label": item["label"], "available": item["available"]}
            for item in providers
        ],
    }


def summarize(cfg):
    """返回服务商总览；available=False 时宿主必须阻止对话。

    检测会访问网络（ollama tags / openai models），结果缓存 5 秒，
    避免一次对话请求里门禁与核心各探测一遍。

    preferred 是界面应高亮的配置项（可能是 auto）；resolved 是实际用于对话的服务商 id。
    """
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "provider": cfg.get("provider"),
                "ollama": cfg.get("ollama"),
                "openai_compat": cfg.get("openai_compat"),
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    now = time.monotonic()
    with _status_lock:
        cached = _status_cache.get(fingerprint)
        if cached and now - cached[0] < _STATUS_TTL:
            return copy.deepcopy(cached[1])

    real = [detect_ollama(cfg), detect_openai_compat(cfg)]
    auto = detect_auto(cfg, real)
    available_ids = [item["id"] for item in real if item["available"]]

    preferred = None
    if available_ids:
        configured = cfg.get("provider")
        if configured == AUTO_ID:
            preferred = AUTO_ID
        elif configured in available_ids:
            preferred = configured
        else:
            preferred = auto["resolved"]

    result = {
        "available": bool(available_ids),
        "preferred": preferred,
        "resolved": auto["resolved"],
        "configured": cfg.get("provider"),
        "auto": {"id": AUTO_ID, "resolved": auto["resolved"]},
        "providers": [auto] + real,
    }

    with _status_lock:
        _status_cache.clear()
        _status_cache[fingerprint] = (now, copy.deepcopy(result))
    return result


def _write(data_dir, cfg):
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "config.json")
    tmp = path + ".tmp"
    with _save_lock:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return cfg


def save(data_dir, provider, payload, current=None, activate=True):
    """校验并原子写入配置；返回新配置。失败抛 ValueError。

    activate=False 时只保存该服务商的字段，不改变「首选服务商」——
    用于「测试连接通过后自动落盘」，避免把用户的 Auto Model 选择挤掉。
    """
    if provider not in PROVIDER_IDS:
        raise ValueError("未知服务商: %s" % provider)

    cfg = dict(current or {})
    cfg["ollama"] = dict(cfg.get("ollama") or {})
    cfg["openai_compat"] = dict(cfg.get("openai_compat") or {})
    payload = dict(payload or {})

    if provider == AUTO_ID:
        if activate:
            cfg["provider"] = AUTO_ID
        _write(data_dir, cfg)
        return cfg

    if provider == "ollama":
        model = str(payload.get("model") or "").strip()
        if not model:
            raise ValueError("请填写模型名称")
        cfg["ollama"]["model"] = model
        cfg["ollama"]["keep_alive"] = str(payload.get("keep_alive") or "").strip() or "30m"
    else:
        previous = dict(cfg["openai_compat"])
        api_base = str(payload.get("api_base") or "").strip().rstrip("/")
        api_key = str(payload.get("api_key") or "").strip()
        model_name = str(payload.get("model_name") or "").strip()
        if not api_base.startswith(("http://", "https://")):
            raise ValueError("API Base 必须以 http:// 或 https:// 开头")
        if not api_key and not previous.get("api_key"):
            raise ValueError("请填写 API Key")
        if not model_name:
            raise ValueError("请填写模型名称")
        cfg["openai_compat"]["api_base"] = api_base
        cfg["openai_compat"]["model_name"] = model_name
        if api_key:
            cfg["openai_compat"]["api_key"] = api_key
        # 端点和 Key 变了，旧的「已验证」记忆作废
        if api_base != previous.get("api_base") or (
            api_key and api_key != previous.get("api_key")
        ):
            cfg["openai_compat"].pop("verified_at", None)

    if activate:
        cfg["provider"] = provider

    _write(data_dir, cfg)
    return cfg


def mark_verified(data_dir, provider, current=None):
    """记录「连接测试通过」，让预检抖动时不至于把已配好的服务商判死。"""
    if provider != "openai_compat":
        return dict(current or {})
    cfg = dict(current or {})
    conf = dict(cfg.get("openai_compat") or {})
    if not conf.get("api_key"):
        return cfg
    conf["verified_at"] = time.time()
    cfg["openai_compat"] = conf
    _write(data_dir, cfg)
    return cfg


def test(provider, payload, current=None):
    """连接测试：不落盘。返回 {ok, message}。"""
    payload = dict(payload or {})
    current = dict(current or {})

    if provider == AUTO_ID:
        providers = [detect_ollama(current), detect_openai_compat(current)]
        best = _best_available(providers)
        if best:
            return {
                "ok": True,
                "message": "Auto Model 已选择最优服务商：%s（%s）" % (best["label"], best["detail"]),
                "resolved": best["id"],
            }
        reasons = ["%s：%s" % (item["label"], item["detail"]) for item in providers]
        return {"ok": False, "message": "暂无可用的服务商（%s）" % "；".join(reasons)}

    conf = dict(current.get(provider) or {})

    if provider == "ollama":
        model = str(payload.get("model") or conf.get("model") or "").strip()
        if not model:
            return {"ok": False, "message": "请先填写模型名称"}
        probe_cfg = {"ollama": dict(conf)}
        probe_cfg["ollama"]["model"] = model
        started, auto_message = ensure_ollama_serving(probe_cfg, wait=6.0)
        models, error = _ollama_tags(probe_cfg, timeout=3.0)
        if models is None:
            return {
                "ok": False,
                "message": "无法连接 Ollama 服务（%s）" % (error or auto_message),
            }
        if not _model_installed(model, models):
            return {
                "ok": False,
                "message": "服务已连接，但未安装模型 %s（已安装: %s）"
                % (model, ", ".join(models) or "无"),
            }
        message = "连接成功，模型 %s 可用" % model
        if started:
            message += "（%s）" % auto_message
        return {"ok": True, "message": message, "models": models}

    if provider == "openai_compat":
        api_base = str(payload.get("api_base") or conf.get("api_base") or "").strip().rstrip("/")
        api_key = str(payload.get("api_key") or conf.get("api_key") or "").strip()
        model_name = str(payload.get("model_name") or conf.get("model_name") or "").strip()
        if not (api_base and api_key and model_name):
            return {"ok": False, "message": "请填写 API Base、API Key 和模型名称"}
        try:
            resp = requests.post(
                api_base + "/chat/completions",
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                },
                timeout=15,
            )
            if resp.status_code >= 400:
                return {"ok": False, "message": "服务返回 HTTP %s: %s" % (resp.status_code, _short(resp.text))}
            return {"ok": True, "message": "连接成功，模型 %s 可以响应" % model_name}
        except Exception as error:
            return {"ok": False, "message": "连接失败: %s" % _short(error)}

    return {"ok": False, "message": "未知服务商: %s" % provider}
