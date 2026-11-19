# -*- coding: utf-8 -*-
"""Agent 工具集（Phase 1 只读 + Phase 2 写操作 + Phase 3 shell + Phase 4 模式隔离）。

设计要点：
- 沙箱：文件类工具全部以 workdir 为根，拒绝绝对路径与 .. 越界（fail-closed）。
- 分级：read 级免审批直接执行；write 级（file_write/file_edit）逐次审批后执行；
  dangerous 级（shell）默认关闭，开启后仍逐次审批 + 命令黑名单 + 超时 + cwd 限定。
- 截断：所有工具输出统一截断，防止 token 爆炸。
- 模式：chat 模式（懒调用）只暴露 read 级工具；agent 模式暴露全部工具但有红线拦截。
- 红线：即使在 agent 模式下也绝对禁止的路径（/system、/etc/passwd 等），fail-closed。
"""
import json
import os
import re
import time
import glob as globlib
import subprocess

from ..safety import analyze_crisis, reality_check

# 项目根目录（tools.py 位于 simchat/runtime/agent/，上两级即 simchat 根）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# ---- 绝对红线（fail-closed，任何模式都禁止触及）----
# 这些路径即使在 agent 模式 + 用户审批的情况下也绝对不能读写
ABSOLUTE_REDLINES = [
    # 系统目录
    '/system', '/sys', '/proc', '/dev',
    '/etc/passwd', '/etc/shadow', '/etc/sudoers',
    # 用户密钥
    '~/.ssh', '~/.aws', '~/.kube',
    # 系统配置
    '/Windows/System32/config',
    # 项目内自我保护
    'data/agent_runs',
]

# 匹配绝对红线路径（大小写不敏感，Windows/Unix 都要覆盖）
def _is_redline_path(path_lower):
    """检查路径（已转小写）是否命中红线。"""
    for redline in ABSOLUTE_REDLINES:
        rl = redline.lower().rstrip('/\\')
        if path_lower == rl:
            return True
        if path_lower.startswith(rl + '/') or path_lower.startswith(rl + '\\'):
            return True
        # 展开 ~
        home = os.path.expanduser(redline)
        if home and home.lower() != redline and path_lower == home.lower():
            return True
        if home and path_lower.startswith(home.lower() + '/'):
            return True
    return False

MAX_OUTPUT_CHARS = 8192          # 工具输出统一截断长度
MAX_READ_CHARS = 32768           # 单次文件读取字节上限
MAX_WRITE_CHARS = 65536          # 单次文件写入内容上限（防止误写超大内容）
MAX_LIST_ENTRIES = 500           # 目录列举条目上限
MAX_GLOB_RESULTS = 200           # glob 结果上限
MAX_GREP_MATCHES = 50            # grep 命中上限
MAX_GREP_FILES = 500             # grep 扫描文件数上限
MAX_GREP_FILE_SIZE = 2 * 1024 * 1024   # 参与扫描/读取的单文件大小上限
GREP_SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build', 'chroma_db'}

# ---- shell（dangerous 级，Phase 3）----
DEFAULT_SHELL_TIMEOUT = 10        # 单条命令默认超时秒数（options.agent_shell_timeout 可覆盖）
MAX_SHELL_TIMEOUT = 30            # 超时上限：模型传参与配置均不得超过
MAX_SHELL_CMD_CHARS = 8192        # 单条命令长度上限

# 命令黑名单：命中即拒（fail-closed，审批之前就拦下），正则大小写不敏感
SHELL_BLACKLIST = [
    (re.compile(r'rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r', re.I), 'rm -rf 递归强制删除'),
    (re.compile(r'\brmdir\b[^|&]*\s/s\b', re.I), 'rmdir /s 递归删除目录'),
    (re.compile(r'\bdel\b[^|&]*\s/s\b', re.I), 'del /s 递归删除文件'),
    (re.compile(r'\bformat\b\s+[a-z]:', re.I), 'format 格式化磁盘'),
    (re.compile(r'\bmkfs\b', re.I), 'mkfs 格式化文件系统'),
    (re.compile(r'\bdiskpart\b', re.I), 'diskpart 磁盘分区操作'),
    (re.compile(r'\breg\s+(delete|add|import|save|restore)\b', re.I), '注册表写操作'),
    (re.compile(r'\bshutdown\b', re.I), '关机/重启命令'),
    (re.compile(r':\s*\(\s*\)\s*\{', re.I), 'fork 炸弹特征'),
    (re.compile(r'\|\s*(bash|sh|zsh|cmd|powershell|pwsh|iex)\b', re.I), '管道传入远程/本地 shell 执行'),
    (re.compile(r'\b(iex|invoke-expression)\b', re.I), 'PowerShell 动态执行表达式'),
    (re.compile(r'remove-item\b[^|]*-recurse[^|]*-force|remove-item\b[^|]*-force[^|]*-recurse', re.I),
     'Remove-Item 递归强制删除'),
    # 红线目录相关命令
    (re.compile(r'(rm|delete|move|copy).*(?:/system|/proc|/sys|/etc/passwd|/etc/shadow)', re.I), '触碰红线目录'),
    (re.compile(r'(rm|del|remove).*(?:\.ssh|\.aws|\.kube)', re.I), '触碰密钥目录'),
    (re.compile(r'chmod\s+777', re.I), '全局放开权限'),
    (re.compile(r'sudo\b', re.I), 'sudo 提权'),
    (re.compile(r'\bnc\b.*(-e|-c|--shell)', re.I), 'netcat 反弹 shell'),
    (re.compile(r'(wget|curl).*\|\s*(bash|sh|zsh)', re.I), '下载并执行远程脚本'),
]

# 路径穿越特征：.. 作为路径段出现即拒（cwd 锚定项目根，fail-closed）
SHELL_TRAVERSAL_RE = re.compile(r'(^|[\\/\s=&|;(])\.\.(?=[\\/]|$)')

# shell 开关配置（由 Web 蓝图每次 agent 请求按 config 配置；默认关闭）
_shell_config = {'enabled': False, 'timeout': DEFAULT_SHELL_TIMEOUT}


def configure_shell(enabled=False, timeout=DEFAULT_SHELL_TIMEOUT):
    """配置 shell 工具启用状态与默认超时（进程内全局，每次 agent 请求前按 options 同步）。"""
    try:
        t = max(1, min(int(timeout), MAX_SHELL_TIMEOUT))
    except (TypeError, ValueError):
        t = DEFAULT_SHELL_TIMEOUT
    _shell_config['enabled'] = bool(enabled)
    _shell_config['timeout'] = t
    return dict(_shell_config)


class ToolError(Exception):
    """工具执行失败（参数/沙箱校验不通过等），信息将回传给模型以便重选。"""


def truncate_output(text, limit=MAX_OUTPUT_CHARS):
    """统一截断工具输出。"""
    text = text or ''
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[输出已截断，原始长度 {len(text)} 字符]"


def resolve_workdir(workdir=None):
    """解析 workdir：None 时回落到项目根。"""
    wd = os.path.abspath(workdir) if workdir else PROJECT_ROOT
    if not os.path.isdir(wd):
        raise ToolError(f"workdir 不存在: {wd}")
    return wd


def safe_resolve(workdir, rel_path):
    """把模型给出的路径锚定到 workdir；拒绝绝对路径与 .. 越界（fail-closed）；命中红线也拒绝。"""
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ToolError("路径为空")
    p = rel_path.strip().strip('"').strip("'").replace('\\', '/')

    # 红线优先：即使是绝对路径先检查是否命中红线
    full_lower = os.path.abspath(rel_path).replace('\\', '/').lower() if re.match(r'^[A-Za-z]:', p) or p.startswith('/') or p.startswith('~') else None
    if full_lower and _is_redline_path(full_lower):
        raise ToolError(f"命中绝对红线，拒绝访问: {rel_path}")

    # 绝对路径和 ~ 展开也做红线检查
    if p.startswith('~'):
        expanded = os.path.expanduser(p)
        if expanded and _is_redline_path(expanded.lower().replace('\\', '/')):
            raise ToolError(f"命中绝对红线，拒绝访问: {rel_path}")

    if re.match(r'^[A-Za-z]:', p) or p.startswith('//') or p.startswith('/') or p.startswith('~'):
        raise ToolError(f"拒绝绝对路径/越界路径: {rel_path}")
    if any(part == '..' for part in p.split('/')):
        raise ToolError(f"路径包含 ..，拒绝越界: {rel_path}")
    full = os.path.abspath(os.path.join(workdir, p))
    wd_abs = os.path.abspath(workdir)
    try:
        if os.path.commonpath([full, wd_abs]) != wd_abs:
            raise ToolError(f"路径越界: {rel_path}")
    except ValueError:
        raise ToolError(f"路径越界: {rel_path}")

    # 解析后再做一次红线检查（防止 workdir 里嵌套了红线路径）
    if _is_redline_path(full.replace('\\', '/').lower()):
        raise ToolError(f"命中绝对红线，拒绝访问: {rel_path}")

    return full


