# 12 打包、发布与继续深入

> 本章是「开发者」路径（C）的最后一站，前置：[08 写第一个 Skill MOD](08-first-skill.md)、[09 权限与安全](09-capabilities.md)。

## 1. 你会得到什么

一个可以直接分发的包：`manifest.json` 里有算好的 `integrity`（binary 包还有 `signature`），一个排除了缓存文件的 zip，以及一条可以贴进 registry 索引的 JSON 条目。

```text
[SimChat] integrity  = sha256:9f2c...
[SimChat] ✓ manifest.json 已更新（integrity + signature 字段）
[SimChat] ✓ 已打包 zip → .simchat/skills/dist/com_example_helloskill-0.1.0.zip
[SimChat] ✓ registry 条目（贴进 simchat/registry/index.json 的 entries[] 数组）：
```

## 2. 前置条件

- 第 08 章的包已经能被加载（重启后工具出现在 `/api/agent/tools`）。
- 依赖里已有 `cryptography`（`requirements-simchat.txt` 包含它），否则签名相关命令会导入失败。
- 知道「私钥只留在本机、公钥才交出去」。

## 3. 跟着做

### 3.1 生成密钥对（只需一次）

```bash
python .simchat/scripts/entry.py cli gen-key
```

预期输出：

```text
[SimChat] ✓ 密钥对已生成:
  私钥: C:\Users\<你>\.simchat\private_key.pem  (不要进 git，不要发给别人)
  公钥: C:\Users\<你>\.simchat\public_key.pub  (发给官方，添加到 simchat/loader/public_keys/)
```

- 默认目录 `~/.simchat`，可用 `--key-dir` 改。
- 私钥权限在 Unix 上会设为 `0600`；Windows 下 `chmod` 不生效，目录权限要自己确认。
- 只有 `type=binary` 的包需要签名；skill / automation / agent-config 不签名。

### 3.2 先做一次只读校验

```bash
python .simchat/scripts/entry.py cli verify .simchat/skills/com_example_helloskill
```

非 binary 包的预期输出是「✓ manifest 结构校验通过（非 binary 类型跳过签名）」，并打印当前 `integrity`。这一步只读，不改文件。

### 3.3 打包

```bash
python .simchat/scripts/entry.py cli pack .simchat/skills/com_example_helloskill
```

它按顺序做四件事：

1. 预检查 `id` / `type` / `name` / `version` / `abi` 五个字段非空；
2. 计算 `integrity`，写进 manifest；
3. 如果是 `binary`，用私钥签名，写进 `signature`；
4. 回写 `manifest.json`，再做一次完整 manifest 校验与验签，最后可选打 zip。

要 zip 就加参数：

```bash
python .simchat/scripts/entry.py cli pack .simchat/skills/com_example_helloskill --zip
```

默认输出到包目录同级的 `dist/`，文件名为 `<id>-<version>.zip`；`--dist <dir>` 可改输出目录。zip 里会跳过 `__pycache__`、`.pyc`、`.pyo`。

### 3.4 binary 包：签名与指定私钥

`type=binary` 的包必须同时有 `signature` 与 `integrity`，缺一个 manifest 校验就报错。默认私钥路径是 `~/.simchat/private_key.pem`，也可以显式指定：

```bash
python .simchat/scripts/entry.py cli pack path/to/binary-mod --key D:\keys\my_private_key.pem
```

签名串格式是 `ed25519:<base64url>`，终端会只显示前 30 个字符。

### 3.5 生成发布条目

```bash
python .simchat/scripts/entry.py cli publish .simchat/skills/com_example_helloskill \
  --publisher "你的名字" \
  --repo-url "https://github.com/you/your-simchat-mods" \
  --output .simchat/skills/dist/registry-entry.json
```

`publish` 会先跑 manifest 校验 + `verify_package`，通过后生成一条包含 `mod_id`、`versions[]`、`manifest_hash` 的条目；`--output` 写文件，不写就打印到终端。

**它不联网、不上传、不创建 PR**。`download` 字段默认是 `git-path` 占位：

```json
"download": {
  "type": "git-path",
  "url": "https://github.com/your-username/your-simchat-mods",
  "path": "mods/com_example_helloskill",
  "ref": "HEAD"
}
```

不传 `--repo-url` 时就是这个占位串，记得替换成真实仓库。

### 3.6 看本地与 registry 索引

```bash
python .simchat/scripts/entry.py cli list
python .simchat/scripts/entry.py cli list --registry
```

`--registry` 会额外读 `registry/index.json`（可用 `--registry <path>` 指定）。文件不存在时只提示「本地没有远端索引」，不算错误。

> registry 的**安装**链路还没定，本章只覆盖「怎么产出条目」；第 08 章也刻意没写从 registry 安装。

### 3.7 确认版本号

```bash
python .simchat/scripts/entry.py cli --version
```

当前实际输出是 `simchat 0.4.0 (Phase 4)`。注意它与加载器的 `HOST_VERSION = "2.3.0"`（`loader/version.py`）不是同一个号：`requires.simchat` 校验用的是后者，前者只是 CLI 打印的字符串，尚未同步。写 `requires` 时以 2.x 为准。

