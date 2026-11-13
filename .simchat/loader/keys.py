"""ed25519 密钥 + 签名工具（Phase 2 P2.2）。

verify.py（加载期验签）和 Phase 4 CLI 打包命令（发布期签名）共用。
私钥**绝不进仓库**，只在本地 .gitignore 目录里存。
"""

import base64
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization

PUBLIC_KEYS_DIR = os.path.join(os.path.dirname(__file__), "public_keys")
REVOKED_FILE    = os.path.join(PUBLIC_KEYS_DIR, "revoked.json")


def generate_keypair():
    """生成一把新的 ed25519 密钥对，返回 (private_pem_bytes, public_pem_bytes)。

    私钥用 PKCS8 格式（-----BEGIN PRIVATE KEY-----），公钥用 SubjectPublicKeyInfo，
    两者都能被 cryptography 标准 load_pem 函数解析。
    """
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key()
    private_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def load_public_keys():
    """遍历 public_keys/ 目录加载所有 .pub 文件里的 PEM 公钥，返回列表。"""
    keys = []
    if not os.path.isdir(PUBLIC_KEYS_DIR):
        return keys
    for name in sorted(os.listdir(PUBLIC_KEYS_DIR)):
        if not name.endswith(".pub"):
            continue
        path = os.path.join(PUBLIC_KEYS_DIR, name)
        try:
            with open(path, "rb") as f:
                keys.append(Ed25519PublicKey.from_public_bytes(
                    serialization.load_pem_public_key(f.read()).public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw,
                    )
                ))
        except Exception:
            # 格式非法的公钥跳过（加载期不因此 fail，发布期再报）
            continue
    return keys


def _public_key_id(pub_key):
    """公钥唯一标识：base64(32 字节原始公钥)。"""
    raw = pub_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def load_revoked():
    """读 revoked.json，返回 {key_id_str: {"reason": str, "time": str}}。文件缺失返回 {}。"""
    if not os.path.isfile(REVOKED_FILE):
        return {}
    try:
        with open(REVOKED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def format_signature(raw_sig_bytes):
    """把 64 字节 ed25519 签名包装成 manifest 里的字符串格式 'ed25519:<base64url>'。"""
    b64 = base64.urlsafe_b64encode(raw_sig_bytes).decode("ascii").rstrip("=")
    return "ed25519:" + b64


def parse_signature(sig_str):
    """把 'ed25519:<base64url>' 解出 64 字节原始签名。格式非法返回 None。"""
    if not isinstance(sig_str, str) or not sig_str.startswith("ed25519:"):
        return None
    try:
        b64 = sig_str[len("ed25519:"):]
        # 补齐 base64 padding
        b64 += "=" * (-len(b64) % 4)
        raw = base64.urlsafe_b64decode(b64)
        if len(raw) != 64:
            return None
        return raw
    except Exception:
        return None


def sign_payload(payload_bytes, private_pem_bytes):
    """用 PEM 格式私钥签 payload，返回 'ed25519:<base64url>' 字符串。"""
    priv = serialization.load_pem_private_key(private_pem_bytes, password=None)
    raw_sig = priv.sign(payload_bytes)
    return format_signature(raw_sig)


def verify_signature(payload_bytes, sig_str, public_keys):
    """遍历公钥列表尝试验签。返回 (ok, message, matched_key_id)。

    - 所有公钥都不匹配 → (False, "签名无效", None)
    - 签名匹配某把公钥但该 key_id 在吊销列表里 → (False, "签名已吊销", key_id)
    - 成功 → (True, "", key_id)
    """
    revoked = load_revoked()
    sig_bytes = parse_signature(sig_str)
    if sig_bytes is None:
        return False, "签名字段格式非法（应为 ed25519:<base64>）", None

    for pub in public_keys:
        key_id = _public_key_id(pub)
        try:
            pub.verify(sig_bytes, payload_bytes)
        except Exception:
            continue
        # 验签成功 → 查吊销
        if key_id in revoked:
            return False, "签名已被吊销（key_id=%s, reason=%s）" % (
                key_id[:12] + "...", revoked[key_id].get("reason", "")), key_id
        return True, "", key_id
    return False, "签名无效（无可用公钥能验证）", None


def build_signing_payload(manifest, integrity):
    """binary MOD 的签名负载规范化：
    ``<integrity>\\0<version>\\0<sorted_json_of_requires>``，UTF-8 编码。
    签发布者和加载器必须使用**完全相同**的序列化，空格/键序差异都会导致验签失败。
    """
    requires = manifest.get("requires") or {}
    return (
        integrity.encode("utf-8") + b"\0" +
        (manifest.get("version") or "").encode("utf-8") + b"\0" +
        json.dumps(requires, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