def _decode_bytes(raw):
    """utf-8 优先，gbk 兜底（Windows 中文项目常见编码）。"""
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('gbk', errors='replace')


class BaseTool:
    """Agent 工具基类。usage 会原样拼进协议段，供模型照抄调用。

    params_schema 声明调用参数：{字段: {"type": 类型, "required": 是否必填}}。
    执行前由 validate_tool_params() 做必填/类型校验；空 dict 表示无约束。
    """
    name = 'base'
    label = '基础工具'
    description = ''
    risk = 'read'
    usage = ''
    params_schema = {}
    category = '其他'
    source = 'builtin'

    def run(self, params, ctx):
        raise NotImplementedError

    def meta(self):
        return {
            'name': self.name,
            'label': self.label,
            'description': self.description,
            'risk': self.risk,
            'usage': self.usage,
            'enabled': True,
            'category': self.category or '其他',
            'source': self.source,
        }


_PARAM_TYPE_LABELS = {
    'string': '字符串', 'integer': '整数', 'number': '数字',
    'boolean': '布尔值', 'object': '对象', 'array': '数组',
}


def _describe_value(value):
    """把实际值压成中文类型名，用于类型错误回灌。"""
    if value is None:
        return '空值'
    if isinstance(value, bool):
        return '布尔值'
    if isinstance(value, str):
        return '字符串'
    if isinstance(value, int):
        return '整数'
    if isinstance(value, float):
        return '小数'
    if isinstance(value, list):
        return '数组'
    if isinstance(value, dict):
        return '对象'
    return type(value).__name__


def _normalize_param_schema(schema):
    """把三种声明形态归一成 {字段: {"type": ..., "required": bool}}。

    支持：内建 params_schema（字段字典）、MOD 的 JSON Schema
    （{"type": "object", "properties": {...}, "required": [...]}）、
    {字段: "类型名"} 的简写。无法识别/为空 → 空 dict（视为无约束）。
    """
    if not isinstance(schema, dict) or not schema:
        return {}
    if 'properties' in schema or schema.get('type') == 'object':
        properties = schema.get('properties')
        if not isinstance(properties, dict):
            return {}
        required = set(schema.get('required') or [])
        fields = {}
        for key, raw in properties.items():
            spec = raw if isinstance(raw, dict) else {}
            fields[key] = {'type': spec.get('type'), 'required': key in required}
        return fields
    fields = {}
    for key, raw in schema.items():
        if isinstance(raw, dict):
            fields[key] = {'type': raw.get('type'), 'required': bool(raw.get('required'))}
        elif isinstance(raw, str):
            fields[key] = {'type': raw, 'required': False}
    return fields


def _check_param_type(value, expected):
    """按 JSON 类型名判断；未知/未声明的类型不做限制。

    integer/number 额外接受可解析的数字字符串——与各工具实现里的 int() 容错保持一致，
    避免把本来能跑通的调用挡在门外。
    """
    if isinstance(expected, (list, tuple)):
        return any(_check_param_type(value, item) for item in expected)
    expected = (expected or '').strip().lower() if isinstance(expected, str) else ''
    if not expected:
        return True
    if expected == 'string':
        return isinstance(value, str)
    if expected == 'boolean':
        return isinstance(value, bool)
    if expected == 'object':
        return isinstance(value, dict)
    if expected == 'array':
        return isinstance(value, list)
    if expected in ('integer', 'number'):
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, float):
            return expected == 'number' or value.is_integer()
        if isinstance(value, str):
            try:
                float(value.strip())
                return True
            except ValueError:
                return False
        return False
    return True


def validate_tool_params(tool, params):
    """执行前校验调用参数；返回错误文本，None 表示通过。

    只校验「必填存在」与「类型明显不符」两项，不拒绝多余参数，
    未声明 params_schema 的方块（含多数 MOD 工具）视为无约束。
    """
    if not isinstance(params, dict):
        params = {}
    schema = _normalize_param_schema(getattr(tool, 'params_schema', None))
    if not schema:
        return None
    problems = []
    for key, spec in schema.items():
        expected = spec.get('type')
        label = _PARAM_TYPE_LABELS.get(expected, '参数') if isinstance(expected, str) else '参数'
        if key not in params or params[key] is None:
            if spec.get('required'):
                problems.append('缺少必填参数 %s（%s）' % (key, label))
            continue
        if isinstance(params[key], str) and not params[key].strip():
            if spec.get('required'):
                problems.append('必填参数 %s 为空（%s）' % (key, label))
            continue
        if not _check_param_type(params[key], expected):
            problems.append('参数 %s 类型错误：期望%s，实际为%s'
                            % (key, label, _describe_value(params[key])))
    if not problems:
        return None
    name = getattr(tool, 'name', '') or '未知工具'
    usage = getattr(tool, 'usage', '') or ('%s PARAMS:{...}' % name)
    return ('参数校验失败（本次调用未执行）：%s。请修正后重试，格式参考：/$TOOL:%s'
            % ('；'.join(problems), usage.lstrip('/')))


def _glob_same_name(workdir, filename, limit=5):
    """报文件不存在时的兜底：在 workdir 下搜同名文件，返回候选相对路径列表。"""
    if not isinstance(filename, str) or not filename.strip():
        return []
    base = os.path.basename(filename.strip())
    if not base or base in ('.', '..'):
        return []
    wd_abs = os.path.abspath(workdir)
    found = []
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in GREP_SKIP_DIRS]
        for fn in files:
            if fn == base:
                full = os.path.abspath(os.path.join(root, fn))
                try:
                    rel = os.path.relpath(full, wd_abs).replace(os.sep, '/')
                    if any(part in GREP_SKIP_DIRS for part in rel.split('/')):
                        continue
                    found.append(rel)
                    if len(found) >= limit:
                        return found
                except ValueError:
                    continue
    return found


class FileReadTool(BaseTool):
    name = 'file_read'
    label = '读取文件'
    category = '办公'
    description = '读取项目内文本文件的内容（offset=起始行，从1开始，可选；limit=读取行数，可选）'
    usage = 'file_read PARAMS:{"path": "相对路径", "offset": 1, "limit": 200}'
    params_schema = {
        'path': {'type': 'string', 'required': True},
        'offset': {'type': 'integer', 'required': False},
        'limit': {'type': 'integer', 'required': False},
    }

    def run(self, params, ctx):
        path = safe_resolve(ctx.get('workdir'), params.get('path'))
        if not os.path.isfile(path):
            hints = _glob_same_name(ctx.get('workdir'), params.get('path'))
            if hints:
                # 给模型直接可抄的工具指令格式，让它重试时无脑抄
                first_hint = hints[0]
                raise ToolError(
                    f"文件不存在: {params.get('path')}。但找到同名文件: {', '.join(hints)}\n"
                    f"请直接改用下面这条指令重试：\n"
                    f"/$TOOL:file_read PARAMS:{{\"path\": \"{first_hint}\", \"offset\": 1}}"
                )
            raise ToolError(f"文件不存在: {params.get('path')}。建议先用 glob 或 list_dir 定位正确路径")
        size = os.path.getsize(path)
        if size > MAX_READ_CHARS:
            raise ToolError(f"文件过大（{size} 字节，上限 {MAX_READ_CHARS}），请配合 grep_text 定位后用 offset/limit 读取片段")
        with open(path, 'rb') as f:
            raw = f.read()
        if b'\x00' in raw[:4096]:
            raise ToolError("疑似二进制文件，拒绝读取")
        lines = _decode_bytes(raw).splitlines()
        total = len(lines)
        try:
            offset = max(1, int(params.get('offset') or 1))
        except (TypeError, ValueError):
            offset = 1
        try:
            limit = max(1, min(int(params.get('limit') or 400), 800))
        except (TypeError, ValueError):
            limit = 400
        sel = lines[offset - 1: offset - 1 + limit]
        header = f"[file_read] {params.get('path')} 共{total}行，显示第{offset}-{offset - 1 + len(sel)}行\n"
        return truncate_output(header + '\n'.join(sel))


class ListDirTool(BaseTool):
    name = 'list_dir'
    label = '列出目录'
    category = '办公'
    description = '列出项目内某个目录的内容'
    usage = 'list_dir PARAMS:{"path": "目录路径"}'
    params_schema = {
        'path': {'type': 'string', 'required': False},  # 缺省为项目根
    }

    def run(self, params, ctx):
        rel = params.get('path') or '.'
        path = safe_resolve(ctx.get('workdir'), rel)
        if not os.path.isdir(path):
            raise ToolError(f"目录不存在: {rel}")
        try:
            names = sorted(os.listdir(path))[:MAX_LIST_ENTRIES]
        except OSError as e:
            raise ToolError(f"读取目录失败: {e}")
        entries = []
        for name in names:
            full = os.path.join(path, name)
            if os.path.isdir(full):
                entries.append(f"[目录] {name}/")
            else:
                try:
                    entries.append(f"[文件] {name} ({os.path.getsize(full)}B)")
                except OSError:
                    entries.append(f"[文件] {name}")
        header = f"[list_dir] {rel} 共{len(entries)}项\n"
        return truncate_output(header + '\n'.join(entries))


