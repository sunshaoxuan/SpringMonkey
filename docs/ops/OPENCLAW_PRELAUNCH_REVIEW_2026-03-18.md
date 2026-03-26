# OpenClaw 启动前总复核

日期：2026-03-18

## 总结结论

结论：已成功启动。启动前复核结论成立，但实际启动时额外暴露出 1 个 systemd 沙箱兼容性问题，现已修复并验证。

阻断项：无

非阻断项：
- `/root/.openclaw/openclaw.json` 与运行时配置不一致，缺少 Discord token 和 guild/channel 规则
- `memory-lancedb` 已完成向量后端预配置，但尚未接管默认 memory slot
- `diffs`、`diagnostics-otel` 仍未达到可加载状态
- `openclaw.service` 原始单元配置中的 `MemoryDenyWriteExecute=true` 与 Node/V8 运行机制不兼容，已改为 `false`
- `openclaw.service` 原始环境变量中的 `OPENCLAW_HOME=/var/lib/openclaw/.openclaw` 会诱发错误的嵌套运行目录，已移除
- `openclaw.service` 直接运行 `openclaw gateway run` 在当前版本下不稳定，已改为 supervisor wrapper 形态

## 通过项

### 远程入口

- `frpc.service`：`active` / `enabled`
- `tailscaled.service`：`active` / `enabled`
- `ssh.service`：`active` / `enabled`

### 基础宿主环境

- `docker.service`：`active` / `enabled`
- `NetworkManager.service`：`active` / `enabled`
- `openclaw` 运行用户存在：`uid=997(openclaw) gid=980(openclaw)`

### 审计与监控

- `openclaw.service`：`inactive` / `disabled`
- `openclaw-snapshot.timer`：`active` / `enabled`
- 审计日志存在：`/var/log/openclaw/audit.jsonl`
- 快照日志存在：`/var/log/openclaw/snapshots.jsonl`
- `nftables` 审计表存在：`inet openclaw_audit`

### 运行时 OpenClaw 配置

配置文件：`/var/lib/openclaw/.openclaw/openclaw.json`

- Discord 已启用
- Discord token 已写入
- Discord guild 已限定为 `1483635906819788931`
- Discord channel 已限定为 `1483636573235843072`
- 频道规则：`allow=true`，`requireMention=true`
- 共享 skills 目录已接入：`/var/lib/openclaw/.openclaw/skills`
- 默认模型 OAuth profile 存在：`openai-codex:default`
- OAuth 类型：`oauth`

### 向量后端预配置

- `memory-lancedb` 已预配置为使用：
  - `baseUrl = http://ccnode.briconbric.com:22545/v1`
  - `model = bge-m3:latest`
  - `dbPath = /var/lib/openclaw/.openclaw/memory/lancedb`
- `autoCapture = false`
- `autoRecall = false`

## 已知问题

### 1. root 配置与运行时配置不一致

文件：`/root/.openclaw/openclaw.json`

现状：
- `discord_enabled = true`
- 但无 Discord token
- 无 guild 规则
- 无 channel 规则

影响：
- 不影响 `openclaw` 服务用户实际启动
- 会影响后续以 `root` 手工执行 CLI 时看到的配置一致性

结论：非阻断

### 2. memory-lancedb 尚未接管默认记忆槽

现状：
- `memory-lancedb` 配置已写入
- `plugins.slots.memory` 仍未切换
- 当前默认仍是 `memory-core`

影响：
- 不影响 OpenClaw 启动
- 只意味着长期向量记忆当前不会自动生效

结论：非阻断

### 3. 两个官方插件仍不可用

现状：
- `diffs`：缺少依赖 `@pierre/diffs`
- `diagnostics-otel`：缺少依赖 `@opentelemetry/exporter-metrics-otlp-proto`

影响：
- 不影响 Discord 主工作链路
- 不影响主模型调用
- 会影响 diff 只读渲染能力和 OTEL 导出能力

结论：非阻断

## 启动判断

满足启动条件：
- Discord 主链路已配好
- OAuth 已完成
- 监控与审计链路存在
- 服务当前未启动，符合手动上线策略

建议启动方式：
- 先手动启动 `openclaw.service`
- 启动后仅在 Discord `public` 频道做一次最小化 `@汤猴` 测试
- 首测通过后，再观察审计日志、快照日志和出站计数

## 启动实测补记

首次启动失败，原因不是 OpenClaw 配置错误，而是 systemd 沙箱项与 Node/V8 冲突。

