## OpenClaw 运行与监控规划

目标：`OpenClaw` 不以 `root` 运行；监控与审计由系统侧机械执行；与 root 侧维护任务分层。

### 当前状态

- 运行用户：`openclaw`
- 服务：`openclaw.service`
- 当前服务状态：`disabled` + `inactive`
- 周期快照：`openclaw-snapshot.timer`
- 当前快照定时器状态：`enabled` + `active`
- OpenClaw 运行目录：`/var/lib/openclaw/.openclaw`
- 审计日志目录：`/var/log/openclaw`
- root 侧维护日志目录：`/var/log/openclaw-maint`

### 权限边界

- `OpenClaw` 不使用 `root`
- `OpenClaw` 以 `openclaw` 用户运行
- 审计日志由 `root` 侧脚本写入
- 周期采样由 `systemd timer` 执行
- 出站网络计数由 `nftables` 完成

### 已部署组件

- `openclaw.service`
  - 手动型服务
  - 默认不自启
  - `User=openclaw`
  - `ProtectSystem=strict`
  - `NoNewPrivileges=true`

- `openclaw-snapshot.service`
  - `root` 执行
  - 负责采集运行状态和网络快照

- `openclaw-snapshot.timer`
  - 开机 2 分钟后首次执行
  - 之后每 5 分钟执行一次

- `openclaw-audit-log`
  - 记录启动/停止/维护事件
  - 输出到 `/var/log/openclaw/audit.jsonl`

- `openclaw-update.service`
  - `root` 执行
  - 负责检查可用更新并在有更新时执行全局升级
  - 升级后重启 `openclaw.service` 并做最小自检

- `openclaw-update.timer`
  - 每日运行
  - root 侧维护链，不走 agent 自更新

- `nftables`
  - 表：`inet openclaw_audit`
  - 规则：按 `openclaw` 用户统计出站流量

### 日志文件

- `/var/log/openclaw/audit.jsonl`
  - 记录人工动作和服务生命周期事件

- `/var/log/openclaw/snapshots.jsonl`
  - 记录周期性快照
  - 包含：
    - 服务是否运行
    - 服务是否启用
    - `pgrep`
    - `ss -tpn`
    - `nft` 规则与计数

- `/var/log/openclaw-maint/`
  - 记录 root 侧自动更新检查与升级日志

### 机械采样原则

- 不调用 AI
- 不做智能判断
- 不自动放行
- 只按固定规则收集事实数据

### 链路说明

- 当前远程维护可能依赖：
  - `frpc` 映射
  - `Tailscale` 虚拟地址
- 当运维端不在目标主机同网段时，控制链路可能明显变长
- 因此监控解读时必须区分：
  - 远程控制通道延迟
  - 主机本地负载
  - OpenClaw 自身工作负载
- 不应仅凭 SSH 变慢就判断 OpenClaw 或主机异常

### 文档原则

- 尽可能记录完整的环境说明、限制条件和运维决策
- 不记录高敏感机密：
  - Token
  - OAuth access / refresh token
  - API key
- 对需要长期维护的拓扑、服务、权限、入口和链路约束，应优先补全文档

### 后续可选增强

1. 增加专用出站白名单
2. 将日志异地同步到另一台主机
3. 对敏感日志做追加写或更严格权限控制
4. 为启动动作增加显式审批脚本
5. 将 `OpenClaw` 的可写目录进一步缩小
6. 对外暴露的 Ollama / embedding 服务增加访问收口或鉴权

## 2026-03-26 运行与维护补充

- 当前 `tools.exec` 已提升为任务域优先：
  - `host = gateway`
  - `security = full`
  - `ask = off`
- 目的：
  - 减少任务域内 `apply / verify / git` 链路的无意义审批

- 当前 `tools.elevated` 保留：
  - `enabled = true`
  - `allowFrom.discord = ["*"]`
- 但本轮排障已确认：
  - `tools.elevated.defaultLevel` 不属于当前版本公开配置 schema
  - 再次写入会触发 crash loop