class GlobTool(BaseTool):
    name = 'glob'
    label = '通配符查找'
    category = '检索'
    description = '按通配符模式查找项目内文件'
    usage = 'glob PARAMS:{"pattern": "如 kirara/*.py 或 **/*.html"}'
    params_schema = {
        'pattern': {'type': 'string', 'required': True},
    }

    def run(self, params, ctx):
        pattern = params.get('pattern')
        if not isinstance(pattern, str) or not pattern.strip():
            raise ToolError("pattern 为空")
        pattern = pattern.strip().replace('\\', '/')
        if re.match(r'^[A-Za-z]:', pattern) or pattern.startswith(('..', '/', '~')):
            raise ToolError(f"拒绝越界 pattern: {pattern}")
        wd = ctx.get('workdir')
        matches = globlib.glob(os.path.join(wd, pattern), recursive=True)
        wd_abs = os.path.abspath(wd)
        out = []
        for m in matches:
            if len(out) >= MAX_GLOB_RESULTS:
                break
            m_abs = os.path.abspath(m)
            try:
                if os.path.commonpath([m_abs, wd_abs]) != wd_abs:
                    continue
            except ValueError:
                continue
            rel = os.path.relpath(m_abs, wd_abs)
            if any(part in GREP_SKIP_DIRS for part in rel.split(os.sep)):
                continue
            out.append(rel.replace(os.sep, '/'))
        if not out:
            return f"[glob] 无匹配: {pattern}"
        return truncate_output(f"[glob] {pattern} 共{len(out)}项\n" + '\n'.join(out))


class GrepTool(BaseTool):
    name = 'grep_text'
    label = '内容搜索'
    category = '检索'
    description = '用正则在项目文件内容中搜索'
    usage = 'grep_text PARAMS:{"pattern": "正则表达式", "path": "限定目录或文件(可选)"}'
    params_schema = {
        'pattern': {'type': 'string', 'required': True},
        'path': {'type': 'string', 'required': False},  # 缺省为项目根
    }

    def run(self, params, ctx):
        pat = params.get('pattern')
        if not isinstance(pat, str) or not pat.strip():
            raise ToolError("pattern 为空")
        try:
            rx = re.compile(pat)
        except re.error as e:
            raise ToolError(f"正则无效: {e}")
        base = params.get('path') or '.'
        base_full = safe_resolve(ctx.get('workdir'), base)
        targets = []
        if os.path.isfile(base_full):
            targets.append(base_full)
        else:
            for root, dirs, files in os.walk(base_full):
                dirs[:] = [d for d in dirs if d not in GREP_SKIP_DIRS]
                for fn in files:
                    targets.append(os.path.join(root, fn))
                    if len(targets) >= MAX_GREP_FILES:
                        break
                if len(targets) >= MAX_GREP_FILES:
                    break
        matches = []
        scanned = 0
        wd = ctx.get('workdir')
        for fp in targets:
            if len(matches) >= MAX_GREP_MATCHES:
                break
            try:
                if os.path.getsize(fp) > MAX_GREP_FILE_SIZE:
                    continue
                with open(fp, 'rb') as f:
                    raw = f.read()
            except OSError:
                continue
            if b'\x00' in raw[:4096]:
                continue
            scanned += 1
            text = _decode_bytes(raw)
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    rel = os.path.relpath(fp, wd).replace(os.sep, '/')
                    matches.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(matches) >= MAX_GREP_MATCHES:
                        break
        if not matches:
            return f"[grep_text] 无匹配: {pat}（扫描 {scanned} 个文件）"
        header = f"[grep_text] {pat} 共{len(matches)}处命中\n"
        return truncate_output(header + '\n'.join(matches))


class WebSearchTool(BaseTool):
    """兼容别名：不再直接 import skills/noic.webSearch 的代码。

    实际实现只保留 MOD 方块 `webSearch` 一份；本方块只负责把调用转发到方块注册表，
    因此同样受装备门禁与执行路径约束。保留别名是为了不打断旧实例里名为
    `web_search` 的装备记录。
    """

    name = 'web_search'
    label = '网络搜索（兼容别名）'
    category = '检索'
    description = '联网搜索关键词（兼容别名，实际调用 webSearch 方块；需安装并启用 noic.webSearch）'
    usage = 'web_search PARAMS:{"query": "关键词", "max_results": 5}'
    params_schema = {
        'query': {'type': 'string', 'required': True},
        'max_results': {'type': 'integer', 'required': False},
    }

    def run(self, params, ctx):
        query = params.get('query')
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query 为空")
        try:
            max_results = min(8, max(1, int(params.get('max_results') or 5)))
        except (TypeError, ValueError):
            max_results = 5

        # 唯一入口：内层 webSearch 方块可能尚未注册（MOD 未安装/未加载），交给注册表判定
        resp = invoke_block(
            'webSearch',
            {'action': 'search', 'query': query.strip(), 'max_results': max_results},
            ctx=ctx,
        )
        if not resp.get('ok'):
            raise ToolError(
                'web_search 不可用：%s。请确认 noic.webSearch 已安装并启用后重试。'
                % resp.get('error', '未知原因')
            )
        output = resp.get('output')
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


# 写操作额外保护的相对路径（相对 workdir）；命中即拒，避免智能体篡改自身运行态/记忆底座
WRITE_PROTECTED_REL = {
    'data/agent_runs',   # 审批挂起态目录，防自我放行
}


def _check_write_guard(full_path, workdir):
    """写工具二次校验：路径不得落入受保护目录（fail-closed）。"""
    try:
        rel = os.path.relpath(full_path, workdir).replace(os.sep, '/')
    except ValueError:
        return
    rel_dir = os.path.dirname(rel)
    parts = rel_dir.split('/') if rel_dir else []
    # 逐级拼接，检查任一前缀是否受保护
    prefix = ''
    for p in parts:
        prefix = p if not prefix else prefix + '/' + p
        if prefix in WRITE_PROTECTED_REL:
            raise ToolError(f"该路径受写保护，拒绝写入: {rel}")


class FileWriteTool(BaseTool):
    name = 'file_write'
    label = '写入文件'
    category = '办公'
    description = '向项目内文本文件写入内容（覆盖或新建，需审批）'
    risk = 'write'
    usage = 'file_write PARAMS:{"path": "相对路径", "content": "文件全文内容", "append": false(可选,默认覆盖)}'
    params_schema = {
        'path': {'type': 'string', 'required': True},
        'content': {'type': 'string', 'required': True},
        'append': {'type': 'boolean', 'required': False},
    }

    def run(self, params, ctx):
        workdir = ctx.get('workdir')
        rel = params.get('path')
        content = params.get('content')
        if not isinstance(rel, str) or not rel.strip():
            raise ToolError("path 为空")
        if not isinstance(content, str):
            raise ToolError("content 必须为字符串")
        if len(content) > MAX_WRITE_CHARS:
            raise ToolError(f"内容过大（{len(content)} 字符，上限 {MAX_WRITE_CHARS}），请分次写入或改用 file_edit 局部修改")
        try:
            append = bool(params.get('append', False))
        except Exception:
            append = False
        full = safe_resolve(workdir, rel)
        _check_write_guard(full, workdir)
        # 不允许覆盖受保护路径下的现有文件（如 options.json）？审批流已把关，此处不额外限制
        mode = 'a' if append else 'w'
        encoding = 'utf-8'
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True) if os.path.dirname(full) else None
            with open(full, mode, encoding=encoding, newline='') as f:
                f.write(content)
        except OSError as e:
            raise ToolError(f"写入失败: {e}")
        action = '追加' if append else '写入'
        size = os.path.getsize(full)
        return truncate_output(f"[file_write] {action}完成: {rel}（{len(content)} 字符，现 {size} 字节）")


