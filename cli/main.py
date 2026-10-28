"""SimChat CLI —— 四个子命令：init / pack / verify / publish。

设计原则（Phase 4）：
  - 独立于 loader/runtime 运行时：只 import loader.keys 和 loader.verify 里的**纯函数**，
    不 import lifecycle / sandbox / resolver / registry（这些是运行时依赖）。
  - 四个子命令共用 argparse 主入口，子命令各自独立、幂等、不涉及宿主进程。
  - 私钥文件路径走 ``--key`` 参数，默认 ``~/.simchat/private_key.pem``；
    私钥文件会被 CLI 自动加入 .gitignore 提示。
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import zipfile

# ---- 确保 simchat 根在 sys.path ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402

from simchat.loader.verify import package_digest, verify_package  # noqa: E402
from simchat.loader.keys import (  # noqa: E402
    build_signing_payload,
    format_signature,
    generate_keypair,
    load_public_keys,
    sign_payload,
)
from simchat.loader.manifest import validate_manifest  # noqa: E402


# ---------------------------------------------------------------------------
# 模板生成 —— init 子命令
# ---------------------------------------------------------------------------

AGENT_CONFIG_TEMPLATE = {
    "$schema": "../../simchat/spec/mod-manifest.schema.json",
    "id": "com.example.mypersona",
    "type": "agent-config",
    "name": "My Persona",
    "description": "一个自定义人设 MOD",
    "version": "0.1.0",
    "abi": "lmbrew-mod/1",
    "license": "MIT",
    "config": {
        "persona": "custom",
        "system_prompt_file": "prompts/persona.txt",
        "theme": "theme.css",
        "params": {
            "think_mode": "medium"
        }
    }
}


SKILL_TEMPLATE_MANIFEST = {
    "$schema": "../../simchat/spec/mod-manifest.schema.json",
    "id": "com.example.helloskill",
    "type": "skill",
    "name": "Hello Skill",
    "description": "一个最简单的 skill MOD 示例",
    "version": "0.1.0",
    "abi": "lmbrew-mod/1",
    "entry": "hello_skill:register",
    "hooks": ["agent.tool"],
    "capabilities": {
        "fs": {"read": ["workspace"]}
    },
    "requires": {
        "lmbrew": ">=2.0,<3",
        "python": ">=3.9"
    },
    "license": "MIT"
}


SKILL_TEMPLATE_PY = '''"""Hello Skill — 最简单的 skill MOD 模板。

CLI init 生成的骨架。在 ModApi 上 register_tool() 后，宿主就能用 call_tool() 调用。
"""

from simchat_mod import ToolSpec


def say_hello(params):
    """示例 backend：接收 dict，返回 dict|str。"""
    name = (params or {}).get("name", "world")
    return {"success": True, "message": "Hello, %s!" % name}


def register(api):
    """entry 函数 —— manifest.entry = 'hello_skill:register'。"""
    api.register_tool(ToolSpec(
        name="say_hello",
        label="Say Hello",
        description="向 Agent 返回一句问候",
        risk="read",
        backend="hello_skill:say_hello",
        params_schema={"type": "object", "properties": {
            "name": {"type": "string", "description": "要问候的人"}
        }},
    ))
    return api
'''


AUTOMATION_TEMPLATE_MANIFEST = {
    "$schema": "../../simchat/spec/mod-manifest.schema.json",
    "id": "com.example.daily-digest",
    "type": "automation",
    "name": "Daily Digest Automation",
    "description": "每天 9 点生成工作区变更摘要（示例）",
    "version": "0.1.0",
    "abi": "lmbrew-mod/1",
    "entry": "flow.json",
    "hooks": ["automation.hook"],
    "capabilities": {
        "schedule": True,
        "fs": {"write": ["workspace"]}
    },
    "requires": {
        "lmbrew": ">=2.0,<3"
    },
    "automation": {
        "flow_file": "flow.json"
    },
    "license": "MIT"
}


AUTOMATION_TEMPLATE_FLOW = '''{
  "id": "daily.workspace.digest",
  "version": "0.1.0",
  "trigger": { "type": "cron", "expr": "0 9 * * 1-5" },
  "steps": [
    {
      "id": "scan",
      "use": "skill:readFile",
      "args": { "file_path": "${env:WORKSPACE}/README.md" }
    },
    {
      "id": "sum",
      "use": "agent:run",
      "args": { "goal": "总结输入文件的内容和要点", "input": "${scan.output}" }
    },
    {
      "id": "write",
      "use": "file:write",
      "args": { "path": "digest.md", "content": "${sum.output}" },
      "approval": "required"
    }
  ],
  "policy": { "max_runtime_s": 300, "daily_quota": 20, "on_error": "stop" }
}
'''


BINARY_TEMPLATE_MANIFEST = {
    "$schema": "../../simchat/spec/mod-manifest.schema.json",
    "id": "com.example.mybinary",
    "type": "binary",
    "name": "My Binary MOD",
    "description": "一个 binary MOD 模板 —— 发布时需要签名",
    "version": "0.1.0",
    "abi": "lmbrew-mod/1",
    "entry": "mybinary.pipeline:register",
    "hooks": ["chat.mode"],
    "capabilities": {
        "net": {"domains": ["example.com"]}
    },
    "requires": {
        "lmbrew": ">=2.0,<3",
        "python": ">=3.9"
    },
    "license": "proprietary"
}


BINARY_TEMPLATE_PY = '''"""My Binary MOD 模板。