- 为兼容当前版本的 Discord elevated exec 行为，远端已存在一个最小运行时补丁：
  - `/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js`
  - 备份：`/usr/lib/node_modules/openclaw/dist/auth-profiles-DRjqKE3G.js.bak-20260326-elevated-full`

- 当前新闻播报已经切换到任务域治理：
  - `config/news/broadcast.json`
  - `scripts/news/apply_news_config.py`
  - `scripts/news/verify_news_config.py`
  - `docs/runtime-notes/news-task-domain.md`
- 这类任务今后应优先修改任务域，而不是手改底层 `jobs.json`

### 新闻播报链路现状

- OpenClaw 当前已具备定时新闻播报能力
- 正式任务：
  - `08:30 JST` 汇总过去 `16` 小时
  - `16:30 JST` 汇总过去 `8` 小时
- 投递目标：
  - Discord `public` 频道

- 当前链路按优先级分为：
  1. `web_search`
  2. `browser`
  3. 公开 RSS / 网页抓取兜底

- 当前已知降级项：
  - `web_search` 缺少 Brave API key
  - `browser` 在当前 Gateway 形态下仍可能超时
  - `web_fetch` 仍可能被外部内容安全门拦截

- 当前已验证结果：
  - cron 自检：已成功投递
  - 新闻烟测：已成功投递
  - 即使上层工具有降级，任务仍可由兜底路径完成

### 常用命令

查看服务状态：

```bash
systemctl status openclaw.service --no-pager
systemctl status openclaw-snapshot.timer --no-pager
```

查看审计日志：

```bash
tail -n 50 /var/log/openclaw/audit.jsonl
tail -n 20 /var/log/openclaw/snapshots.jsonl
```

查看出站计数：

```bash
nft list table inet openclaw_audit
```

手动执行一次快照：

```bash
systemctl start openclaw-snapshot.service
```

手动启动 OpenClaw：

```bash
systemctl start openclaw.service
```

手动停止 OpenClaw：

```bash
systemctl stop openclaw.service
```

### 当前结论

- 现在可以继续评估要给 `OpenClaw` 哪些额外权限
- 在你明确下令前，不应启动 `openclaw.service`
## 已知运行兼容性

- `OpenClaw` 基于 Node/V8
- 在 systemd 沙箱下运行时，`MemoryDenyWriteExecute=true` 会导致进程启动失败
- 该问题表现为：
  - 服务启动即退出
  - `journalctl -u openclaw` 出现 V8 fatal error
  - `systemctl` 显示 `Result=signal` 或 `status=5/TRAP`
- 因此该服务单元应明确保留：
  - `MemoryDenyWriteExecute=false`
- 这属于兼容性要求，不属于权限放宽失控

## 已知运行目录约束

- `openclaw.service` 应只设置：
  - `HOME=/var/lib/openclaw`
- 不应再额外设置：
  - `OPENCLAW_HOME=/var/lib/openclaw/.openclaw`
- 原因：
  - 当前版本在该组合下会把实际运行目录错误解析为
    `/var/lib/openclaw/.openclaw/.openclaw`
  - 结果会导致服务读取到一套空白运行配置
  - 表现为 Discord 不挂载、默认模型退回、OAuth/profile 不生效
- 这是已实测问题，后续不得恢复该环境变量

## 已知常驻运行约束

- 当前版本直接以 `systemd` 执行：
  - `openclaw gateway run ...`
  存在非稳定退出现象
- 现象：
  - Discord 登录成功后，gateway 仍会收到 `SIGTERM`
  - 服务会在无显式崩溃的情况下掉回 `inactive`
- 已采用的稳定方案：
  - 由 `systemd` 托管一个外层 supervisor wrapper
  - wrapper 路径：`/usr/local/bin/openclaw-gateway-supervise`
  - wrapper 负责拉起：
    `openclaw gateway run --allow-unconfigured --bind loopback --verbose --ws-log compact`
  - 若 gateway 退出，wrapper 在 2 秒后自动重拉