class FileEditTool(BaseTool):
    name = 'file_edit'
    label = '局部编辑'
    category = '代码'
    description = '对项目内文本文件做精确字符串替换（需审批）'
    risk = 'write'
    usage = 'file_edit PARAMS:{"path": "相对路径", "old_string": "要替换的原文", "new_string": "新文本", "replace_all": false(可选)}'
    params_schema = {
        'path': {'type': 'string', 'required': True},
        'old_string': {'type': 'string', 'required': True},
        'new_string': {'type': 'string', 'required': True},
        'replace_all': {'type': 'boolean', 'required': False},
    }

    def run(self, params, ctx):
        workdir = ctx.get('workdir')
        rel = params.get('path')
        old = params.get('old_string')
        new = params.get('new_string')
        if not isinstance(rel, str) or not rel.strip():
            raise ToolError("path 为空")
        if not isinstance(old, str) or not old:
            raise ToolError("old_string 为空")
        if not isinstance(new, str):
            raise ToolError("new_string 必须为字符串")
        if len(old) > MAX_WRITE_CHARS or len(new) > MAX_WRITE_CHARS:
            raise ToolError("编辑片段过大，请缩小替换范围")
        full = safe_resolve(workdir, rel)
        _check_write_guard(full, workdir)
        if not os.path.isfile(full):
            hints = _glob_same_name(workdir, rel)
            if hints:
                raise ToolError(f"文件不存在: {rel}。但找到同名文件: {', '.join(hints)}")
            raise ToolError(f"文件不存在: {rel}。建议先用 glob 或 list_dir 定位正确路径")
        size = os.path.getsize(full)
        if size > MAX_READ_CHARS:
            raise ToolError(f"文件过大（{size} 字节），请先用 file_read 片段读取后精确编辑")
        try:
            with open(full, 'rb') as f:
                raw = f.read()
        except OSError as e:
            raise ToolError(f"读取失败: {e}")
        if b'\x00' in raw[:4096]:
            raise ToolError("疑似二进制文件，拒绝编辑")
        text = _decode_bytes(raw)
        try:
            replace_all = bool(params.get('replace_all', False))
        except Exception:
            replace_all = False
        count = text.count(old)
        if count == 0:
            raise ToolError(f"未找到要替换的原文（请确认 old_string 与文件内容完全一致，含缩进/换行）")
        if count > 1 and not replace_all:
            raise ToolError(f"原文在文件中出现 {count} 次，需明确 replace_all=true 或提供更长的唯一上下文")
        if replace_all:
            new_text = text.replace(old, new)
        else:
            new_text = text.replace(old, new, 1)
        try:
            with open(full, 'w', encoding='utf-8', newline='') as f:
                f.write(new_text)
        except OSError as e:
            raise ToolError(f"写回失败: {e}")
        return truncate_output(
            f"[file_edit] 完成: {rel}（替换 {count if replace_all else 1} 处，"
            f"文件 {size} → {os.path.getsize(full)} 字节）"
        )


def _kill_process_tree(proc):
    """终止子进程及其后代（Windows 用 taskkill /T 杀进程树；POSIX 杀进程组）。"""
    pid = getattr(proc, 'pid', None)
    if pid is None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)],
                           capture_output=True, timeout=5)
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


