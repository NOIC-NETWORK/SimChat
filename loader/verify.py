"""包完整性 + 签名校验（Phase 2 P2.2 重写）。

manifest.json 自身不参与哈希（无法自引用）。__pycache__ / *.pyc 也排除，
避免运行时字节码缓存导致哈希漂移。

binary 类型两阶段：
  1. integrity 哈希校验（本地算的 == manifest 声明的）
  2. ed25519 签名校验（遍历 public_keys/ 下所有公钥尝试验签 + 查吊销列表）

两阶段任一失败 → fail-closed：lifecycle 会把 MOD 设为 status=failed。
非 binary 类型（agent-config / skill / automation）跳过签名校验。
"""

import hashlib
import os

from .keys import (
    build_signing_payload,
    load_public_keys,
    verify_signature,
)

SKIP_DIRS = frozenset(["__pycache__"])
SKIP_FILES = frozenset(["manifest.json"])
SKIP_SUFFIXES = (".pyc", ".pyo")


def package_digest(package_dir):
    """对包内文件按相对路径排序后计算 sha256，返回 `sha256:<hex>`。

    integrity 格式与 schema 严格对齐：^sha256:[a-f0-9]{64}$。
    """
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name in SKIP_FILES or name.endswith(SKIP_SUFFIXES):
                continue
            full_path = os.path.join(root, name)
            relative = os.path.relpath(full_path, package_dir).replace(os.sep, "/")
            hasher.update(relative.encode("utf-8"))
            hasher.update(b"\0")
            with open(full_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    hasher.update(chunk)
            hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def verify_package(package_dir, manifest):
    """binary MOD 两阶段校验；其他类型跳过。返回 (ok, message)。

    两阶段任一失败都会以明确错误信息 fail-closed：
    - integrity 不匹配 → 'integrity 不匹配'
    - 签名格式非法 → '签名字段格式非法'
    - 无可用公钥能验证 → '签名无效'
    - 签名匹配但 key_id 在吊销列表里 → '签名已吊销'
    """
    if manifest.get("type") != "binary":
        return True, ""

    # 阶段 1：integrity
    expected = manifest.get("integrity")
    if not expected:
        return False, "binary MOD 缺少 integrity"
    actual = package_digest(package_dir)
    if actual != expected:
        return False, "integrity 不匹配（manifest=%s, actual=%s）" % (
            str(expected)[:19], actual[:19]
        )

    # 阶段 2：ed25519 签名
    sig = manifest.get("signature")
    if not sig:
        return False, "binary MOD 缺少 signature"

    payload = build_signing_payload(manifest, actual)
    public_keys = load_public_keys()
    if not public_keys:
        return False, "系统未配置任何 MOD 签名公钥，无法验签"

    ok, msg, _key_id = verify_signature(payload, sig, public_keys)
    if not ok:
        return False, msg
    return True, ""
