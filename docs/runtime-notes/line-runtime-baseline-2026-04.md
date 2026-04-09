# LINE 运行基线（2026-04）

用途：记录汤猴当前 LINE 接入的可恢复事实，避免以后只凭脚本名和聊天记录猜现场。

本文关注：

- LINE 通道在 OpenClaw 内的配置形态
- Webhook 如何到达宿主机
- `dmPolicy`、pairing / open 两种模式的区别
- LINE 与 Discord 的共享能力边界
- 宿主机被覆盖时的最小恢复顺序

## 1. 当前接入形态

汤猴的 LINE 不是独立服务，而是 OpenClaw 同一个 gateway 进程中的一个 channel。

这意味着：

- LINE 和 Discord 共用同一个 `openclaw.service`
- 共用同一个 `openclaw.json`
- 共用同一个长期记忆池
- 共用同一套全局 provider 能力与 secret 入口

但以下内容仍然是 LINE 自己独有的接入参数：

- `channels.line.enabled`
- `channels.line.dmPolicy`
- `channels.line.tokenFile`
- `channels.line.secretFile`
- LINE Webhook 的公网入口与回调配置

## 2. 宿主机配置要点

LINE 关键配置位于宿主机：

- `/var/lib/openclaw/.openclaw/openclaw.json`

当前基线应至少满足：

- `channels.line.enabled = true`
- `channels.line.tokenFile = "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt"`
- `channels.line.secretFile = "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt"`

`dmPolicy` 有两种常见值：

- `pairing`
  - 适合首次接入或重新配对
  - 用户需要输入 pairing code 完成绑定
- `open`
  - 适合已经接通后的日常使用
  - 允许已接入用户直接对话

这两种模式都不是“能力开关”，只是接入和会话开放策略。

## 3. 密钥与文件位置

LINE 密钥不进 Git，当前约定写在宿主机：

- `/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt`
- `/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt`

仓库内只保留写入脚本，不保存真实 secret。

相关脚本：

- `scripts/push_line_credentials_remote.py`
- `scripts/remote_line_apply_secrets.sh`

## 4. Webhook 入口

OpenClaw 本机监听的 LINE Webhook 路径是：

- `http://127.0.0.1:18789/line/webhook`

这只是宿主机 loopback 入口，LINE 官方平台不能直接访问。

所以公网链路必须额外提供：

1. 外部 HTTPS 域名
2. 反代到 ccnode / frps 暴露的 TCP 端口
3. frpc 把公网端口映射回宿主机 `127.0.0.1:18789`

本仓库当前采用的辅助脚本：

- `scripts/remote_frpc_line_webhook_map.py`
- `scripts/remote_diag_frpc_tunnel.py`
- `scripts/remote_cat_frpc_config.py`

重要事实：

- `remotePort` 在 frps / ccnode 上监听，不会直接出现在汤猴本机 `ss -ltnp`
- 汤猴本机只能看到 localPort，例如 `127.0.0.1:18789`

## 5. 插件与接通顺序

LINE 通道本身依赖插件：

- `@openclaw/line`

若插件缺失或 manifest 异常，先修插件，再推密钥。

推荐顺序：

1. 安装 / 修复插件
2. 写入 token / secret
3. 检查 `channels.line.enabled`
4. 确认 Webhook 公网链路
5. 按需要切换 `dmPolicy`

相关脚本：

- `scripts/remote_install_line_plugin_fix.py`
- `scripts/push_line_credentials_remote.py`
- `scripts/remote_line_force_open.py`
- `scripts/remote_line_connect_now.py`
- `scripts/remote_line_pairing_approve.py`

## 6. `dmPolicy` 运维约定

### 6.1 `pairing`

适合：

- 首次接入
- 重新绑定用户
- 需要明确授权后才开放会话

相关脚本：

- `scripts/remote_line_pairing_approve.py`

### 6.2 `open`

适合：

- 已完成接入后的正常使用
- 允许用户直接与汤猴会话

相关脚本：

- `scripts/remote_line_force_open.py`
- `scripts/remote_line_connect_now.py`

### 6.3 结论

`pairing` 与 `open` 的切换只影响“谁可以开始聊天”，不影响：

- Brave / web / browser / exec 等共享能力
- 长期记忆共享
- 定时任务的 delivery 目标

## 7. LINE 与 Discord 的共享边界

### 7.1 共享的

- 同一个 gateway 进程
- 同一个 `openclaw.json`
- 同一个长期记忆池
- 同一套全局 provider secret
- 同一套联网 / 浏览器 / exec / process 能力
- 同一套聊天主模型基线

### 7.2 不共享的

- Discord token 与 LINE token/secret
- LINE Webhook 回调链路
- 当前 channel 的短期 session 历史
- 各任务的 `delivery.channel` 与 `delivery.to`

所以：

- 长记忆可以共享
- 但一个在 LINE 建的 cron 任务，只要 `delivery.channel = line`，就不应投到 Discord

## 8. 当前能力口径

为了避免 LINE 会话沿用旧认知，runtime `TOOLS.md` 已明确写入：

- LINE 可以使用 `web_search`
- LINE 可以使用 `web_fetch`
- LINE 可以使用 `browser`
- LINE 可以使用 `exec` / `process`
- 若 browser 本轮失败，只能说明“本轮失败”，不能说“我没有上网能力”

刷新脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py capability-awareness`

## 9. 最小恢复顺序

如果宿主机被覆盖，LINE 恢复建议顺序：

1. 宿主机 `git pull`
2. 跑共享能力基线：`shared-capabilities`
3. 修 LINE 插件：`line-install`
4. 推 LINE 密钥：`line-push`
5. 校验本机 `/line/webhook`
6. 配置或诊断 frpc 映射：`frpc-line` / `frpc-diag`
7. 根据需要切到：
   - `pairing`：走 pairing approve
   - `open`：走 `line-connect` 或 `remote_line_force_open.py`
8. 若需要联网/浏览器能力，再按宿主机总基线恢复 browser 能力

## 10. 相关脚本

- `scripts/remote_install_line_plugin_fix.py`
- `scripts/push_line_credentials_remote.py`
- `scripts/remote_line_openclaw_setup.sh`
- `scripts/remote_line_apply_secrets.sh`
- `scripts/remote_frpc_line_webhook_map.py`
- `scripts/remote_diag_frpc_tunnel.py`
- `scripts/remote_cat_frpc_config.py`
- `scripts/remote_line_pairing_approve.py`
- `scripts/remote_line_force_open.py`
- `scripts/remote_line_connect_now.py`
- `scripts/remote_diag_line_support.py`
- `scripts/openclaw_remote_cli.py`

## 11. 参照

- `docs/runtime-notes/openclaw-runtime-baseline-2026-04.md`
- `docs/ops/TOOLS_REGISTRY.md`
- `docs/CAPABILITY_INDEX.md`