- 当前 `openclaw.service` 管理的是 supervisor，而不是直接管理 `openclaw gateway run`
- 这属于为了长期在线而做的运行层补偿，不改变 OpenClaw 的权限边界

## 已知运行冲突

- 机器上曾存在一套旧的 root 用户级服务：
  - `/root/.config/systemd/user/openclaw-gateway.service`
- 该服务会在 `systemd --user` 下持续自动重启
- 它会与当前系统级 `openclaw.service` 并行争用 gateway 生命周期
- 实测表现：
  - Discord provider 刚启动成功后，当前服务就收到异常 `SIGTERM`
  - 现象会被误判成“OpenClaw 不稳定”或“Discord 没活着”
- 当前处理要求：
  - 保持该 root 用户级服务处于移除状态
  - 后续不得再恢复旧的 user service 形态

## 已知配置归一化要求

- `gateway.mode` 必须显式为 `local`
- Discord 配置应使用：
  - `channels.discord.dmPolicy`
- 不应继续保留旧式：
  - `channels.discord.dm.policy`
- 原因：
  - 否则每次启动都会出现 doctor 迁移提示
  - 会增加排障噪音，干扰真实问题判断

- 若继续使用 `/usr/local/bin/openclaw-gateway-supervise`
  - `openclaw.service` 的 `ReadWritePaths` 必须包含 `/var/log/openclaw`
- 原因：
  - supervisor 需要向 `/var/log/openclaw/supervisor.log` 记录异常重启
  - 若未授权写入，会制造额外失败噪音

## 长记忆与向量后端现状

- 当前长记忆槽位已切换为：
  - `plugins.slots.memory = memory-lancedb`
- 当前策略已启用：
  - `autoCapture = true`
  - `autoRecall = true`
- 当前向量库路径：
  - `/var/lib/openclaw/.openclaw/memory/lancedb`
- 当前 embedding 后端：
  - `http://ccnode.briconbric.com:22545/v1`
  - `bge-m3:latest`
  - `dimensions = 1024`
- 当前 `captureMaxChars = 2000`

- 需要特别注意：
  - `openclaw memory ...` 主要反映的是旧的 builtin/file-backed memory CLI
  - 真正针对 `memory-lancedb` 的显性验证命令应使用：
    - `openclaw ltm stats`
    - `openclaw ltm search ...`

## 长记忆未入库的已知根因与修复

- 已实测的根因不是向量链路故障，而是 auto-capture 过滤过严：
  - Discord 用户消息会带 `Conversation info / Sender` 元数据包装
  - 当前版本原始 `MEMORY_TRIGGERS` 几乎只覆盖英文 / 捷克语
  - 原始最小捕获长度门槛会吞掉短中文设定

- 远端已应用的修复：
  - 在 `memory-lancedb` 插件内新增 `stripConversationMetadata()`
  - `before_agent_start` 与 `agent_end` 都先清洗 Discord 元数据
  - 中文触发词已扩展到：
    - `记住`
    - `偏好`
    - `以后`
    - `默认`
    - `统一`
    - `改成`
    - `对齐`
    - `名字是`
    - `名字叫`
    - `东京时间`
    - `JST`
  - 最小捕获长度从 `10` 降到 `6`
  - `captureMaxChars` 提升到 `2000`

- 显性验证结果：
  - `openclaw ltm stats` 已从 `0` 变为 `2`
  - `openclaw ltm search '东京时间' --limit 5` 已命中长期记忆
  - 当前已受控回填 2 条记忆：
    - `你的名字叫：汤猴`
    - `对了，咱们对一下表，请你把你的时间对齐为东京时间。`

## Ollama 兼容补丁说明

- 远端已补装：
  - `@lancedb/lancedb`
- 否则 `memory-lancedb` 只能注册，不能真正初始化或查询

- 远端已对以下文件应用兼容补丁：
  - `/usr/lib/node_modules/openclaw/extensions/memory-lancedb/index.ts`
- 备份文件：
  - `/usr/lib/node_modules/openclaw/extensions/memory-lancedb/index.ts.bak-20260318`