class ShellTool(BaseTool):
    """shell 命令执行（dangerous 级）：默认关闭、黑名单、超时杀进程树、cwd 限定、可被 abort 即时终止。"""
    name = 'shell'
    label = '执行命令'
    category = '代码'
    description = '在项目根目录执行一条 shell 命令（Windows cmd，危险操作需审批；timeout 为超时秒数，可选，默认 10，上限 30）'
    risk = 'dangerous'
    usage = 'shell PARAMS:{"command": "命令行", "timeout": 10}'
    params_schema = {
        'command': {'type': 'string', 'required': True},
        'timeout': {'type': 'integer', 'required': False},
    }

    def meta(self):
        m = super().meta()
        m['enabled'] = _shell_config['enabled']
        return m

    def run(self, params, ctx):
        # 第一道闸门：未启用直接拒绝（fail-closed；即使模型幻觉出 shell 调用也不执行）
        if not _shell_config['enabled']:
            raise ToolError('shell 工具未启用（设置中 agent_shell_enabled=false，拒绝执行命令）')
        command = params.get('command')
        if not isinstance(command, str) or not command.strip():
            raise ToolError('command 为空')
        command = command.strip()
        if len(command) > MAX_SHELL_CMD_CHARS:
            raise ToolError(f'命令过长（{len(command)} 字符，上限 {MAX_SHELL_CMD_CHARS}）')

        # 黑名单
        for rx, reason in SHELL_BLACKLIST:
            if rx.search(command):
                raise ToolError(f'命令命中黑名单（{reason}），拒绝执行: {command}')
        # cwd 限定：拒绝任何 .. 路径穿越
        if SHELL_TRAVERSAL_RE.search(command):
            raise ToolError(f'命令包含 .. 路径穿越，禁止跳出项目根目录: {command}')

        # 超时：模型传参封顶 MAX_SHELL_TIMEOUT，缺省用配置
        try:
            timeout = int(params.get('timeout') or ctx.get('shell_timeout') or _shell_config['timeout'])
        except (TypeError, ValueError):
            timeout = _shell_config['timeout']
        timeout = max(1, min(timeout, MAX_SHELL_TIMEOUT))

        workdir = ctx.get('workdir')
        abort_event = ctx.get('abort_event')
        popen_kwargs = dict(
            shell=True,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if os.name == 'nt':
            # 独立进程组，taskkill /T 才能整树终止
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs['start_new_session'] = True

        started = time.monotonic()
        try:
            proc = subprocess.Popen(command, **popen_kwargs)
        except OSError as e:
            raise ToolError(f'命令启动失败: {e}')

        deadline = started + timeout
        timed_out = False
        aborted = False
        raw = b''
        while True:
            # abort 即时生效：不等超时，立刻杀进程树
            if abort_event is not None and abort_event.is_set():
                _kill_process_tree(proc)
                try:
                    raw, _ = proc.communicate(timeout=2)
                except Exception:
                    raw = b''
                aborted = True
                break
            try:
                raw, _ = proc.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    _kill_process_tree(proc)
                    try:
                        raw, _ = proc.communicate(timeout=2)
                    except Exception:
                        raw = b''
                    timed_out = True
                    break

        elapsed = time.monotonic() - started
        if aborted:
            raise ToolError(f'任务已中止，命令进程已终止（已运行 {elapsed:.1f}s）: {command}')
        output = _decode_bytes(raw or b'')
        header = f"[shell] {command}\n退出码 {proc.returncode}，用时 {elapsed:.1f}s，cwd=项目根\n"
        if timed_out:
            tail = truncate_output(output)
            raise ToolError(
                f'命令超时（>{timeout}s），进程树已被强制终止。\n{header}{tail}'
            )
        return truncate_output(header + output)


class BlockRegistry:
    """方块注册表（类似 Minecraft Block.REGISTRY）。

    同时持有：
    - 引擎内建方块（FileReadTool、GlobTool 等硬编码注册，不可移除）
    - skill MOD 注册的可插拔方块（运行时挂载，可被禁用）

    统一通过 get_block() / list_blocks() 消费，调用方不感知方块来源。
    """

    def __init__(self):
        self._blocks = {}           # name -> BaseTool 实例
        self._builtin = frozenset()  # 内建方块名集合（不可移除）
        self._ci = {}               # 小写名 -> canonical 名（大小写不敏感查找）

    def register(self, block, builtin=True):
        """注册一个方块。builtin=True 表示引擎内建，不可被 MOD 覆盖。"""
        name = getattr(block, 'name', None)
        if not name:
            raise ValueError("方块缺少 name 属性")
        key = name.lower()
        canonical = self._ci.get(key, name)
        if not builtin and canonical in self._builtin:
            raise ValueError(f"skill MOD 不能覆盖引擎内建方块: {name}")
        if canonical != name:
            # 仅大小写不同的重名：以新注册为准，清掉旧条目，避免索引歧义
            self._blocks.pop(canonical, None)
            self._builtin = frozenset(set(self._builtin) - {canonical})
        self._blocks[name] = block
        self._ci[key] = name
        if builtin:
            self._builtin = frozenset(set(self._builtin) | {name})
        return block

    def register_external(self, block):
        """skill MOD 注册可插拔方块（等同 register(block, builtin=False)）。"""
        return self.register(block, builtin=False)

    def unregister(self, name):
        """移除一个可插拔方块；引擎内建方块拒绝移除。"""
        canonical = self._ci.get(name.lower(), name)
        if canonical in self._builtin:
            raise ValueError(f"引擎内建方块不可移除: {name}")
        self._blocks.pop(canonical, None)
        self._ci.pop(canonical.lower(), None)

    def get(self, name):
        """按名取方块；大小写不敏感（模型可能照抄 prompt 里的大小写，也可能自己改写）。"""
        if not isinstance(name, str):
            return None
        block = self._blocks.get(name)
        if block is not None:
            return block
        canonical = self._ci.get(name.lower())
        return self._blocks.get(canonical) if canonical else None

    def has(self, name):
        return self.get(name) is not None

    def list_all(self):
        """返回全部已注册方块（内建 + 可插拔），按内建优先、字母序。"""
        builtin = [(n, self._blocks[n]) for n in sorted(self._builtin)]
        external = sorted(
            [(n, b) for n, b in self._blocks.items() if n not in self._builtin],
            key=lambda x: x[0]
        )
        return [b for _, b in builtin + external]

    def is_builtin(self, name):
        canonical = self._ci.get(name.lower(), name) if isinstance(name, str) else name
        return canonical in self._builtin

    def __contains__(self, name):
        return self.has(name)

    def __iter__(self):
        return iter(self.list_all())


# ---------- 全局单例 ----------
BLOCK_REGISTRY = BlockRegistry()


class RealityCheckTool(BaseTool):
    """运行时内置：输出侧现实审视（不可被 MOD 停用）。"""

    name = 'realityCheck'
    label = '现实审视'
    category = 'CoT'
    description = '检测文本中的偏见/仇恨/暴力/心理伤害内容；命中时返回自省提示'
    risk = 'read'
    usage = 'realityCheck PARAMS:{"text": "<要检测的文本>"}'
    params_schema = {
        'text': {'type': 'string', 'required': True},
    }

    def run(self, params, ctx):
        text = params.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ToolError('text 为空')
        return reality_check(text)


class AreYouUnderTroubleTool(BaseTool):
    """运行时内置：输入侧危机信号识别与应急建议（不可被 MOD 停用）。"""

    name = 'areYouUnderTrouble'
    label = '危机支持'
    category = 'CoT'
    description = '察觉情绪低落或处境艰难的信号，给出温和的陪伴式支持建议与可用的求助渠道'
    risk = 'read'
    usage = ('areYouUnderTrouble PARAMS:{"query": "<用户输入>", '
             '"user_location": "中国", "user_contact": ""}')
    params_schema = {
        'query': {'type': 'string', 'required': True},
        'user_location': {'type': 'string', 'required': False},
        'user_contact': {'type': 'string', 'required': False},
    }

    def run(self, params, ctx):
        query = params.get('query')
        if not isinstance(query, str) or not query.strip():
            raise ToolError('query 为空')
        return analyze_crisis(
            query,
            params.get('user_location') or '中国',
            params.get('user_contact') or '',
        )

class AutomationTool(BaseTool):
    """查看本体自动化调度状态（只读）：flow 清单与最近运行记录。"""

    name = 'automation'
    label = '自动化调度'
    category = '自动化'
    description = '查看已注册的自动化 flow 与最近运行记录（触发请用 automation_trigger，写级需审批）'
    risk = 'read'
    usage = ('automation PARAMS:{"action": "list"} 或 '
             'automation PARAMS:{"action": "runs", "limit": 5}')
    params_schema = {
        'action': {'type': 'string', 'required': False},  # 缺省/空串等同 list
        'limit': {'type': 'integer', 'required': False},  # runs 时缺省 5
    }

    def run(self, params, ctx):
        from simchat.automation import get_engine

        engine = get_engine()
        if engine is None:
            raise ToolError('自动化引擎未启动，当前无法查询调度状态')
        action = str(params.get('action') or 'list').strip().lower()
        if action in ('list', 'flows'):
            flows = engine.list_flows()
            if not flows:
                return '当前没有已注册的自动化 flow。'
            lines = ['已注册 flow（%d 个）：' % len(flows)]
            for item in flows:
                lines.append('- %s | mod=%s | trigger=%s | next_run=%s' % (
                    item.get('flow_id'), item.get('mod_id'), item.get('trigger_type'),
                    item.get('next_run') or '-'))
            lines.append('触发：/$TOOL:automation_trigger PARAMS:{"flow_id": "<id>"}（写级，需审批）')
            return '\n'.join(lines)
        if action == 'runs':
            runs = engine.list_runs(int(params.get('limit') or 5))
            if not runs:
                return '还没有运行记录。'
            lines = ['最近运行（%d 条）：' % len(runs)]
            for run in runs:
                lines.append('- %s | %s | %s | %s | %sms%s' % (
                    run.get('run_id'), run.get('flow_id'), run.get('triggered_by'),
                    run.get('status'), run.get('duration_ms', '-'),
                    (' | ' + str(run['error'])) if run.get('error') else ''))
            return '\n'.join(lines)
        if action == 'trigger':
            raise ToolError('trigger 属写级操作，请改用 /$TOOL:automation_trigger '
                            'PARAMS:{"flow_id": "..."}（会走审批）')
        raise ToolError('未知 action: %s（可用: list / runs）' % action)


class AutomationTriggerTool(BaseTool):
    """立即触发一个已注册的 flow（写级，走审批）。"""

    name = 'automation_trigger'
    label = '触发自动化'
    category = '自动化'
    description = '按 flow id 立即触发一次自动化执行（写级，需用户审批）'
    risk = 'write'
    usage = 'automation_trigger PARAMS:{"flow_id": "daily.workspace.digest"}'
    params_schema = {
        'flow_id': {'type': 'string', 'required': True},
    }

    def run(self, params, ctx):
        from simchat.automation import get_engine

        flow_id = str(params.get('flow_id') or '').strip()
        if not flow_id:
            raise ToolError('缺少 flow_id（先用 /$TOOL:automation PARAMS:{"action": "list"} 查看）')
        engine = get_engine()
        if engine is None:
            raise ToolError('自动化引擎未启动，无法触发')
        summary = engine.trigger_flow(
            flow_id, triggered_by='tool',
            allowed=(ctx or {}).get('allowed'),
        )
        if not summary.get('ok'):
            raise ToolError(summary.get('error') or ('flow 执行未成功: %s' % summary.get('status')))
        return json.dumps(summary, ensure_ascii=False)


# 向后兼容别名：旧代码用 TOOL_REGISTRY，新代码用 BLOCK_REGISTRY
# 旧的 list_agent_tools() / build_tool_protocol_section() 保持不动，
# 内部用 BLOCK_REGISTRY.list_all() 替代 TOOL_REGISTRY.values()


def _register_builtin(tool):
    """注册引擎内建方块（硬编码，不可移除）。"""
    return BLOCK_REGISTRY.register(tool, builtin=True)


# ---- Orbiter：宿主侧编排方块 ----
# 命令契约来自 jrvs-orbiter 的 README 原案：
#   简单问题由本地模型直接答；复杂任务由本地模型润色后输出
#   /@<模型名> -prompt "..." 或 /$ <命令> -dir "..."，宿主解析并派发。
# 云端只收到工程化简报；未知模型 id 明确报错，不静默失败。

ORBITER_DEFAULT_TARGET_MODEL = "qwen4-max"
ORBITER_TARGET_CANDIDATES = ("qwen4-max", "qwen3.8-max", "deepseek-v4-pro")
ORBITER_CONTRACT_PATH = os.path.join(PROJECT_ROOT, "jrvs-orbiter", "prompts", "system.txt")
ORBITER_IMAGE_MODES = ("image", "img", "picture", "draw", "t2i")

_ORBITER_CORE = None


def configure_orbiter(core):
    """由 Web 启动时注入宿主 Core；未注入时按默认 data 目录懒加载。"""
    global _ORBITER_CORE
    _ORBITER_CORE = core


def _orbiter_core():
    global _ORBITER_CORE
    if _ORBITER_CORE is None:
        from ..core import SimChatCore
        _ORBITER_CORE = SimChatCore()
    return _ORBITER_CORE


def _orbiter_contract(core, target_model):
    """本地分诊用的系统提示：README 契约 + 宿主侧的真实边界。"""
    text = ""
    try:
        with open(ORBITER_CONTRACT_PATH, "r", encoding="utf-8") as handle:
            text = handle.read().strip()
    except Exception:
        text = ""
    if not text:
        text = (
            "先分诊：简单问题直接回答；只有复杂任务、且确实需要别的 AI 或技能时才委派。\n"
            "无参数委派：/@<模型名> -prompt \"<工程化任务简报>\"\n"
            "带参数委派：第一行 /@<模型名> -键=值，第二行起写自然语言 spec\n"
            "调用技能：/$ <命令> -dir \"<目录>\"\n"
        )
    candidates = []
    for name in (target_model,) + ORBITER_TARGET_CANDIDATES:
        name = str(name or "").strip()
        if name and name not in candidates:
            candidates.append(name)
    text += (
        "\n[宿主 Orbiter 约束]\n"
        "- 可委派的模型 id 只能从以下列表选择：%s。\n"
        "- 分诊规则：日常问答、事实查询、简单计算直接回答；"
        "设计、实现、分析、对比、写作、方案、排查、多步骤任务必须委派，禁止本地直接作答。\n"
        "- 委派内容必须是工程化任务简报（目标、已知背景、约束与边界、期望交付物、验收标准），"
        "不能只复制用户原话；只能使用用户提供的事实，缺失信息写“待确认”。\n"
        "- 委派示例：/@qwen4-max -prompt \"目标：…；背景：…；约束：…；交付物：…；验收：…\"\n"
        "- 图像生成、AWS/AutoDL 远程实例、单租户虚拟化、JRVS-390B 都尚未接入，属于规划；"
        "遇到这类需求直接如实说明，不要编造 /@ 指令。\n"
    ) % "、".join(candidates)
    return text


def _parse_orbiter_flags(text):
    """解析 -key=value / -key "value" / -key value，返回 (flags, 剩余文本)。"""
    flags = {}
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length or text[index] != '-':
            break
        start = index + 1
        end = start
        while end < length and (text[end].isalnum() or text[end] in '_-'):
            end += 1
        if end == start:
            break
        key = text[start:end].lower()
        cursor = end
        while cursor < length and text[cursor].isspace():
            cursor += 1
        if cursor < length and text[cursor] == '=':
            cursor += 1
            while cursor < length and text[cursor].isspace():
                cursor += 1
        value = ""
        if cursor < length and text[cursor] in ('"', "'"):
            quote = text[cursor]
            closing = text.find(quote, cursor + 1)
            if closing == -1:
                value = text[cursor + 1:]
                cursor = length
            else:
                value = text[cursor + 1:closing]
                cursor = closing + 1
        else:
            match = re.match(r'\S+', text[cursor:])
            if match:
                value = match.group(0)
                cursor += match.end()
        flags[key] = value
        index = cursor
    return flags, text[index:].strip()


def _coerce_orbiter_param(value, expected):
    """命令行参数都是字符串，按方块声明的类型做最小转换。"""
    expected = (expected or "").strip().lower() if isinstance(expected, str) else ""
    if expected in ("integer", "number"):
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
    if expected == "boolean":
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if expected in ("object", "array"):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


class OrbiterTool(BaseTool):
    name = 'orbiter'
    label = 'Orbiter 编排'
    category = '编排'
    risk = 'write'
    description = (
        '按 Orbiter 契约分诊：简单问题由本地 JRVS 直接回答；复杂任务先在本地润色并生成 '
        '/@<模型名> 或 /$ <命令> 委派指令，由宿主解析后派发。云端只收到工程化简报；'
        '本地不可用时 fail-closed，未知模型 id 明确报错。'
    )
    usage = (
        'orbiter PARAMS:{"request": "用户原话", "context": "可选上下文", '
        '"target_model": "可选默认委派模型", "max_tokens": 4096}'
    )
    params_schema = {
        'request': {'type': 'string', 'required': True},
        'context': {'type': 'string', 'required': False},
        'target_model': {'type': 'string', 'required': False},
        'max_tokens': {'type': 'integer', 'required': False},
    }

    _ANSWER_SYSTEM = (
        '你是一名严谨的执行助手。请根据任务简报给出可执行、结构清晰的回答；'
        '不要复述简报，不要提及“简报”或“编排”过程。'
    )

    # 本地模型偶尔会跳过委派直接作答；用保守启发式兜底，保证复杂任务一定被派发。
    _TASK_HINTS = (
        '写', '生成', '实现', '分析', '对比', '设计', '规划', '重构', '修复', '排查',
        '总结', '报告', '方案', '代码', '脚本', '文档', '表格', '调研', '研究',
        '翻译', '优化', '部署', '测试', '做一个', '帮我做', '整理',
    )
    _MULTI_STEP_RE = re.compile(r'(先.{0,12}再|第一步|步骤[一二三四1234]|端到端|详细|深入|框架|架构)', re.S)

    def _looks_complex(self, request, context):
        text = request.strip()
        if len(text) > 120:
            return True, '请求较长（%d 字）' % len(text)
        if context and len(context.strip()) > 200:
            return True, '附带了较长上下文'
        match = self._MULTI_STEP_RE.search(text)
        if match:
            return True, '出现多步骤/深入分析信号：%s' % match.group(1)
        for hint in self._TASK_HINTS:
            if hint in text:
                return True, '出现任务型动词：%s' % hint
        return False, '短问答，无任务型动词'

    def _target_model(self, core, params):
        explicit = str(params.get('target_model') or '').strip()
        if explicit:
            return explicit
        orbiter_cfg = (core.config or {}).get('orbiter') or {}
        configured = str(orbiter_cfg.get('target_model') or '').strip()
        return configured or ORBITER_DEFAULT_TARGET_MODEL

    def run(self, params, ctx):
        request = str(params.get('request') or '').strip()
        if not request:
            raise ToolError('orbiter 需要 request（用户原话），不能为空')

        context = str(params.get('context') or '').strip()
        core = _orbiter_core()
        target_model = self._target_model(core, params)

        # 分诊与润色都只允许本地模型；不可用则 fail-closed，原始请求不上云
        ollama_id, ollama_error = core.resolve_provider('ollama')
        if ollama_error or not ollama_id:
            raise ToolError(
                '本地 JRVS/Ollama 不可用，orbiter 已 fail-closed；'
                '原始请求没有发送到云端。原因: %s' % (ollama_error or 'ollama 未就绪')
            )

        ollama_cfg = (core.config or {}).get('ollama') or {}
        local_model = str(ollama_cfg.get('model') or '').strip() or None
        local_input = '用户请求：\n%s' % request
        if context:
            local_input += '\n\n可用上下文：\n%s' % context

        try:
            decision = core.generate(
                local_input,
                system_msg=_orbiter_contract(core, target_model),
                provider='ollama',
                model=local_model,
                max_tokens=1024,
                temperature=0.3,
            )
        except Exception as exc:
            raise ToolError(
                '本地 JRVS 分诊/润色失败，已终止；原始请求没有发送到云端。原因: %s: %s'
                % (type(exc).__name__, exc)
            )
        decision = str(decision or '').strip()
        if not decision:
            raise ToolError('本地 JRVS 返回为空，已终止；原始请求没有发送到云端。')

        delegation = self._find_delegation(decision)
        if delegation is not None:
            lines, index = delegation
            if lines[index].strip().startswith('/@'):
                return self._delegate_model(lines, index, core, params)
            return self._delegate_skill(lines, index, ctx)

        # 本地模型漏掉委派时兜底：复杂任务再催一次，仍失败就明确报错，不上云
        is_complex, reason = self._looks_complex(request, context)
        if is_complex:
            try:
                forced = self._force_delegation(core, local_model, local_input, target_model)
            except Exception as exc:
                raise ToolError(
                    '本地 JRVS 生成委派指令失败，已终止；原始请求没有发送到云端。原因: %s: %s'
                    % (type(exc).__name__, exc)
                )
            delegation = self._find_delegation(forced)
            if delegation is not None:
                lines, index = delegation
                if lines[index].strip().startswith('/@'):
                    return self._delegate_model(lines, index, core, params)
                return self._delegate_skill(lines, index, ctx)
            raise ToolError(
                '本地模型未能按契约生成委派指令（判定依据：%s），已终止；'
                '原始请求没有发送到云端。' % reason
            )

        return {
            'path': 'direct',
            'answer': decision,
            'provider': 'ollama',
            'model': local_model or '',
        }

    @staticmethod
    def _find_delegation(text):
        """找出第一条委派指令（优先行首；容忍“好的，先生。”这类短前缀）。"""
        lines = str(text or '').splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('/@') or stripped.startswith('/$'):
                return lines, index
            positions = [pos for pos in (stripped.find('/@'), stripped.find('/$')) if pos > 0]
            if positions:
                pos = min(positions)
                prefix = stripped[:pos].strip()
                if len(prefix) <= 40 and '`' not in prefix and '"' not in prefix:
                    lines[index] = stripped[pos:]
                    return lines, index
        return None

    def _force_delegation(self, core, local_model, local_input, target_model):
        """复杂任务被本地模型直接作答时，再要求它只输出委派指令。"""
        prompt = (
            local_input
            + '\n\n[强制格式] 这个任务属于复杂任务，必须委派，不能本地直接作答。'
            '只输出一行委派指令：/@<模型名> -prompt "<工程化任务简报>"，'
            '不要回答问题，不要解释，不要加任何前后缀。'
            '简报只能包含用户请求里已有的信息；用户没提过的背景、SDK、库、数字一律写“待确认”，'
            '不得自行补充或猜测。'
        )
        return core.generate(
            prompt,
            system_msg=_orbiter_contract(core, target_model),
            provider='ollama',
            model=local_model,
            max_tokens=1024,
            temperature=0.2,
        )

    def _delegate_model(self, lines, index, core, params):
        head = lines[index].strip()[2:]
        parts = head.split(None, 1)
        model_name = parts[0].strip() if parts else ''
        if not model_name:
            raise ToolError('委派指令缺少模型名：/@ 后必须跟模型 id')
        remainder = parts[1] if len(parts) > 1 else ''
        flags, inline = _parse_orbiter_flags(remainder)
        extra = '\n'.join(lines[index + 1:]).strip()
        if flags.get('prompt'):
            task = flags['prompt'].strip()
            if extra:
                task = (task + '\n' + extra).strip()
        else:
            task = (inline + ('\n' + extra if extra else '')).strip()
        if not task:
            raise ToolError('委派指令缺少任务内容：请用 -prompt "..." 或下一行写任务简报')

        mode = str(flags.get('mode') or '').strip().lower()
        from .. import provider_config

        conf = (core.config or {}).get('openai_compat') or {}
        _vendor_id, _vendor = provider_config._vendor_meta('openai_compat', conf)
        models, discover_error = provider_config._openai_models(
            conf.get('api_base'), conf.get('api_key'), timeout=5,
            headers=provider_config._openai_headers(_vendor, conf, conf.get('api_key') or ''),
            query=provider_config._openai_query(conf),
        )
        if discover_error:
            raise ToolError(
                '无法校验委派模型 %s（模型列表探测失败：%s）' % (model_name, discover_error)
            )
        if model_name not in models:
            suggest = [name for name in ORBITER_TARGET_CANDIDATES if name in models]
            for name in models:
                if len(suggest) >= 8:
                    break
                if name in suggest:
                    continue
                low = name.lower()
                if any(token in low for token in
                       ('speech', 'audio', 'tts', 'asr', 'image', 'video', 'embed', 'rerank')):
                    continue
                suggest.append(name)
            hint = '、'.join(suggest) if suggest else '无'
            extra_hint = '；另外图像生成尚未接入（规划中）' if mode in ORBITER_IMAGE_MODES else ''
            raise ToolError(
                '模型不存在: %s（未在云端模型清单中）。可用示例: %s%s'
                % (model_name, hint, extra_hint)
            )
        if mode in ORBITER_IMAGE_MODES:
            raise ToolError(
                '图像生成尚未接入（规划中）：宿主没有图像端点，模型 %s 不会被调用' % model_name
            )

        try:
            budget = int(params.get('max_tokens') or 0)
        except (TypeError, ValueError):
            budget = 0
        if budget <= 0:
            budget = 4096
        budget = max(256, min(budget, 8192))

        def _call(tokens):
            return core.generate(
                task,
                system_msg=self._ANSWER_SYSTEM,
                provider='openai_compat',
                model=model_name,
                max_tokens=tokens,
                temperature=0.6,
            )

        try:
            answer = _call(budget)
        except Exception as exc:
            if '模型返回为空' in str(exc) and budget < 8192:
                try:
                    answer = _call(8192)
                except Exception as retry_error:
                    raise ToolError(
                        '云端回答失败（润色已完成，但结果未回收）：%s: %s'
                        % (type(retry_error).__name__, retry_error)
                    )
            else:
                raise ToolError(
                    '云端回答失败（润色已完成，但结果未回收）：%s: %s'
                    % (type(exc).__name__, exc)
                )
        return {
            'path': 'delegate',
            'model': model_name,
            'mode': mode or 'text',
            'brief': task,
            'answer': answer,
            'delegation': lines[index].strip(),
        }

    def _delegate_skill(self, lines, index, ctx):
        head = lines[index].strip()[2:]
        parts = head.split(None, 1)
        command = parts[0].strip() if parts else ''
        if not command:
            raise ToolError('技能委派缺少命令名：/$ 后必须跟方块名')
        remainder = parts[1] if len(parts) > 1 else ''
        flags, inline = _parse_orbiter_flags(remainder)
        extra = '\n'.join(lines[index + 1:]).strip()
        spec = (inline + ('\n' + extra if extra else '')).strip()

        block = BLOCK_REGISTRY.get(command)
        if block is None:
            names = ', '.join(sorted(item.name for item in BLOCK_REGISTRY.list_all()))
            raise ToolError('技能不存在: %s（可用方块: %s）' % (command, names))

        fields = _normalize_param_schema(getattr(block, 'params_schema', {}))
        run_params = {}
        for key, value in flags.items():
            if key == 'dir':
                continue
            if fields and key not in fields:
                raise ToolError(
                    '技能 %s 不支持参数 -%s（支持: %s）'
                    % (block.name, key, ', '.join(fields))
                )
            run_params[key] = _coerce_orbiter_param(value, (fields.get(key) or {}).get('type'))

        workdir = (ctx or {}).get('workdir') or PROJECT_ROOT
        if flags.get('dir'):
            workdir = resolve_workdir(flags['dir'])
        if spec:
            key = next(
                (name for name in ('path', 'query', 'request', 'prompt', 'text', 'content', 'command')
                 if name in fields and name not in run_params),
                None,
            )
            if key:
                run_params[key] = spec
            elif not run_params:
                raise ToolError(
                    '技能 %s 需要参数，请在命令后用 -键=值 指定（支持: %s）'
                    % (block.name, ', '.join(fields) or '无')
                )

        allowed = (ctx or {}).get('allowed')
        result = invoke_block(
            block.name, run_params, {'workdir': workdir, 'allowed': allowed},
            allowed=allowed, approved=False,
        )
        if not result.get('ok'):
            raise ToolError(
                '技能 %s 执行失败：%s' % (block.name, result.get('error') or '未知错误')
            )
        return {
            'path': 'skill',
            'command': block.name,
            'params': run_params,
            'answer': result.get('output'),
        }


_register_builtin(OrbiterTool())
_register_builtin(FileReadTool())
_register_builtin(ListDirTool())
_register_builtin(GlobTool())
_register_builtin(GrepTool())
_register_builtin(WebSearchTool())
_register_builtin(FileWriteTool())
_register_builtin(FileEditTool())
_register_builtin(ShellTool())
# 安全能力硬编码进运行时，不依赖 MOD 加载
_register_builtin(RealityCheckTool())
_register_builtin(AreYouUnderTroubleTool())
_register_builtin(AutomationTool())
_register_builtin(AutomationTriggerTool())


# 向后兼容：旧代码仍可 import TOOL_REGISTRY
class _RegistryCompat:
    """让 TOOL_REGISTRY dict-like 访问兼容旧代码。"""

    def __iter__(self):
        return iter(BLOCK_REGISTRY.list_all())

    def __contains__(self, name):
        return BLOCK_REGISTRY.has(name)

    def __getitem__(self, name):
        block = BLOCK_REGISTRY.get(name)
        if block is None:
            raise KeyError(name)
        return block

    def get(self, name, default=None):
        return BLOCK_REGISTRY.get(name) or default

    def values(self):
        return list(BLOCK_REGISTRY.list_all())

    def keys(self):
        return [b.name for b in BLOCK_REGISTRY.list_all()]

    def items(self):
        return [(b.name, b) for b in BLOCK_REGISTRY.list_all()]


TOOL_REGISTRY = _RegistryCompat()  # noqa: F841 — 向后兼容别名，保持 loop.py 等旧代码可 import


class ModToolBlock(BaseTool):
    """把已加载 MOD 注册的工具包装成引擎方块，统一经 BLOCK_REGISTRY 调用。"""

    source = 'mod'

    def __init__(self, loader, spec, mod_id):
        spec = spec or {}
        self._loader = loader
        self._mod_id = mod_id
        self.name = spec.get('name') or ''
        self.label = spec.get('label') or self.name
        self.description = spec.get('description') or ''
        self.risk = spec.get('risk') or 'read'
        self.usage = spec.get('usage') or ('%s PARAMS:{}' % self.name)
        # 沿用 MOD 自己声明的参数约束：优先 params_schema，其次 input_schema；
        # 两者都没有时为空 dict（无必填约束，不额外报错）
        self.params_schema = spec.get('params_schema') or spec.get('input_schema') or {}
        # 分类由 MOD 在 ToolSpec 里声明；旧包未声明时归入「其他」
        category = spec.get('category')
        self.category = category.strip() if isinstance(category, str) and category.strip() else '其他'

    def meta(self):
        data = super().meta()
        data['source'] = self.source
        data['mod_id'] = self._mod_id
        return data

    def run(self, params, ctx):
        if not isinstance(params, dict):
            raise ToolError('参数必须是对象')
        resp = self._loader.call_tool(self.name, params)
        if not resp.get('ok'):
            raise ToolError(resp.get('error') or 'MOD 工具执行失败')
        output = resp.get('output')
        if output is None:
            return ''
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)