binary MOD 走签名流程：pack 时 CLI 会算 integrity + 用你的私钥签名，
回写 manifest.json。宿主加载期两阶段校验（integrity + ed25519）。
"""

from simchat_mod import ModeSpec


def register(api):
    """entry —— manifest.entry = 'mybinary.pipeline:register'。"""
    api.register_mode(ModeSpec(
        id="mybinary",
        label="我的模式",
        icon="🔧",
        description="binary MOD 示例模式",
    ))
    return api
'''


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _init_agent_config(target, mod_id):
    os.makedirs(os.path.join(target, "prompts"), exist_ok=True)
    os.makedirs(os.path.join(target, "assets"), exist_ok=True)

    manifest = dict(AGENT_CONFIG_TEMPLATE)
    manifest["id"] = mod_id
    manifest["name"] = mod_id.split(".")[-1].title()
    _write_json(os.path.join(target, "manifest.json"), manifest)

    _write_text(os.path.join(target, "prompts", "persona.txt"),
                "你是一个 %s 的自定义人设。\n" % mod_id)
    _write_text(os.path.join(target, "theme.css"),
                "/* %s theme */\nbody { --simchat-accent: #6366f1; }\n" % mod_id)


def _init_skill(target, mod_id):
    os.makedirs(os.path.join(target, "python"), exist_ok=True)

    manifest = dict(SKILL_TEMPLATE_MANIFEST)
    manifest["id"] = mod_id
    manifest["entry"] = "hello_skill:register"
    manifest["name"] = mod_id.split(".")[-1].title()
    _write_json(os.path.join(target, "manifest.json"), manifest)
    _write_text(os.path.join(target, "python", "hello_skill.py"), SKILL_TEMPLATE_PY)
    _write_text(os.path.join(target, "python", "__init__.py"), "")


def _init_automation(target, mod_id):
    manifest = dict(AUTOMATION_TEMPLATE_MANIFEST)
    manifest["id"] = mod_id
    manifest["name"] = mod_id.split(".")[-1].title()
    _write_json(os.path.join(target, "manifest.json"), manifest)
    _write_text(os.path.join(target, "flow.json"), AUTOMATION_TEMPLATE_FLOW)


def _init_binary(target, mod_id):
    os.makedirs(os.path.join(target, "python"), exist_ok=True)
    os.makedirs(os.path.join(target, "web"), exist_ok=True)

    manifest = dict(BINARY_TEMPLATE_MANIFEST)
    manifest["id"] = mod_id
    manifest["entry"] = "mybinary.pipeline:register"
    manifest["name"] = mod_id.split(".")[-1].title()
    _write_json(os.path.join(target, "manifest.json"), manifest)
    _write_text(os.path.join(target, "python", "mybinary.py"), BINARY_TEMPLATE_PY)
    _write_text(os.path.join(target, "python", "__init__.py"), "")
    _write_text(os.path.join(target, "web", "mybinary.js"),
                "// %s frontend entry (manifest.web_entry 可选)\n" % mod_id)


INIT_HANDLERS = {
    "agent-config": _init_agent_config,
    "skill": _init_skill,
    "automation": _init_automation,
    "binary": _init_binary,
}


def cmd_init(args):
    handler = INIT_HANDLERS.get(args.type)
    if handler is None:
        print("[SimChat] 未知 MOD 类型: %s" % args.type)
        return 2

    target = args.target or os.path.join(os.getcwd(), args.name)
    if os.path.exists(target) and not args.force:
        print("[SimChat] 目录已存在: %s （加 --force 覆盖）" % target)
        return 2
    os.makedirs(target, exist_ok=True)

    handler(target, args.name)
    print("[SimChat] ✓ 已生成 %s 模板 → %s" % (args.type, target))
    print("  → 编辑 manifest.json 填写真实 id / version / description")
    print("  → 编写你的 MOD 代码")
    print("  → 打包: python -m simchat.cli pack %s" % target)
    return 0


# ---------------------------------------------------------------------------
# pack 子命令
# ---------------------------------------------------------------------------

def _find_private_key(key_path):
    """默认 key 路径：~/.simchat/private_key.pem；CLI --key 可覆盖。"""
    if key_path:
        return key_path
    home = os.path.expanduser("~")
    candidate = os.path.join(home, ".simchat", "private_key.pem")
    if os.path.isfile(candidate):
        return candidate
    return None


def _load_extra_pub_keys(pub_key_paths):
    """从 --pub-key 指定的 PEM 文件加载 Ed25519PublicKey 列表。
    开发期用：让本地 generate_keypair 生成的私钥签名的包能被本地 verify。
    """
    if not pub_key_paths:
        return None
    result = []
    for path in pub_key_paths:
        try:
            with open(path, "rb") as f:
                pub = serialization.load_pem_public_key(f.read())
            result.append(pub)
        except Exception as e:
            print("  ! 警告: 加载公钥 %s 失败: %s（跳过）" % (path, e))
    return result or None


_PACK_REQUIRED_KEYS = ("id", "type", "name", "version", "abi")


def _precheck_manifest(manifest):
    """pack 前轻量预检查 —— 只验证 pack 流程依赖的基础字段。
    binary 的 signature/integrity 在 pack 中补齐，不在此阶段强制。
    """
    missing = [k for k in _PACK_REQUIRED_KEYS
               if not isinstance(manifest.get(k), str) or not manifest[k].strip()]
    if missing:
        return "缺少必填字段: %s" % ", ".join(missing)
    return None


def cmd_pack(args):
    package_dir = os.path.abspath(args.package_dir)
    manifest_path = os.path.join(package_dir, "manifest.json")

    if not os.path.isfile(manifest_path):
        print("[SimChat] ✗ manifest.json 不存在: %s" % manifest_path)
        return 2

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print("[SimChat] ✗ manifest.json 读取失败: %s" % e)
        return 2

    # pack 前轻量预检查（不强制 binary 的 signature/integrity —— pack 流程会补齐）
    pre_err = _precheck_manifest(manifest)
    if pre_err:
        print("[SimChat] ✗ manifest 预检查失败: %s" % pre_err)
        return 2

    # 算 integrity（不写入磁盘，先更新内存 dict）
    integrity = package_digest(package_dir)
    manifest["integrity"] = integrity
    print("[SimChat] integrity  = %s" % integrity)

    # binary → 签名
    if manifest.get("type") == "binary":
        key_path = _find_private_key(getattr(args, "key", None))
        if not key_path:
            print("[SimChat] ✗ binary MOD 需要私钥，但找不到 key 文件。")
            print("  生成一把新密钥对：")
            print("    python -m simchat.cli gen-key")
            print("  然后把私钥放到 ~/.simchat/private_key.pem，或用 --key 指定路径")
            return 2

        try:
            with open(key_path, "rb") as f:
                priv_pem = f.read()
        except Exception as e:
            print("[SimChat] ✗ 读取私钥失败: %s" % e)
            return 2

        payload = build_signing_payload(manifest, integrity)
        signature = sign_payload(payload, priv_pem)
        manifest["signature"] = signature
        print("[SimChat] signature = %s" % signature[:30] + "...")
        print("[SimChat] （签名 payload 为 integrity + version + requires 的规范化串联）")

    # 回写 manifest
    _write_json(manifest_path, manifest)
    print("[SimChat] ✓ manifest.json 已更新（integrity + signature 字段）")

    # pack 后完整校验（此时所有 pack 补齐的字段都已到位）
    errors, warnings = validate_manifest(manifest)
    for w in warnings:
        print("  ! 警告: %s" % w)
    if errors:
        print("[SimChat] ✗ pack 后 manifest 完整校验失败:")
        for err in errors:
            print("    - %s" % err)
        return 2

    # 最终 verify（binary 会走两阶段 integrity + 签名；非 binary 直接通过）
    extra_pub = _load_extra_pub_keys(getattr(args, "pub_key", None))
    ok, msg = verify_package(package_dir, manifest, extra_public_keys=extra_pub)
    if not ok:
        print("[SimChat] ✗ pack 后 verify_package 失败: %s" % msg)
        return 2

    # 可选 zip
    if args.zip:
        dist_dir = args.dist or os.path.join(os.path.dirname(package_dir), "dist")
        os.makedirs(dist_dir, exist_ok=True)
        mod_id = manifest.get("id", os.path.basename(package_dir))
        version = manifest.get("version", "0.0.0")
        zip_name = "%s-%s.zip" % (mod_id, version)
        zip_path = os.path.join(dist_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(package_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for name in files:
                    if name.endswith((".pyc", ".pyo")):
                        continue
                    full = os.path.join(root, name)
                    arcname = os.path.relpath(full, package_dir)
                    zf.write(full, arcname)
        print("[SimChat] ✓ 已打包 zip → %s" % zip_path)

    return 0


# ---------------------------------------------------------------------------
# verify 子命令
# ---------------------------------------------------------------------------

def cmd_verify(args):
    package_dir = os.path.abspath(args.package_dir)
    manifest_path = os.path.join(package_dir, "manifest.json")

    if not os.path.isfile(manifest_path):
        print("[SimChat] ✗ manifest.json 不存在: %s" % manifest_path)
        return 2

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print("[SimChat] ✗ manifest.json 读取失败: %s" % e)
        return 2

    errors, warnings = validate_manifest(manifest)
    for w in warnings:
        print("  ! 警告: %s" % w)
    if errors:
        print("[SimChat] ✗ manifest 校验失败:")
        for err in errors:
            print("    - %s" % err)
        return 2

    extra_pub = _load_extra_pub_keys(getattr(args, "pub_key", None))
    ok, msg = verify_package(package_dir, manifest, extra_public_keys=extra_pub)
    if not ok:
        print("[SimChat] ✗ verify_package 失败: %s" % msg)
        return 2

    mtype = manifest.get("type")
    if mtype == "binary":
        print("[SimChat] ✓ binary MOD 两阶段校验通过（integrity + ed25519）")
    else:
        print("[SimChat] ✓ manifest 结构校验通过（非 binary 类型跳过签名）")

    integrity = package_digest(package_dir)
    print("[SimChat] integrity = %s" % integrity)
    return 0


# ---------------------------------------------------------------------------
# publish 子命令
# ---------------------------------------------------------------------------

def cmd_publish(args):
    package_dir = os.path.abspath(args.package_dir)
    manifest_path = os.path.join(package_dir, "manifest.json")

    if not os.path.isfile(manifest_path):
        print("[SimChat] ✗ manifest.json 不存在: %s" % manifest_path)
        return 2

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print("[SimChat] ✗ manifest.json 读取失败: %s" % e)
        return 2

    errors, warnings = validate_manifest(manifest)
    for w in warnings:
        print("  ! 警告: %s" % w)
    if errors:
        print("[SimChat] ✗ manifest 校验失败:")
        for err in errors:
            print("    - %s" % err)
        return 2

    ok, msg = verify_package(package_dir, manifest,
                             extra_public_keys=_load_extra_pub_keys(getattr(args, "pub_key", None)))
    if not ok:
        print("[SimChat] ✗ verify_package 失败: %s" % msg)
        print("  → 先跑 `python -m simchat.cli pack %s` 更新 integrity + signature" % package_dir)
        return 2

    integrity = package_digest(package_dir)
    mtype = manifest.get("type")

    # 生成 registry 条目
    entry = {
        "mod_id": manifest["id"],
        "type": mtype,
        "name": manifest["name"],
        "description": manifest.get("description", ""),
        "license": manifest.get("license", "MIT"),
        "publisher": args.publisher or "Community",
        "homepage": manifest.get("homepage", ""),
        "versions": [{
            "version": manifest["version"],
            "abi": manifest.get("abi", "lmbrew-mod/1"),
            "requires": manifest.get("requires", {}),
            "download": {
                "type": "git-path",
                "url": args.repo_url or "https://github.com/your-username/your-simchat-mods",
                "path": "mods/%s" % manifest["id"],
                "ref": "HEAD",
            },
            "manifest_hash": integrity,
        }],
    }

    if mtype == "binary" and manifest.get("signature"):
        entry["versions"][0]["signature"] = manifest["signature"]
    if manifest.get("capabilities"):
        entry["versions"][0]["capabilities"] = manifest["capabilities"]

    entry["versions"][0]["published_at"] = datetime.date.today().isoformat()
    entry["versions"][0]["downloads"] = 0
    entry["versions"][0]["deprecated"] = False

    if args.output:
        _write_json(args.output, entry)
        print("[SimChat] ✓ registry 条目已写入 %s" % args.output)
    else:
        print("[SimChat] ✓ registry 条目（贴进 simchat/registry/index.json 的 entries[] 数组）：")
        print(json.dumps(entry, ensure_ascii=False, indent=2))

    print("")
    print("提交流程：")
    print("  1. 把上面的 JSON 合并进 registry/index.json 的 entries[]")
    print("  2. 创建 PR 到 registry 仓库")
    print("  3. 维护者审核签名 + capabilities 后合并")
    return 0


# ---------------------------------------------------------------------------
# gen-key 子命令（私钥生成 —— 首次 binary MOD 发布需要）
# ---------------------------------------------------------------------------

def cmd_gen_key(args):
    priv_pem, pub_pem = generate_keypair()
    key_dir = args.key_dir or os.path.join(os.path.expanduser("~"), ".simchat")
    os.makedirs(key_dir, exist_ok=True)
    priv_path = os.path.join(key_dir, "private_key.pem")
    pub_path = os.path.join(key_dir, "public_key.pub")

    with open(priv_path, "wb") as f:
        f.write(priv_pem)
    os.chmod(priv_path, 0o600)  # 仅 Unix 有效；Windows 下略过

    with open(pub_path, "wb") as f:
        f.write(pub_pem)

    print("[SimChat] ✓ 密钥对已生成:")
    print("  私钥: %s  (不要进 git，不要发给别人)" % priv_path)
    print("  公钥: %s  (发给官方，添加到 simchat/loader/public_keys/)" % pub_path)
    print("")
    print("下次 pack binary MOD 时，CLI 会自动用这把私钥签名。")
    print("如果换机器，记得把公钥也换上去，让 loader 认识新签名。")
    return 0


# ---------------------------------------------------------------------------
# main —— argparse 主入口
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="simchat",
        description="SimChat CLI — MOD 的 init / pack / verify / publish",
    )
    parser.add_argument("--version", action="version", version="simchat 0.4.0 (Phase 4)")

    sub = parser.add_subparsers(dest="command", required=True)

    # ---- init ----
    p_init = sub.add_parser("init", help="生成 MOD 模板骨架")
    p_init.add_argument("--type", required=True, choices=list(INIT_HANDLERS.keys()),
                        help="MOD 类型")
    p_init.add_argument("--name", required=True, help="MOD id，形如 com.example.mymod")
    p_init.add_argument("--target", help="输出目录（默认 ./<name>）")
    p_init.add_argument("--force", action="store_true", help="目标目录已存在时覆盖")
    p_init.set_defaults(func=cmd_init)

    # ---- pack ----
    p_pack = sub.add_parser("pack", help="算 integrity + 签名 + 可选 zip")
    p_pack.add_argument("package_dir", help="MOD 目录（含 manifest.json）")
    p_pack.add_argument("--key", help="私钥 PEM 路径（默认 ~/.simchat/private_key.pem）")
    p_pack.add_argument("--pub-key", action="append", default=None,
                        help="开发期额外公钥路径（可多次指定，便于本地测试签名）")
    p_pack.add_argument("--zip", action="store_true", help="额外打包 .zip 到 dist/")
    p_pack.add_argument("--dist", help="zip 输出目录（默认 <mod-dir>/../dist/）")
    p_pack.set_defaults(func=cmd_pack)

    # ---- verify ----
    p_verify = sub.add_parser("verify", help="本地两阶段校验（integrity + 签名）")
    p_verify.add_argument("package_dir", help="MOD 目录（含 manifest.json）")
    p_verify.add_argument("--pub-key", action="append", default=None,
                          help="开发期额外公钥路径（可多次指定，便于本地测试签名）")
    p_verify.set_defaults(func=cmd_verify)

    # ---- publish ----
    p_pub = sub.add_parser("publish", help="验证后生成 registry 条目 JSON 片段")
    p_pub.add_argument("package_dir", help="MOD 目录（含 manifest.json）")
    p_pub.add_argument("--publisher", help="发布者名（默认 Community）")
    p_pub.add_argument("--repo-url", help="仓库 URL（用于 download 字段）")
    p_pub.add_argument("--output", help="把 registry 条目写到文件而非打印")
    p_pub.add_argument("--pub-key", action="append", default=None,
                       help="开发期额外公钥路径（可多次指定，便于本地测试签名）")
    p_pub.set_defaults(func=cmd_publish)

    # ---- gen-key ----
    p_key = sub.add_parser("gen-key", help="生成 ed25519 密钥对")
    p_key.add_argument("--key-dir", help="密钥存放目录（默认 ~/.simchat）")
    p_key.set_defaults(func=cmd_gen_key)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
