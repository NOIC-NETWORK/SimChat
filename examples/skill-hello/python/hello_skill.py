"""Hello Skill — SimChat SDK skill MOD 最小示例。

这个文件被 `python -m simchat.cli init --type skill` 生成的模板拷贝自这里。
loader 在 sandbox 子进程里执行 manifest.entry = 'hello_skill:register'，
ModApi 实例注入为 register(api) 的参数。

register_tool() 调用会让宿主能通过 call_tool('say_hello', {...}) 跨进程调用。
backend 参数必须是字符串引用 'module:attr'（callable 不能跨进程序列化）。
"""

from simchat_mod import ToolSpec


def say_hello(params):
    """ToolSpec.backend 指向的函数。

    sandbox_runner 把宿主侧 call_tool() 转发到这个函数；
    返回值可以是 dict 或 str，宿主原样消费。
    """
    name = (params or {}).get("name", "world")
    greeting = "Hello, %s! — from SimChat skill-hello" % name
    return {
        "success": True,
        "message": greeting,
        "params_received": params,
    }


def register(api):
    """entry 函数 —— 被 sandbox 子进程启动时调用。

    api 是 simchat_mod.ModApi 实例，宿主注入。register_tool() 注册后，
    loader.lifecycle._tools 表里会出现一个新条目，tool name = 'say_hello'。
    """
    api.register_tool(ToolSpec(
        name="say_hello",
        label="Say Hello",
        description="向 Agent 返回一句问候 —— 最简单的 skill MOD 示例",
        risk="read",
        backend="hello_skill:say_hello",
        params_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要问候的名字"}
            }
        },
    ))
    return api