def sync_loader_blocks(loader):
    """把已加载 MOD 的工具同步进方块注册表；重复调用幂等，返回本次挂载的工具名。"""
    names = []
    for record in loader.list_mods():
        if record.get('status') != 'loaded':
            continue
        for spec in record.get('tools') or []:
            name = spec.get('name')
            if not name or BLOCK_REGISTRY.is_builtin(name):
                continue
            existing = BLOCK_REGISTRY.get(name)
            if existing is not None and getattr(existing, 'source', None) != 'mod':
                continue
            BLOCK_REGISTRY.register(ModToolBlock(loader, spec, record.get('id')), builtin=False)
            names.append(name)
    return names


def invoke_block(name, params=None, ctx=None, allowed=None, approved=False):
    """非交互调用方的唯一能力入口（automation flow / SkillManager / 内建别名）。

    所有能力都必须落到 BLOCK_REGISTRY 里的方块上：
    - 未注册 → 拒绝；
    - allowed 不是 None 时，方块 canonical 名必须在显式装备集合内；
      allowed=None 只允许调用方在更外层已完成装备判定（例如内建别名转发），
      不表示“放开一切”；
    - write/dangerous 级必须由调用方显式传 approved=True，否则 fail-closed；
    - shell 未启用时拒绝。

    返回 dict：{"ok": bool, "output": ...} 或 {"ok": False, "error": str, "denied": reason}。
    """
    block = BLOCK_REGISTRY.get(name)
    if block is None:
        return {'ok': False, 'denied': 'unknown', 'error': '未知方块: %s' % name}

    canonical = block.name
    if allowed is not None and canonical not in set(allowed):
        candidates = ', '.join(sorted(str(a) for a in allowed)) or '无'
        return {
            'ok': False, 'denied': 'equipped',
            'error': '方块 %s 未装备（可用: %s）' % (canonical, candidates),
        }

    if not block.meta().get('enabled', True) or (canonical == 'shell' and not _shell_config['enabled']):
        return {'ok': False, 'denied': 'disabled', 'error': '方块 %s 当前未启用' % canonical}

    risk = block.risk or 'read'
    if risk in ('write', 'dangerous') and not approved:
        return {
            'ok': False, 'denied': 'approval',
            'error': '方块 %s 为 %s 级，非交互调用需要显式审批，已拒绝' % (canonical, risk),
        }

    if params is None:
        params = {}
    if not isinstance(params, dict):
        return {'ok': False, 'denied': 'params', 'error': '参数必须是对象'}

    validation_error = validate_tool_params(block, params)
    if validation_error:
        return {'ok': False, 'denied': 'params', 'error': validation_error}

    run_ctx = dict(ctx or {})
    run_ctx.setdefault('workdir', PROJECT_ROOT)
    run_ctx.setdefault('shell_timeout', _shell_config['timeout'] or DEFAULT_SHELL_TIMEOUT)
    run_ctx.setdefault('allowed', allowed)
    try:
        return {'ok': True, 'output': block.run(params, run_ctx)}
    except ToolError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}


