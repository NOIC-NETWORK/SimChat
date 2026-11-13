"""SimChat Loader（Apache-2.0）。

对外只暴露 ModLoader 与校验工具；MOD 通过 SDK（simchat_mod）接入。
"""

from .lifecycle import ModLoader
from .manifest import KNOWN_HOOKS, validate_manifest
from .registry import ModeRegistry
from .verify import package_digest, verify_package

__all__ = [
    "ModLoader",
    "KNOWN_HOOKS",
    "validate_manifest",
    "ModeRegistry",
    "package_digest",
    "verify_package",
]
