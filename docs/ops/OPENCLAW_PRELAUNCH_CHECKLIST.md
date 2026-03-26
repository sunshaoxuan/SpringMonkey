## OpenClaw 启动前检查清单

用途：在每次准备启动 `OpenClaw` 前，按本清单逐项复核环境，确认无误后再启动。

---

## 1. 远程入口

- [ ] `frpc` 可用
- [ ] `tailscale` 可用
- [ ] 当前主机登录信息已记录在 [HOST_ACCESS.md](/c:/tmp/default/HOST_ACCESS.md)
- [ ] 已确认当前控制链路是否为同网段直连
- [ ] 已确认当前控制链路是否经过 `frpc` / `Tailscale` 绕行
- [ ] 已知晓“SSH 变慢不等于主机变慢”
- [ ] 已确认本轮操作不会触发 Tailscale 认证态变化
- [ ] 未经明确授权，不执行任何会弹出 Tailscale 验证页的命令

---

## 2. OpenClaw 安装与模型

- [ ] OpenClaw 已安装
- [ ] ChatGPT 订阅 OAuth 已完成
- [ ] 默认模型为 `openai-codex/gpt-5.4`
- [ ] 默认思考强度为 `low`

---

## 3. 运行权限

- [ ] OpenClaw 不以 `root` 运行
- [ ] OpenClaw 使用独立系统用户 `openclaw`
- [ ] OpenClaw 对自己的工作目录具有正常读写权限
- [ ] OpenClaw 对 OAuth/token 刷新所需状态具有写权限
- [ ] OpenClaw 无权修改 `systemd`
- [ ] OpenClaw 无权修改 `nftables/iptables`
- [ ] OpenClaw 无权修改 root 侧审计脚本
- [ ] OpenClaw 无权修改 root 侧审计日志

---

## 4. 服务状态

- [ ] `openclaw.service` 已存在
- [ ] `openclaw.service` 当前为 `disabled`
- [ ] `openclaw.service` 当前为 `inactive`
- [ ] 在明确启动前，不允许自启

---

## 5. 审计与监控

- [ ] 审计日志存在：`/var/log/openclaw/audit.jsonl`
- [ ] 快照日志存在：`/var/log/openclaw/snapshots.jsonl`
- [ ] `openclaw-snapshot.timer` 已启用
- [ ] `openclaw-snapshot.timer` 正在运行
- [ ] `nftables` 已对 `openclaw` 用户出站流量计数
- [ ] 当前监控为系统机械采集，不依赖 AI 决策

---

## 6. Discord 接入

- [ ] Discord bot 已加入服务器 `PKROCOHR001`
- [ ] Bot Token 已写入 OpenClaw 配置
- [ ] 服务器 ID 已配置：`1483635906819788931`
- [ ] 频道 ID 已配置：`1483636573235843072`
- [ ] 当前只允许 `public` 频道作为控制入口
- [ ] 当前规则为：`public` 频道允许直接普通文本触发
- [ ] 已知 `汤猴` 是 Discord 托管角色，不是 bot 用户提及
- [ ] 测试时不得把 `<@&1483642962377314447>` 误当成 bot mention
- [ ] 当前规则为：频道外不响应

---

## 7. 风险边界

- [ ] 允许 OpenClaw 正常联网工作
- [ ] 不允许 OpenClaw 越权修改监控与系统层设置
- [ ] 当前未授予额外高危权限
- [ ] 如需新增权限，必须按任务逐项评估

---

## 8. 关联文档

- [ ] 主机与入口信息已记录在 [HOST_ACCESS.md](/c:/tmp/default/HOST_ACCESS.md)
- [ ] 监控规划已记录在 [OPENCLAW_MONITORING_PLAN.md](/c:/tmp/default/OPENCLAW_MONITORING_PLAN.md)
- [ ] Skills 审查清单已记录在 [OPENCLAW_SKILLS_REVIEW_QUEUE.md](/c:/tmp/default/OPENCLAW_SKILLS_REVIEW_QUEUE.md)
- [ ] Ollama embedding 测试报告已记录在 [OLLAMA_EMBEDDING_TEST_REPORT.md](/c:/tmp/default/OLLAMA_EMBEDDING_TEST_REPORT.md)
- [ ] 统一向量后端方案已记录在 [OPENCLAW_VECTOR_BACKEND_PLAN.md](/c:/tmp/default/OPENCLAW_VECTOR_BACKEND_PLAN.md)
- [ ] 长记忆未入库排障记录已记录在 [OPENCLAW_LTM_ROOTCAUSE_2026-03-18.md](/c:/tmp/default/OPENCLAW_LTM_ROOTCAUSE_2026-03-18.md)
- [ ] 文档中未记录高敏感机密（Token / API key / OAuth access / refresh token）

---

## 9. Skills / Plugins