## 4. 为什么会这样

### 4.1 integrity 怎么算

对包内所有文件按相对路径排序，逐个把「相对路径 + `\0` + 文件内容 + `\0`」喂给 SHA-256，输出 `sha256:<64 hex>`。`manifest.json` 自身不参与（否则无法自引用），`__pycache__`、`*.pyc`、`*.pyo` 排除（避免字节码缓存导致哈希漂移）。

所以：**pack 之后只要改了包内任何文件，integrity 就失效**，必须重新 pack。

### 4.2 签名负载怎么拼

```
<integrity> \0 <version> \0 <requires 的键排序 JSON（无空格）>
```

签名方与加载器必须用完全相同的序列化，空格或键序差异都会导致验签失败。加载器遍历 `loader/public_keys/` 下所有 `.pub` 公钥尝试验签，并检查吊销列表（`revoked.json`）。

### 4.3 两阶段校验，失败即拒

binary 包：

1. 本地重算 integrity，与 manifest 声明的比较；
2. 用公钥验签，并检查 `key_id` 是否被吊销。

任一失败，加载器 `fail-closed`，包变成 `status=failed`。非 binary 包跳过这两步，只做 manifest 结构校验——这意味着**「结构校验通过」不等于「代码可信」**，安装第三方包仍应读代码（第 09 章）。

开发期可用环境变量 `SIMCHAT_SKIP_VERIFY=1` 跳过 binary 的完整性与签名校验；它不会让非法 manifest 变合法，也不是修复手段。

### 4.4 `--pub-key` 与额外公钥

`verify_package(package_dir, manifest, extra_public_keys=None)` 会把 `loader/public_keys/` 下的公钥与调用方传入的额外公钥合并后一起尝试验签。CLI 的 `pack` / `verify` / `publish` 都通过 `--pub-key <pem>` 传入额外公钥（可重复），用于开发期：用本地 `gen-key` 生成的私钥签名、再用对应公钥验证，而不必把公钥先放进 `loader/public_keys/`。

```bash
python .simchat/scripts/entry.py cli verify path/to/binary-mod \
  --pub-key ~/.simchat/public_key.pub
```

不传 `--pub-key` 时只用系统公钥目录；两边都没有可用公钥，binary 包会以「系统未配置任何 MOD 签名公钥，无法验签」失败。

### 4.5 发布线现状

- `publish` 只负责「校验 + 生成条目 JSON」，不做网络请求、不校验 `--repo-url` 是否真实存在。
- 条目里的 `published_at` 取当天日期，`downloads` 固定 0，`deprecated` 固定 `false`。
- `registry/index.json` 是本地可选文件，`cli list --registry` 只读扫描它；官方索引的合并、审核与安装流程尚未落地。

### 4.6 ABI 与兼容规则

- 当前 ABI 是 `simchat-mod/2`；旧版 `lmbrew-mod/1` 仍可加载，但会收到迁移警告，下个大版本移除。
- `requires.simchat` 用区间（如 `>=2.0,<3`），与 `HOST_VERSION` 比较；`requires.python` 用同样的区间语法。
- `hooks` 是 fail-closed：出现未注册的 hook 名直接判 manifest 非法，不是忽略。
- ABI 变更规则见 [abi-changelog.md](../../spec/abi-changelog.md)，hook 清单见 [hooks.md](../../spec/hooks.md)。

## 5. 常见坑

- **pack 之后又改了文件**：integrity 失效，加载时报「integrity 不匹配」。改完必须重新 pack。
- **把私钥提交进 git**：私钥默认在 `~/.simchat`，不在仓库内；不要复制进项目目录。
- **以为非 binary 也验签**：skill / automation 只校验结构，签名字段对它们没有意义。
- **直接使用默认 `repo-url`**：占位串不会报错，但别人按条目下载会 404。
- **在 Windows 上依赖 `chmod 600`**：不生效，私钥保护要靠目录 ACL。

## 6. 验收清单

- [ ] 能用 `gen-key` 生成一对密钥，并说清哪个能给别人
- [ ] 能跑通 `verify`，并会用 `--pub-key` 验本地签名的包
- [ ] 能解释 integrity 为什么排除 `manifest.json`
- [ ] 能给 binary 包签名，并知道签名负载由哪三部分组成
- [ ] 能生成一条 registry 条目，并替换掉占位的 `repo-url`

已知限制：`cli --version` 与 `HOST_VERSION` 目前不同步，见 [known-limitations.md](../known-limitations.md)。

## 7. 延伸阅读

- [cli/main.py](../../cli/main.py)：`init` / `pack` / `verify` / `publish` / `gen-key` / `list`
- [verify.py](../../loader/verify.py)：integrity 计算与两阶段校验
- [keys.py](../../loader/keys.py)：签名负载、公钥加载、吊销列表
- [manifest.py](../../loader/manifest.py)：条件必填与 ABI 兼容
- [abi-changelog.md](../../spec/abi-changelog.md) / [hooks.md](../../spec/hooks.md)
- [11 调试与排错](11-debugging.md)