现象：
- `openclaw.service` 启动后立即失败
- `systemctl show` 显示 `Result=signal`
- `journalctl -u openclaw` 显示 Node/V8 fatal error
- 关键报错为：
  - `Check failed: 12 == (*__errno_location ()).`
  - 进程以 `status=5/TRAP` 退出

根因：
- 单元文件中设置了 `MemoryDenyWriteExecute=true`
- Node/V8 在运行时需要可执行内存权限用于 JIT / baseline compilation
- 因此该限制会导致 OpenClaw 进程被直接打死

修复：
- 修改 `/etc/systemd/system/openclaw.service`
- 将：
  - `MemoryDenyWriteExecute=true`
- 改为：
  - `MemoryDenyWriteExecute=false`

修复后结果：
- `systemctl daemon-reload` 后重新启动成功
- `openclaw.service` 已进入 `active/running`

经验结论：
- 后续凡是 Node / V8 类长期服务，不应机械套用 `MemoryDenyWriteExecute=true`
- 该项需要作为 OpenClaw 的已知兼容性例外保留在部署文档中

## 运行目录问题补记

现象：
- 服务启动后 Discord 看起来像“没活着”
- 日志显示默认模型退回
- 实际运行目录落到了 `/var/lib/openclaw/.openclaw/.openclaw`

根因：
- 单元中同时设置了：
  - `HOME=/var/lib/openclaw`
  - `OPENCLAW_HOME=/var/lib/openclaw/.openclaw`
- 当前版本在该组合下会产生错误的嵌套目录解析

修复：
- 从 `/etc/systemd/system/openclaw.service` 中移除：
  - `Environment=OPENCLAW_HOME=/var/lib/openclaw/.openclaw`
- 保留：
  - `Environment=HOME=/var/lib/openclaw`

修复后结果：
- OpenClaw 正确读取 `/var/lib/openclaw/.openclaw/openclaw.json`
- 正确读取 `/var/lib/openclaw/.openclaw/agents/main/agent/auth-profiles.json`
- Discord 状态恢复为 `configured`
- 默认模型恢复为 `gpt-5.4`
- 服务保持 `active/running`

## 常驻稳定性补记

现象：
- 即使配置与工作目录修正后
- `openclaw.service` 仍会在 Discord 登录成功后无规律退出
- 日志表现为 gateway 收到 `SIGTERM`，服务回到 `inactive`

处理方式：
- 增加 supervisor wrapper：
  - `/usr/local/bin/openclaw-gateway-supervise`
- wrapper 以 `HOME=/var/lib/openclaw` 启动 gateway
- 若 gateway 退出，则等待 2 秒后自动拉起
- `systemd` 改为托管 wrapper，而不是直接托管 gateway 命令

验证结果：
- 修复后进行 100 秒驻留观察
- 服务维持 `active/running`
- wrapper、`openclaw`、`openclaw-gateway` 进程链持续存在

## 启动后追加复核

后续继续排障时，又发现了 4 个关键事实：

### 1. 真正打断服务的是旧的 root 用户级网关服务

现象：
- 机器上还残留：
  - `/root/.config/systemd/user/openclaw-gateway.service`
- 该服务由 `systemd --user` 持续自动重启
- 与当前系统级 `openclaw.service` 并行运行

影响：
- 两套服务争用同一条 gateway 生命周期
- 表现为 Discord 刚登录成功，当前服务就收到异常 `SIGTERM`
- 会被误判为“systemd 直跑不稳定”

处理：
- 已停用并移除旧的 root 用户级服务
- 保留当前系统级 `openclaw.service` 作为唯一正式入口

### 2. 运行配置已归一化到正式本地网关形态

修复项：
- 在运行配置中显式写入：
  - `gateway.mode=local`
- 将旧式 Discord 配置：
  - `channels.discord.dm.policy`
  归一为：
  - `channels.discord.dmPolicy`

结果：
- 启动时不再反复提示同一类 doctor 迁移
- gateway / discord 的状态判断更一致

### 3. supervisor 日志写权限已补齐

现象：
- wrapper 尝试写 `/var/log/openclaw/supervisor.log` 时
  遇到只读文件系统错误

处理：
- 已将 `/var/log/openclaw` 补入 `openclaw.service` 的 `ReadWritePaths`

结果：
- 后续若 gateway 异常退出，supervisor 可正常留下重启日志

### 4. 之前的 “@汤猴” 实际打到的是角色，不是 bot

Discord 实测：
- bot 实际用户名：
  - `PKROCOHR001`
- 服务器中存在一个托管角色：
  - `汤猴`
  - 角色 ID：`1483642962377314447`

