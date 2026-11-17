# 08 写第一个 Skill MOD

> 本章属于「装配型」路径（B），前置：[07 技能安装与启停](07-manage-skills.md)。本章只讲「自己写一个可插拔方块」，不讲从 registry 安装（那条线还没定）。

## 1. 你会得到什么

`.simchat/skills/com.example.helloskill/` 下有一个能加载的技能包；重启服务后，控制台技能页多出「Hello Skill」，Agent 工具清单里多出 `say_hello`，并且能被模型真正调用。

```text
> 用 say_hello 工具向张三问一句好
工具调用 say_hello {"name": "张三"}
✓ {"success": true, "message": "Hello, 张三!"}
```

## 2. 前置条件

- 服务能正常启动，Agent 模式可用（第 04 章）。
- 会读 JSON，能写一点 Python（函数级就够）。
- 知道改完包要重启服务（第 07 章）。

## 3. 跟着做

### 3.1 生成骨架

```bash
python .simchat/scripts/entry.py cli init --type skill --name com.example.helloskill --target .simchat/skills/com.example.helloskill
```

预期输出 `[SimChat] ✓ 已生成 skill 模板 → .simchat/skills/com.example.helloskill`，目录里有：

```text
com.example.helloskill/
  manifest.json
  python/
    hello_skill.py
    __init__.py
```

`--type` 还可选 `binary` / `automation` / `agent-config`；本章只要 `skill`。

### 3.2 读懂 manifest

```json
{
  "id": "com.example.helloskill",
  "type": "skill",
  "layer": "block",
  "name": "Hello Skill",
  "description": "一个最简单的 skill MOD（可插拔方块）示例",
  "version": "0.1.0",
  "abi": "simchat-mod/2",
  "entry": "hello_skill:register",
  "hooks": ["agent.block"],
  "capabilities": { "fs": { "read": ["workspace"] } },
  "requires": { "simchat": ">=2.0,<3", "python": ">=3.9" },
  "license": "MIT"
}
```

几个关键点：

- `id` 是唯一标识，也是启停接口用的键；**不要求等于目录名**，但建议一致。
- `type=skill` + `layer=block` 表示「可插拔方块」；`entry` 形如 `模块:函数`，模块名相对包内 `python/` 解析。
- `hooks` 至少一个，`agent.block` 表示参与 Agent 工具集。
- `capabilities` 是运行时护栏的依据：示例只声明了读工作区。用不到文件就别声明，声明了才有权限。
- `requires.simchat` 用区间；本地跑直接写 `>=2.0,<3` 即可。

> 模板里的 `$schema` 是给编辑器补全用的相对路径，加载器不校验它。从 `.simchat/skills/` 生成时它指向的位置是错的，改成 `../../../spec/mod-manifest.schema.json` 或不写都行。

### 3.3 写 entry

打开 `python/hello_skill.py`，模板已经给了最小实现：

```python
from simchat_mod import ToolSpec


def say_hello(params):
    name = (params or {}).get("name", "world")
    return {"success": True, "message": "Hello, %s!" % name}


def register(api):
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
```

只改三处就能变成你自己的工具：

1. `say_hello` 的函数体（真正干活的地方）；
2. `ToolSpec.name`（模型看到的工具名，建议小写+下划线）；
3. `ToolSpec.description`（模型决定要不要调它，主要看这句）。

如果要加必填参数，在 `params_schema` 里写标准 JSON Schema 的 `required`：

```python
params_schema={
    "type": "object",
    "properties": {
        "city": {"type": "string", "description": "城市名"},
        "days": {"type": "integer", "description": "预报天数"},
    },
    "required": ["city"],
}
```

执行前的参数校验会读它：缺 `city` 或类型明显不符时，工具不会执行，模型会收到一条说明缺什么、期望什么类型的错误文本。

### 3.4 重启并验证