def _filter_allowed(tools, allowed):
    """按装备集合过滤方块；allowed=None 表示不做限制（兼容旧调用）。"""
    if allowed is None:
        return list(tools)
    allowed = set(allowed)
    return [t for t in tools if t.name in allowed]


def list_agent_tools(mode="agent", allowed=None):
    """工具清单（供 /api/agent/tools 与前端展示）。enabled=false 的工具前端可见但置灰。

    mode: "agent"（完整工具集）| "chat"（懒调用，只暴露 read 级 + automation/MCP 能力标识）
    allowed: 已装备的能力名集合；None = 不限制。
    """
    all_tools = _filter_allowed(BLOCK_REGISTRY.list_all(), allowed)
    if mode == "chat":
        # Chat 模式（懒调用）：只暴露 read 级工具 + automation/MCP 能力
        # 写操作和 shell 被完全隐藏（不是禁用，是根本不进工具清单）
        filtered = [t for t in all_tools if t.risk == 'read']
        return [t.meta() for t in filtered] + [
            # 额外暴露 MCP 能力标识（不是具体工具，是能力声明）
            {'name': 'mcp', 'label': 'MCP 服务器', 'description': '当前运行时尚未接入 MCP，不可连接或调用任何 MCP 服务器', 'risk': 'read', 'usage': None, 'enabled': True, 'mode_hint': 'lazy'},
        ]
    return [t.meta() for t in all_tools]


