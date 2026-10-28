
# SimChat WebView — HarmonyOS NEXT 原生客户端壳

一个最小 ArkTS 工程，把 SimChat 的 Flask Web UI 包成一个鸿蒙原生应用。

## 工作原理

```
┌────────────────────────────┐         ┌──────────────────────────────────┐
│  HarmonyOS 宿主            │         │  融合开发引擎 (openEuler Linux)   │
│  ┌──────────────────────┐  │  NAT    │  ┌────────────────────────────┐  │
│  │  SimChat WebView App │──┼─────────┼─▶│  python -m simchat.web       │  │
│  │  (ArkUI + Web 组件)  │  │         │  │  http://127.0.0.1:5000      │  │
│  └──────────────────────┘  │         │  └────────────────────────────┘  │
└────────────────────────────┘         └──────────────────────────────────┘
```

ArkUI 的 `Web` 组件加载 Linux 子系统里的 SimChat 后端。用户可以在应用内修改后端地址（融合开发引擎的 NAT IP / 本机 / 远端云服务）。

## 快速开始

### 1. 准备后端（融合开发引擎里）

```bash
# 启动融合开发引擎后，cd 到共享目录
cd /mnt/linux_share/<你的LMBrewer目录>

# 安装依赖 + 启动 SimChat
pip install -r simchat/scripts/requirements-simchat.txt
python -m simchat.web &

# 看看 Linux 子系统的内网 IP（鸿蒙端访问用这个）
ip addr show eth0 | grep 'inet '
#   → 192.168.xxx.xxx
```

### 2. 构建鸿蒙客户端

在 **DevEco Studio**（鸿蒙电脑应用市场可直接安装）里：

1. **新建** → **ArkTS** → **Employment** → 空项目（Empty Ability）
2. 把本目录下的文件复制进去覆盖：
   - `entry/src/main/ets/entryability/EntryAbility.ets`
   - `entry/src/main/ets/pages/Index.ets`
   - `entry/src/main/module.json5`（记得把权限里的 INTERNET 保留）
   - `AppScope/app.json5`
3. `entry/src/main/resources/base/profile/main_pages.json` 和 `string.json` 参考本目录
4. 替换图标 `entry/src/main/resources/base/media/app_icon.png`（随便放一张 PNG）
5. **Run** → 选择鸿蒙设备或模拟器 → 编译

### 3. 连接

在应用里填：`http://192.168.xxx.xxx:5000`（刚才 `ip addr` 看到的地址），点「连接」。

## 为什么这样设计？

鸿蒙 PC **原生不支持 Python 运行时**（华为官网声明），但通过融合开发引擎可以：
- 跑完整 openEuler Linux 用户态 → python3 + pip 全可用
- NAT 网络让鸿蒙宿主 ↔ Linux 子系统互通
- 共享文件夹做双向数据桥

SimChat 的 Web 后端跑在 Linux 里最稳，鸿蒙侧只做一个 **WebView 壳**——这是"SimChat 鸿蒙入口"的最优解：
- ✅ 不需要把 Python 移植到 HarmonyOS 内核
- ✅ 后端代码完全复用 simchat/web/，零改动
- ✅ ArkUI 壳加起来也就 200 行
- ✅ Phase 0 骨架，后续可以加 JSBridge、深链接、离线缓存

## 后续 Phase

- **Phase 1**：JSBridge —— ArkUI 侧加"一键拉起 Ollama 检查"按钮
- **Phase 2**：离线支持 —— 把 chat.css / chat.js 预打包进 `$rawfile/`，无网络也能聊（走本地模型）
- **Phase 3**：鸿蒙原生会话管理 —— 用 `@ohos.data.relationalStore` 存 session

## 关键文件

| 文件 | 作用 |
|---|---|
| `scripts/run-harmony.sh` | 融合开发引擎里的启动脚本（自动探测 Layer 1-3） |
| `EntryAbility.ets` | 应用入口，加载 `pages/Index` |
| `Index.ets` | WebView 主界面：后端地址配置 + SimChat 对话 |
| `module.json5` | 模块配置（声明 INTERNET 权限） |