1. `Ctrl+C` 停服务，再 `python .simchat/scripts/entry.py web`。
2. 控制台技能页应出现「Hello Skill v0.1.0」。
3. 确认工具已注册：

   ```bash
   curl http://127.0.0.1:5000/api/agent/tools
   ```

   在返回的 JSON 里搜 `say_hello`。

4. 切到 Agent 模式，发「用 say_hello 向张三问好」。预期出现工具调用卡片和 `Hello, 张三!`。

### 3.5 调试

- 加载失败：控制台技能页条目的 `status` 变成 `err`（`warn` 表示只有警告），具体原因看 `GET /api/console/skills` 的 `error` 字段。
- entry 抛异常：宿主只保留加载器给的摘要（如「沙箱启动超时」「沙箱静默退出」），**不会拖垮服务**（子进程隔离）；但子进程的 stderr 会被宿主直接丢弃，traceback 不进 `simchat.log`，要复现得进包目录手动跑（见 [11 章](11-debugging.md)）。
- 运行期报错：工具调用卡片会显示错误文本；同时看 `.simchat/data/logs/simchat.log`。IDE 控制台的「沙箱输出」页签目前没有数据源，是空的。
- 改了代码没生效：忘了重启。工具是启动时注册的，没有热重载。

## 4. 为什么会这样

- **为什么要子进程**：每个包跑在独立的 Python 进程里，`cwd` 是包目录，`python/` 与 `scripts/` 会被加进 `sys.path`，所以 `from hello_skill import ...` 和相对导入都按包内布局工作。包崩了宿主只记一条失败，不影响其它包。
- **为什么 IPC 不会污染输出**：宿主只消费带 `@@simchat-ipc@@` 前缀的行，你在工具里 `print()` 多少都不会破坏协议。
- **为什么 `backend` 还要再写一次模块名**：`ToolSpec.backend` 是「工具名 → 实现函数」的映射，格式与 `entry` 一样是 `模块:函数`；宿主在收到调用请求时按这个字符串在子进程里定位。
- **为什么 risk 很重要**：`read` 直接执行；`write` / `dangerous` 会走审批。写操作把自己标成 `read` 属于欺骗，代码评审时应该拦下来。
- **为什么参数校验会拦你**：`params_schema` 支持 JSON Schema 形态（`{type: object, properties, required}`）和内建方块的简写形态（`{字段: {type, required}}`），两种都会被归一化后再校验。声明得越准，模型被纠正得越快。
- **返回值约束**：`dict` / `str` 都行，最终会被 JSON 序列化回灌模型；不要把不可序列化对象直接返回。单次输出建议控制在 8KB 内（宿主会统一截断）。

## 5. 常见坑

- **`no module named hello_skill`**：`entry` / `backend` 里的模块名必须对应 `python/` 下的文件名（不含 `.py`），且 `python/__init__.py` 存在。
- **工具出现了但模型从不调用**：`description` 写得太抽象。把「什么时候用、输入是什么」写清楚，必要时在任务里直接点名工具。
- **写完 `capabilities.fs.read` 还是读不到文件**：白名单只放行声明的 scope，且 `file_read` 之外的路径访问要靠自己按包内约定实现；越界会被护栏拒绝。
- **目录名与 id 不一致导致 toggle 404**：启停接口用 `id`，不是目录名。

## 6. 验收清单

- [ ] 能说出 `manifest.json` 里六个必填字段
- [ ] 能从模板改出一个自己的工具，并在工具清单里看到它
- [ ] 能加上 `required` 参数，并验证缺参时被拦下
- [ ] 能读懂加载失败时 `error` 字段的含义
- [ ] 知道改代码后必须重启

## 7. 延伸阅读

- [simchat_mod SDK](../../sdk/python/simchat_mod/__init__.py)：`ModApi`、`ToolSpec`、`hook`
- [mod-manifest.schema.json](../../spec/mod-manifest.schema.json)：字段与条件必填
- [sandbox_runner.py](../../loader/sandbox_runner.py)：`sys.path`、cwd 与 IPC 前缀
- [09 权限与安全](09-capabilities.md)