- 原因：
  - 当前 `memory-lancedb` 默认通过 Node `OpenAI` SDK 对接 Ollama 兼容 embeddings 接口
  - 在本环境里该 SDK 会把 Ollama 返回的 embedding 解析错位
  - 表现为：
    - LanceDB 表维度是 `1024`
    - SDK 侧拿到的查询向量却错误为 `256`
    - 导致 `ltm search` 报维度不匹配

- 当前处理：
  - 当 `baseUrl` 存在时，补丁改为直接调用原始 `POST /v1/embeddings`
  - 这样能拿到真实 `1024` 维向量
  - 已经完成显性验证：
    - `openclaw ltm stats` 正常返回
    - `openclaw ltm search ...` 正常返回 `[]`
    - 不再报 LanceDB 维度错误

## Discord 入口识别说明

- 当前 bot 的实际 Discord 用户名是：
  - `PKROCOHR001`
- 当前服务器中还有一个托管角色：
  - `汤猴`
- 该角色提及格式为：
  - `<@&1483642962377314447>`
- 这不是 bot 用户提及
- 因此监控和人工测试时必须区分：
  - 角色提及
  - bot 用户提及
  - 普通文本消息
- 当前 `public` 频道已配置为允许直接普通文本触发，优先用普通文本测试，避免角色提及混淆

## 定时播报自动化现状

- `OpenClaw` 已自行研究到可行路径：
  - 使用内置 `openclaw cron` 调度
  - 目标是为 Discord 频道创建定时新闻播报任务

- 当前不是“还在摸索”，而是卡在明确权限点：
  - `/var/lib/openclaw/.openclaw/identity/device.json`
  - 当前仍为 `root:root`
  - 权限为 `600`
  - 因此 `openclaw` 用户调用 `openclaw cron ...` 时会报：
    - `EACCES: permission denied, open '/var/lib/openclaw/.openclaw/identity/device.json'`

- 当前验证结果：
  - `openclaw cron list --json` 仍失败
  - `/var/lib/openclaw/.openclaw/cron/jobs.json` 当前内容为：
    - `jobs: []`
  - 也就是：
    - 方案已找到
    - 但定时任务尚未真正创建

- 若要继续让其自行落地，需要的不是新模型能力，而是二选一：
  1. 修正 `identity/` 目录及相关身份文件的属主/权限，使 `openclaw` 可读
  2. 或开启允许 Discord provider 使用 elevated exec

- 当前实际状态更新：
  - `identity/` 目录现已整体修正为 `openclaw:openclaw`
  - `tools.elevated.enabled = true`
  - `tools.elevated.allowFrom.discord = ["*"]`
  - 原先的 `EACCES` 已解除
  - 但 `openclaw cron list --json` 仍未成功，现阶段剩余问题变为：
    - Gateway RPC timeout / abnormal closure
    - 也就是：
      - 权限门已打开
      - cron 自治链路仍未完全打通
  - 当前这是明确的高风险放宽：
    - Discord 来源的 elevated allowlist 使用了通配 `["*"]`
    - 这样做是为了避免“简单情报采集 + 定时发送”任务继续被权限门反复卡住

## Tailscale 探测限制

- Tailscale 现在是受保护远程入口，不只是普通网络工具
- 因此排障和监控时必须遵守：
  - 不得为了“顺手验证”去运行任何可能触发重新认证、重新授权、重新暴露的命令

- 未经明确指令，禁止：
  - `tailscale up`
  - `tailscale login`
  - `tailscale logout`
  - `tailscale set ...`
  - `tailscale serve ...`
  - `tailscale funnel ...`
  - 其他可能弹出网页登录/验证页的动作

- 默认允许：
  - 读取现有状态
  - 使用既有 Tailscale IP 做普通 SSH
  - 不改变节点认证态的基础连通性探测

- 若再次观察到 Tailscale 验证页被触发：
  - 立即停止相关探测
  - 先按事故处理
  - 再回查是哪条命令触发
