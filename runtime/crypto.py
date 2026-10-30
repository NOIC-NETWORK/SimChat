"""SimChat 本地加密 — Fernet 对称加密，密钥文件落在 data/.secret_key。

设计原则：
- 密钥自动生成，首次使用时创建；丢失则无法解密既有数据（但不会让整个系统崩溃）
- 只用于敏感字段（API Key、密码、AK 等），不加密普通配置
- 加密结果带上前缀 ``f1:`` 方便识别；旧的明文值（无前缀）视为未加密直接返回
- 模块级单例：进程内只加载一次密钥，减少文件 I/O
"""

import base64
import hashlib
import os
import threading

from cryptography.fernet import Fernet, InvalidToken

_KEY_FILENAME = ".secret_key"
_PREFIX = "f1:"  # 加密值前缀，用于区分明文

_lock = threading.Lock()
_fernet = None  # 延迟初始化


def _key_path(data_dir):
    return os.path.join(data_dir, _KEY_FILENAME)


def _derive_key(material: bytes) -> bytes:
    """把任意 32+ 字节材料 derive 成 Fernet 需要的 URL-safe base64 32 字节 key。"""
    digest = hashlib.sha256(material).digest()
    return base64.urlsafe_b64encode(digest)


def _load_or_create_fernet(data_dir):
    """加载或生成密钥，返回 Fernet 实例。"""
    global _fernet
    if _fernet is not None:
        return _fernet

    with _lock:
        if _fernet is not None:
            return _fernet
        path = _key_path(data_dir)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                # 兼容旧格式：文件里可能存的是 base64 key，也可能是原始 material
                if len(raw) == 44 and raw.endswith(b"="):
                    # 已经是 Fernet key
                    key = raw.strip()
                else:
                    key = _derive_key(raw)
                _fernet = Fernet(key)
                return _fernet
            except Exception:
                # 密钥损坏，重新生成（旧密文将不可解密，但至少系统可用）
                pass

        # 首次使用：生成新密钥并原子写入
        os.makedirs(data_dir, exist_ok=True)
        key = Fernet.generate_key()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(key)
        os.replace(tmp, path)
        # 权限收紧（POSIX；Windows 上 chmod 无效但不影响功能）
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        _fernet = Fernet(key)
        return _fernet


def encrypt(plaintext: str, data_dir: str) -> str:
    """加密明文字符串，返回带 ``f1:`` 前缀的密文字符串。空值原样返回。"""
    if plaintext is None or plaintext == "":
        return plaintext or ""
    f = _load_or_create_fernet(data_dir)
    token = f.encrypt(plaintext.encode("utf-8"))
    return _PREFIX + token.decode("ascii")


def decrypt(ciphertext: str, data_dir: str) -> str:
    """解密带 ``f1:`` 前缀的密文。空值或无前缀值原样返回；解密失败返回空串。"""
    if not isinstance(ciphertext, str) or ciphertext == "":
        return ""
    if not ciphertext.startswith(_PREFIX):
        # 明文遗留，直接返回（允许平滑过渡）
        return ciphertext
    try:
        f = _load_or_create_fernet(data_dir)
        token = ciphertext[len(_PREFIX):].encode("ascii")
        return f.decrypt(token).decode("utf-8")
    except (InvalidToken, Exception):
        return ""


def is_encrypted(value: str) -> bool:
    """判断值是否是本模块加密过的（带 ``f1:`` 前缀）。"""
    return isinstance(value, str) and value.startswith(_PREFIX)
