"""Git 索引客户端 —— 运行时从 SimChat Registry 查找 MOD。

Phase 4 实现本地索引读取 + 缓存 + 查找。**不负责 git clone / 自动下载**——
那是宿主进程（lifecycle）的安装行为，留给后续切片或宿主直接调用 CLI。

CLI publish 命令生成的条目 JSON 就是要合并进 index.json 的 entries[] 数组。

用法（宿主侧）：
    from simchat.loader.index import Registry

    reg = Registry.load("path/to/simchat/registry/index.json")
    entry = reg.find("barry.galax")
    print(entry["versions"][0]["download"]["url"])
    print(entry["versions"][0]["signature"])  # binary 的签名，可喂给 loader.verify

设计原则（与 CLI 一致）：
  - 零运行时依赖：不 import lifecycle / sandbox / registry.py；只读 JSON。
  - 所有方法幂等、无副作用；缓存放在进程内。
  - 解析失败时 fail-open（返回空索引而不是抛异常）—— 索引文件损坏不阻断本体。
"""

import json
import os


DEFAULT_INDEX_PATH = os.path.join(
    os.path.dirname(__file__), "..", "registry", "index.json"
)


def _parse_version(tuple_or_spec):
    """把 version 字符串或 (major,minor,patch) 元组统一成 (major,minor,patch) 元组。"""
    if isinstance(tuple_or_spec, (tuple, list)):
        parts = list(tuple_or_spec) + [0, 0, 0]
        return tuple(int(x) for x in parts[:3])
    text = str(tuple_or_spec or "").strip()
    if not text:
        return (0, 0, 0)
    # 剥掉预发布后缀和 build metadata
    text = text.split("-")[0].split("+")[0]
    parts = text.split(".")
    while len(parts) < 3:
        parts.append("0")
    return tuple(int(x) for x in parts[:3])


def _version_ge(version, spec):
    """simple semver compare：version >= spec。两个字符串都先 parse 成 (M,m,p) 元组。"""
    return _parse_version(version) >= _parse_version(spec)


class Registry(object):
    """官方 MOD 索引客户端。"""

    def __init__(self, data):
        self._data = data or {"entries": []}
        self._entries = self._data.get("entries") or []
        # 倒排索引：mod_id → entry
        self._by_id = {}
        for entry in self._entries:
            mod_id = entry.get("mod_id")
            if mod_id:
                self._by_id[mod_id] = entry

    # ---------- 构造 ----------

    @classmethod
    def load(cls, index_path=None):
        """从本地 index.json 加载。文件不存在或解析失败 → 返回空索引（fail-open）。"""
        path = os.path.abspath(index_path or DEFAULT_INDEX_PATH)
        if not os.path.isfile(path):
            return cls({})
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return cls({})
        return cls(data)

    @classmethod
    def from_json(cls, json_text):
        """直接从 JSON 字符串构造（测试 / 远程拉取后解析用）。"""
        try:
            data = json.loads(json_text) if isinstance(json_text, str) else json_text
        except Exception:
            data = {}
        return cls(data)

    # ---------- 只读字段 ----------

    @property
    def version(self):
        return self._data.get("version", 0)

    @property
    def updated_at(self):
        return self._data.get("updated_at", "")

    @property
    def abi(self):
        return self._data.get("abi", "")

    @property
    def entries(self):
        return list(self._entries)

    def __len__(self):
        return len(self._entries)

    # ---------- 查找 ----------

    def find(self, mod_id, version=None):
        """按 mod_id 查找条目。返回 dict 或 None。

        若 version 为 None → 返回最新版本的完整 entry；
        否则从 entry.versions[] 里挑出指定版本的 version dict（注意层级不同）。
        """
        entry = self._by_id.get(mod_id)
        if not entry:
            return None
        if version is None:
            return entry
        for ver in entry.get("versions", []):
            if ver.get("version") == version:
                return ver
        return None

    def search(self, mod_type=None, abi=None, host_version=None):
        """搜索 MOD，按 type / abi / requires.lmbrew 过滤。返回 entry 列表。"""
        result = []
        for entry in self._entries:
            if mod_type and entry.get("type") != mod_type:
                continue
            # 至少要有一个版本满足 abi + requires
            if abi or host_version:
                matched = False
                for ver in entry.get("versions", []):
                    if abi and ver.get("abi") != abi:
                        continue
                    requires = (ver.get("requires") or {}).get("lmbrew", "")
                    if host_version and requires:
                        # 简单处理：requires 形如 ">=2.0,<3" 或 ">=2.0" ——
                        # 只取第一个 >=/==/> 约束的下限做比较
                        lower = None
                        for part in requires.split(","):
                            part = part.strip()
                            if part.startswith(">="):
                                lower = part[2:].strip()
                                break
                            if part.startswith(">") or part.startswith("=="):
                                lower = part[1:].strip()
                                break
                        if lower and not _version_ge(host_version, lower):
                            continue
                    matched = True
                    break
                if not matched:
                    continue
            result.append(entry)
        return result

    # ---------- 工具 ----------

    @staticmethod
    def get_download_url(entry_or_version):
        """从 entry 或 version dict 计算实际下载 URL。

        支持 Phase 4 索引三种 download.type：
          - git-path → url + / + ref + / + path 片段（给 git clone sparse-checkout 用）
          - git-tag  → url + / + tag
          - direct   → url 直接给
        """
        download = entry_or_version.get("download") if isinstance(entry_or_version, dict) else None
        if not download:
            return None
        dtype = download.get("type", "direct")
        url = download.get("url", "")
        path = download.get("path")
        ref = download.get("ref")
        if dtype == "git-path":
            return "%s#%s:%s" % (url, ref or "HEAD", path or "")
        if dtype == "git-tag":
            return "%s#%s" % (url, ref or "")
        return url

    def latest_version(self, mod_id):
        """返回 mod_id 的最新版本号字符串；找不到返回 None。"""
        entry = self._by_id.get(mod_id)
        if not entry:
            return None
        versions = [v.get("version", "0.0.0") for v in entry.get("versions", [])]
        if not versions:
            return None
        versions.sort(key=_parse_version)
        return versions[-1]


# ---------- 全局单例（可选） ----------

_REGISTRY_CACHE = {}


def get_registry(index_path=None):
    """全局 getter，进程内缓存。"""
    key = os.path.abspath(index_path or DEFAULT_INDEX_PATH)
    if key not in _REGISTRY_CACHE:
        _REGISTRY_CACHE[key] = Registry.load(key)
    return _REGISTRY_CACHE[key]


def reload_registry(index_path=None):
    """强制重新加载索引（宿主进程有热更新需求时用）。"""
    key = os.path.abspath(index_path or DEFAULT_INDEX_PATH)
    _REGISTRY_CACHE.pop(key, None)
    return get_registry(key)
