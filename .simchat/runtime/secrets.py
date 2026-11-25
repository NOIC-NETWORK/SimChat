"""本地密钥加密 —— 让 data/config.json 里不再出现明文 API Key。

方案：Fernet（AES-128-CBC + HMAC）加密，主密钥保存在 ``data/.secret.key``。
  · Windows：主密钥先用 DPAPI 包裹（CryptProtectData，仅当前用户可解），
    再落盘；别人拷走文件也解不开。
  · 其他平台：主密钥文件 chmod 600。

密文格式为 ``enc:v1:<token>``，解密对不带前缀的值原样返回，因此旧配置
可以平滑迁移：启动时由 :func:`migrate` 把明文 key 加密后原子写回。

本模块只管「服务商凭据」：``openai_compat.api_key`` 与 ``anthropic.api_key``。
其他段（settings / workspace / comms）不在此处理。
"""

import base64
import ctypes
import json
import os
import sys

_PREFIX = "enc:v1:"
_KEY_FILE = ".secret.key"
_SECRET_FIELDS = {
    "openai_compat": ("api_key",),
    "anthropic": ("api_key",),
}

_FERNET_CACHE = {}
_WARNED = set()


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(_PREFIX)


# ---------------- 主密钥 ----------------


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.c_void_p)]


def _dpapi(data, protect):
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    blob_in = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.c_void_p))
    blob_out = _BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(
        ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)
    ):
        raise OSError("DPAPI 调用失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _wrap(key):
    if sys.platform == "win32":
        return b"dpapi:v1:" + base64.b64encode(_dpapi(key, True))
    return b"raw:v1:" + base64.b64encode(key)


def _unwrap(blob):
    if blob.startswith(b"dpapi:v1:"):
        return _dpapi(base64.b64decode(blob[len(b"dpapi:v1:"):]), False)
    if blob.startswith(b"raw:v1:"):
        return base64.b64decode(blob[len(b"raw:v1:"):])
    raise ValueError("无法识别的主密钥格式")


def _load_key(data_dir):
    from cryptography.fernet import Fernet

    path = os.path.join(data_dir, _KEY_FILE)
    if os.path.exists(path):
        with open(path, "rb") as handle:
            return _unwrap(handle.read())
    key = Fernet.generate_key()
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(_wrap(key))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _fernet(data_dir):
    from cryptography.fernet import Fernet

    cached = _FERNET_CACHE.get(data_dir)
    if cached is None:
        cached = Fernet(_load_key(data_dir))
        _FERNET_CACHE[data_dir] = cached
    return cached


# ---------------- 加解密 ----------------


def encrypt_value(value, data_dir):
    if not isinstance(value, str) or not value or is_encrypted(value):
        return value
    token = _fernet(data_dir).encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_value(value, data_dir):
    if not is_encrypted(value):
        return value
    from cryptography.fernet import InvalidToken

    try:
        return _fernet(data_dir).decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, OSError) as error:
        if data_dir not in _WARNED:
            _WARNED.add(data_dir)
            print("[SimChat] 有 API Key 无法解密（主密钥已变？），请重新填写：%s" % error)
        return ""


def _transform(cfg, fn, data_dir):
    """返回新配置，只替换凭据字段；未命中的段保持原对象。"""
    out = dict(cfg)
    for block, fields in _SECRET_FIELDS.items():
        section = cfg.get(block)
        if not isinstance(section, dict):
            continue
        updated = dict(section)
        for field in fields:
            if updated.get(field):
                updated[field] = fn(updated[field], data_dir)
        out[block] = updated
    return out


def encrypt_config(cfg, data_dir):
    return _transform(cfg, encrypt_value, data_dir)


def decrypt_config(cfg, data_dir):
    return _transform(cfg, decrypt_value, data_dir)


def migrate(data_dir):
    """把磁盘上残留的明文凭据加密后写回；返回加密条数。"""
    path = os.path.join(data_dir, "config.json")
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    pending = 0
    for block, fields in _SECRET_FIELDS.items():
        section = cfg.get(block)
        if not isinstance(section, dict):
            continue
        for field in fields:
            if section.get(field) and not is_encrypted(section[field]):
                pending += 1
    if not pending:
        return 0
    encrypted = encrypt_config(cfg, data_dir)
    # 先验证能解回来，再覆盖磁盘，避免把用户 Key 写坏
    check = decrypt_config(encrypted, data_dir)
    for block, fields in _SECRET_FIELDS.items():
        for field in fields:
            before = (cfg.get(block) or {}).get(field)
            after = (check.get(block) or {}).get(field)
            if before and before != after:
                raise RuntimeError("凭据加密自检失败，已放弃迁移")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(encrypted, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return pending