影响：
- 用户之前多次发送的是：
  - `<@&1483642962377314447> ...`
- 这是角色提及，不是 bot 用户提及
- 因此这些历史消息不能作为“bot 已正确收到 mention”的依据

当前策略：
- `public` 频道已切到允许直接普通文本触发
- 后续优先用普通文本测试，避免角色提及歧义

## 当前运行结论

- 当前 `openclaw.service` 已稳定保持 `active/running`
- Discord gateway 已成功连接
- bot 已可在 `public` 频道主动发消息
- 当前仍缺少 1 个最终收口验证：
  - 需要一条“修复后新发送的人工消息”来确认它已真正进入 OpenClaw 处理链
- 这一步不是权限或服务问题，而是最终交互验证问题

## 长记忆启用补记

后续已按要求将长记忆正式启用，并完成了显性验证。

当前状态：
- `plugins.slots.memory = memory-lancedb`
- `autoCapture = true`
- `autoRecall = true`
- 向量库路径：
  - `/var/lib/openclaw/.openclaw/memory/lancedb`
- embedding 后端：
  - `http://ccnode.briconbric.com:22545/v1`
  - `bge-m3:latest`
  - `dimensions = 1024`

实际暴露出的两个问题：

### 1. 发行包缺少 LanceDB 运行依赖

现象：
- `openclaw ltm stats` 直接失败
- 报错：
  - `Cannot find module '@lancedb/lancedb'`

处理：
- 已在远端 OpenClaw 安装目录补装：
  - `@lancedb/lancedb`

### 2. Node OpenAI SDK 与当前 Ollama embeddings 兼容性异常

现象：
- 原始 HTTP `/v1/embeddings` 实测返回 `1024` 维向量
- 但 `memory-lancedb` 默认使用的 Node `OpenAI` SDK 在本环境里拿到的 embedding 被解析错位
- 表现为 LanceDB 表是 `1024` 维，查询向量却异常变成 `256` 维
- `openclaw ltm search ...` 因此报向量维度不匹配

处理：
- 已对远端文件应用兼容补丁：
  - `/usr/lib/node_modules/openclaw/extensions/memory-lancedb/index.ts`
- 备份：
  - `/usr/lib/node_modules/openclaw/extensions/memory-lancedb/index.ts.bak-20260318`
- 补丁逻辑：
  - 当配置了 `baseUrl` 时，不再走 Node `OpenAI` SDK
  - 直接调用原始 `POST /v1/embeddings`

验证结果：
- `openclaw ltm stats` 正常返回 `Total memories: 0`
- `openclaw ltm search 'I prefer long-term memory with vector recall' --limit 3`
  正常返回 `[]`
- LanceDB 数据目录已落盘
- `journalctl -u openclaw` 已看到：
  - `memory-lancedb: initialized (db: /var/lib/openclaw/.openclaw/memory/lancedb, model: bge-m3:latest)`

结论：
- 长记忆模式已正式启用
- 小模型向量化链路已生效
- 当前还没有真实记忆条目，仅表示“自动捕获与自动召回已经准备就绪，后续满足捕获条件的对话会进入 LanceDB”

## 长记忆入库问题补记

后续继续排障后，已确认“链路已启用但 `Total memories: 0`”的根因不在向量后端，而在 auto-capture 规则本身。

真实根因：
- Discord 用户消息会被包装上：
  - `Conversation info (untrusted metadata)`
  - `Sender (untrusted metadata)`
- 当前版本 `memory-lancedb` 原始触发词几乎只覆盖英文 / 捷克语
- 原始最小捕获长度门槛为 `10`
- 因此中文设定类消息即使很重要，也会在 `shouldCapture()` 前被全部拦掉

已修复：
- 远端插件已加入 `stripConversationMetadata()`
- auto-recall 与 auto-capture 都先清洗 Discord 元数据
- 中文触发词与分类规则已补入
- 最小捕获长度从 `10` 调整为 `6`
- `captureMaxChars` 已调整为 `2000`

显性验证：
- 已做一次受控回填，只处理当前 Discord 会话中满足规则的用户消息
- `openclaw ltm stats` 当前为：
  - `Total memories: 2`
- `openclaw ltm search '东京时间' --limit 5` 已能命中：
  - `对了，咱们对一下表，请你把你的时间对齐为东京时间。`
- 当前 LanceDB 中已知记忆至少包括：
  - `你的名字叫：汤猴`
  - `对了，咱们对一下表，请你把你的时间对齐为东京时间。`