def build_tool_protocol_section(mode="agent", allowed=None):
    """拼进用户消息侧的动态协议段（不改 SFT system 触发词）。

    mode: "agent"（完整协议段，含写操作 + 审批流）| "chat"（懒调用协议，只给只读工具 + automation/MCP 标识）
    allowed: 已装备的能力名集合；None = 不限制。
    """
    all_tools = _filter_allowed(BLOCK_REGISTRY.list_all(), allowed)
    shell_enabled = _shell_config['enabled']

    if mode == "chat":
        # Chat 模式：只暴露只读工具 + automation/MCP 能力
        read_tools = [t for t in all_tools if t.risk == 'read' and t.meta().get('enabled', True)]
        lines = [
            '【懒调用工具协议（Chat 模式）】',
            '你可以在必要时调用以下工具来获取信息（所有路径均相对项目根目录）：',
            '',
            '【只读工具（直接执行，无需审批）】',
        ]
        for t in read_tools:
            lines.append(f"- {t.usage}  # {t.description}")
        lines += [
            '',
            '【可用能力（懒调用标识，不需要显式 /$TOOL: 指令）】',
            '- automation：已接线本体调度引擎，用 /$TOOL:automation PARAMS:{"action": "list"} 查 flow、{"action": "runs"} 查最近运行；触发用 /$TOOL:automation_trigger（写级，本模式会拦截并提示审批）',
            '- mcp：当前运行时尚未接入 MCP，没有可连接的服务器；用户问到外部工具/资源接入时请如实说明暂不支持，不要尝试调用，也不要承诺代为连接',
            '',
            '调用规则：',
            '1. 需要显式调用只读工具时，单独输出一行（一行可多条指令）：',
            '   /$TOOL:工具名 PARAMS:{"参数名": "值"}',
            '2. automation 用 /$TOOL:automation 查看 flow 与运行记录，触发用 /$TOOL:automation_trigger（写级需审批）。MCP 尚未接入，不要调用，也不要向用户承诺该能力存在。',
            '3. 本模式下**绝对禁止文件写入和 shell 命令**——请保持在只读范围内。',
            '4. 路径提示：所有路径均相对项目根。**用户没给精确路径时，先用 glob 或 list_dir 定位！不要猜路径！**',
            '5. 任务完成时，直接输出给用户的最终答复，不要再输出任何 /$TOOL: 指令。',
            '',
            '【重要红线】',
            '- 严禁访问 /system、/proc、/sys、/dev、/etc/passwd 等系统目录',
            '- 严禁触碰 ~/.ssh、~/.aws、~/.kube 等密钥目录',
        ]
        return '\n'.join(lines)

    # Agent 模式：完整协议段
    enabled_tools = [t for t in all_tools if t.meta().get('enabled', True)]
    read_tools = [t for t in enabled_tools if t.risk == 'read']
    write_tools = [t for t in enabled_tools if t.risk in ('write', 'dangerous')]
    lines = [
        '【Agent 工具协议（仅本任务生效）】',
        '你现在处于 Agent 模式，可以调用以下工具完成任务（所有路径均相对项目根目录）：',
        '',
        '【只读工具（直接执行）】',
    ]
    for t in read_tools:
        lines.append(f"- {t.usage}  # {t.description}")
    if write_tools:
        lines.append('')
        lines.append('【写操作工具（需用户逐次审批后执行）】')
        for t in write_tools:
            lines.append(f"- {t.usage}  # {t.description}")
    lines += [
        '',
        '调用规则：',
        '1. 需要调用工具时，单独输出一行（一行可多条指令）：',
        '   /$TOOL:工具名 PARAMS:{"参数名": "值"}',
        '2. 每轮先简短说明思路，再输出工具指令；系统会把结果返回给你，下一轮继续。',
        '3. 只能使用上面列出的工具；PARAMS 必须是合法 JSON 对象。',
        '4. 写操作工具会先暂停并征求用户同意：被批准后才会执行，被拒绝请改用只读思路或调整方案。',
        '5. 任务完成时，直接输出给用户的最终答复，不要再输出任何 /$TOOL: 指令。',
        '6. 路径提示：所有路径均相对项目根。**用户没给精确路径时，先用 glob 或 list_dir 定位！不要猜路径！**',
        '7. 如果工具返回错误并给出了重试指令，请直接抄那个指令重试，不要换其他工具绕路。',
        '',
        '【重要红线（即使审批也绝对禁止）】',
        '- 系统目录：/system、/proc、/sys、/dev、/etc/passwd、/Windows/System32/config',
        '- 密钥目录：~/.ssh、~/.aws、~/.kube',
        '- 上述红线任何情况下都不能触碰，包括 shell 命令里也绝对禁止。',
    ]
    if shell_enabled:
        lines += [
            '',
            '8. shell 为危险级工具：命令在 Windows 宿主以项目根为工作目录执行，**每条命令都会暂停征求用户同意**。',
            '   只允许运行安全、只读或建设性的命令；禁止任何删除/格式化/关机/注册表/跳出项目目录的命令（黑名单会直接拒绝）。',
            '   命令必须简洁单条，优先用文件工具完成文件操作；命令带超时（默认 10 秒），长任务不要用 shell。',
        ]
    lines += [
        '',
        '【工具调用完整示例（照抄这个结构）】',
        '场景 A：用户只说"帮我看看 xxx 文件"，没给路径',
        '  思路：先 glob 找到文件在哪~',
        '  /$TOOL:glob PARAMS:{"pattern": "**/xxx*"}',
        '  （假设 glob 返回 "subdir/xxx.md"）',
        '  思路：好的找到了，这就去读~',
        '  /$TOOL:file_read PARAMS:{"path": "subdir/xxx.md", "offset": 1}',
        '',
        '场景 B：搜索包含关键词的文件',
        '  思路：我来搜一下哪个文件里有这个内容~',
        '  /$TOOL:grep_text PARAMS:{"pattern": "某个关键词"}',
        '',
        '场景 C：看一眼目录里有啥',
        '  思路：先看看项目结构吧~',
        '  /$TOOL:list_dir PARAMS:{"path": "."}',
        '',
        '场景 D：文件不存在但错误里给了候选 → 直接抄',
        '  你调用: /$TOOL:file_read PARAMS:{"path": "wrong/path/file.txt"}',
        '  系统返回错误: 文件不存在... 但找到同名文件: real/file.txt',
        '  下一轮你直接抄系统给的重试指令:',
        '  /$TOOL:file_read PARAMS:{"path": "real/file.txt", "offset": 1}',
    ]
    return '\n'.join(lines)