- [ ] 共享 skills 目录已存在：`/var/lib/openclaw/.openclaw/skills`
- [ ] `skills.load.extraDirs` 已指向共享 skills 目录
- [ ] 当前优先使用内置 / 官方能力
- [ ] Discord 官方插件已启用
- [ ] `lobster` 官方插件已启用并可加载
- [ ] `llm-task` 官方插件已启用并可加载
- [ ] `diffs` / `diagnostics-otel` 的依赖状态已复核
- [ ] `memory-lancedb` 是否接管默认记忆槽已明确决定
- [ ] `memory-lancedb` 的统一向量后端预配置已写入远端
- [ ] `memory-lancedb` 已实际接管默认 `memory` 槽位
- [ ] `memory-lancedb` 已启用 `autoCapture=true`
- [ ] `memory-lancedb` 已启用 `autoRecall=true`
- [ ] `memory-lancedb` 已明确配置 `dimensions=1024`
- [ ] `memory-lancedb` 已明确配置 `captureMaxChars=2000`
- [ ] `memory-lancedb` 已应用 Discord 元数据清洗逻辑
- [ ] `memory-lancedb` 的中文触发词已复核，不再只依赖英文 / 捷克语
- [ ] 远端已补装 `@lancedb/lancedb`
- [ ] `openclaw ltm stats` 可正常返回
- [ ] `openclaw ltm search ...` 可正常返回且不报维度错误
- [ ] `openclaw ltm stats` 已大于 `0`，确认自动入库链路真实工作
- [ ] 未经审查的社区 skill 未安装到生产目录
- [ ] 新增社区 skill 前必须完成逐项审核
- [ ] 已安装的第三方 skill 已逐项补记到 [OPENCLAW_SKILLS_REVIEW_QUEUE.md](/c:/tmp/default/OPENCLAW_SKILLS_REVIEW_QUEUE.md)
- [ ] 已安装的第三方 skill 已逐项补记到本清单
- [ ] 已安装第三方 skills：
  - `git-essentials`
  - `notion`
  - `openclaw-backup`
  - `calendar`
- [ ] 每次新增或更新 skill 后，重新执行一次启动前检查

当前远端实况补记：

- 官方 plugins 当前配置为 `enabled=true`：
  - `discord`
  - `memory-lancedb`
  - `lobster`
  - `llm-task`
  - `diffs`
  - `diagnostics-otel`
- 当前真正可正常工作：
  - `discord`
  - `memory-lancedb`
  - `lobster`
  - `llm-task`
- 当前配置已启用但运行时加载失败：
  - `diffs`
  - `diagnostics-otel`
- 当前共享第三方 skills：
  - `calendar`
  - `git-essentials`
  - `notion`
  - `openclaw-backup`

---

## 启动后首测

- [ ] `openclaw.service` 启动成功
- [ ] Discord 中 `@汤猴` 有响应
- [ ] 仅在 `public` 频道响应
- [ ] 审计日志中出现启动记录
- [ ] 快照日志中能看到进程与网络活动
- [ ] 无异常高频请求
- [ ] 无异常出站目标

---

## 复核建议

- 每次正式启动前，完整检查一次本清单
- 每次修改权限边界后，重新检查第 3、5、7 项
- 每次修改 Discord 接入后，重新检查第 6 项
- 每次模型或认证变更后，重新检查第 2 项
## 启动后补充约束

- `openclaw.service` 的 systemd 沙箱配置不得设置 `MemoryDenyWriteExecute=true`
- 原因：OpenClaw 基于 Node/V8，运行时需要可执行内存
- 若误设该项，服务会在启动时以 `TRAP` 失败
- `openclaw.service` 只保留 `HOME=/var/lib/openclaw`
- 不得再写 `OPENCLAW_HOME=/var/lib/openclaw/.openclaw`
- 原因：会诱发错误的嵌套运行目录 `.openclaw/.openclaw`
- `openclaw.service` 不再直接 `ExecStart=/usr/bin/openclaw gateway run ...`
- 当前稳定形态应为 `ExecStart=/usr/local/bin/openclaw-gateway-supervise`
- supervisor 日志位于：
  - `/var/log/openclaw/supervisor.log`
- 运行配置中必须显式包含：
  - `gateway.mode=local`
- Discord 配置必须使用：
  - `channels.discord.dmPolicy`
- 不应再保留：
  - `channels.discord.dm.policy`
- 机器上不得再保留旧的 root 用户级服务：
  - `/root/.config/systemd/user/openclaw-gateway.service`
- `openclaw.service` 的 `ReadWritePaths` 必须包含：
  - `/var/log/openclaw`
- `memory-lancedb` 的显性验证应优先使用：
  - `openclaw ltm stats`
  - `openclaw ltm search ...`
- 不应仅凭：
  - `openclaw memory status`
  来判断 `memory-lancedb` 是否接管成功
- 未经明确授权，禁止执行：
  - `tailscale up`
  - `tailscale login`
  - `tailscale logout`
  - `tailscale set ...`
  - `tailscale serve ...`
  - `tailscale funnel ...`
