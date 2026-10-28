# Sandbox IPC 协议设计（Phase 2 P2.3）

> 发布者和加载者必须遵守本协议。实现见 [sandbox_runner.py](./sandbox_runner.py)（子进程侧）和 [sandbox.py](./sandbox.py)（宿主侧）。

---

## 1. 目标

把 binary MOD 的 Python 入口从宿主进程 `importlib.import_module` 放进**独立 Python 子进程**。Phase 1 只解决三件事：
- **崩溃隔离**：子进程崩溃/超时不拖宿主（kill -9 友好）。
- **进程树闸门**：MOD 声明 `capabilities.shell=true` 才能在子进程里创建新进程（monkey-patch subprocess.Popen）。
- **资源清理**：宿主 atexit/SIGTERM 时 kill 所有沙箱子进程。

不做 Phase 1 的：文件/网络/seccomp 级系统调用隔离（P2.3 后续或 Phase 4）；非 binary 类型（agent-config/skill/automation）沙箱。

---

## 2. 生命周期

```
宿主 discover()
  │
  ├─ sandbox.run_isolated(package_dir, entry, manifest)
  │     → 启动 subprocess.Popen([sys.executable, sandbox_runner.py, ...])
  │
  │     子进程启动：
  │       1. sys.path 注入 MOD python/
  │       2. monkey-patch subprocess.Popen（capabilities.shell=false 时 raise PermissionError）
  │       3. 读命令行参数（package_dir / entry_spec / manifest_json）
  │       4. importlib.import_module + getattr entry attr
  │       5. 创建 ModApi（只有 register_mode 方法 + 空 services dict）
  │       6. 调 entry(api) → MOD 注册 ModeSpec 元数据
  │       7. stdout 写 {"type":"register", "modes":[...]}
  │       8. 进入 stdin JSON 行读循环（长驻）
  │
  │     宿主收到 {"type":"register", "modes":[...]}
  │       → 把每个 ModeSpec 注册到 ModeRegistry（回调是代理函数）
  │       → 保存 (handle, manifest) 到 _sandboxes 字典
  │
  ├─ 用户点 Galax ⚡ 按钮 → 宿主调代理回调()
  │     → sandbox.invoke(handle, mode_id, args_dict)
  │         → stdin 写 {"type":"invoke", "mode_id":"galax", "input":{...}}
  │         → 子进程内调 galax.pipeline:query
  │         → stdout 写 {"type":"result", "mode_id":"galax", "ok":true, "output":...}
  │         → 宿主读回
  │
  └─ 宿主退出（atexit / SIGTERM）
        → sandbox.kill_all()
        → 对每个 handle 发 {"type":"shutdown"} 后 wait(timeout=5) + force kill
```

---

## 3. 消息格式（JSON Lines，UTF-8，一行一条）

### 宿主 → 子进程

| type | fields | 说明 |
|---|---|---|
| `"invoke"` | `mode_id: str`, `input: dict` | 调已注册 mode 的 backend 函数 |
| `"shutdown"` | （无） | 优雅关闭 |
| `"ping"` | （无） | 健康检查，预期 pong |

### 子进程 → 宿主

| type | fields | 说明 |
|---|---|---|
| `"register"` | `modes: list[ModeSpec]` | 启动后第一条，一次性 |
| `"result"` | `mode_id: str`, `ok: bool`, `output: any`, `error: str?` | invoke 响应 |
| `"pong"` | （无） | ping 响应 |
| `"log"` | `level: str`, `msg: str` | 子进程日志回传宿主（可选） |

### ModeSpec 序列化字段（从 SDK ModeSpec 对象提取）

```json
{
  "id": "galax",
  "label": "Galax",
  "icon": "⚡",
  "order": 20,
  "frontend_entry": "web/galax.js",
  "backend": "galax.pipeline:query",  // 字符串形式的 entry spec，宿主按需重新 import
  "cost": "high",
  "hook": "chat.mode"
}
```

---

## 4. 错误路径

| 场景 | 宿主行为 | MOD status |
|---|---|---|
| 子进程启动后超时（entry(api) 30s 内没发 register） | kill + `_fail(record, "沙箱启动超时")` | failed |
| 子进程崩溃（非 0 退出码） | `_fail(record, "沙箱崩溃")` | failed |
| 子进程 stdout 不是合法 JSON | 视为 register 失败 → `_fail` | failed |
| invoke 时子进程已死 | 代理回调抛 RuntimeError → 宿主 UI 显示"M O D 执行失败" | 不改变（仍然 loaded） |
| invoke 结果 ok=false | 代理回调返回 error → 宿主正常错误处理 | 不改变 |

---

## 5. capabilities.shell 闸门

子进程启动时检查 manifest.capabilities.shell：
- 缺省或 false → monkey-patch `subprocess.Popen`：如果不是内部 runner 自己的调用（可以通过一个 token 检测），就 raise PermissionError("MOD 未声明 shell capability，禁止创建子进程")。
- true → 不 patch。

Phase 1 只 patch subprocess.Popen；os.system / os.popen / multiprocessing 等其他进程创建入口暂不覆盖。

---

## 6. 与 lifecycle._invoke_entry 的集成点

```python
# lifecycle._invoke_entry 改调 sandbox
from .sandbox import run_isolated, invoke as sandbox_invoke, kill_all

def _invoke_entry(self, package_dir, manifest, mod_id):
    handle = run_isolated(package_dir, manifest["entry"], manifest,
                          host_services=self._services)
    for spec in handle["modes"]:
        # ModeRegistry.register(handle["mod_id"], {id, label, callback: lambda: sandbox_invoke(handle, spec["id"], ...)})
        ...
    self._sandboxes[mod_id] = handle
```

---

## 7. 不做（Phase 1 边界）

- **文件系统隔离**：不限制 os.open / os.remove / shutil。Phase 2+ 用 seccomp/AppContainer/WASM 补。
- **网络隔离**：不限制 socket / urllib / requests。
- **sys.modules 黑名单**：不禁止 import os/subprocess/socket 等。
- **非 binary 类型沙箱**：agent-config/skill/automation 继续在宿主跑。
- **ModeSpec 完整序列化**：只提取上表列出的 8 个字段，其他 ModeSpec 扩展字段 Phase 1 忽略。
