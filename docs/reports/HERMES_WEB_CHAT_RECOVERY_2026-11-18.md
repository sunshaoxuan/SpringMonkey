# Hermes 网页聊天恢复与亮色主题

日期：2026-11-18，Asia/Tokyo。目标是处理用户反馈的聊天无响应及界面过暗。固定 Hermes v0.23.1 与既有 r2 镜像保持，未改网关账户、模型接口、Discord、主机联网或远程访问。

## 发现与处理

网页终端持续 `retrying`。原生 `gateway_bootstrap.py` 首先返回 `gateway inaccessible: unsafe_control_permissions`，明确指出 `/opt/data/gateway.sock` 为 0660，要求 0600。检查确认该路径为 UID10001 的 socket，管理员 home 为 0700。仅将该 socket 收紧为 0600，保留所有者；未放宽官方发现检查。

随后原生发现返回 `gateway absent: not ready`，直接连接旧 socket 得到 ConnectionRefused，进程列表无运行中的聊天后台。执行官方 bootstrap `--start` 成功取得 attach grant，凭据不进入记录。网页新对话随即显示 `ready` 与 gpt-6.1-sol。

这是旧控制 socket 权限及后台未就绪的组合故障。原部署的 CLI、模型和文件验收没有覆盖完整 GUI 聊天收发，本次补齐该链路。旧历史日志中存在其他 UID/state.db 错误，不能据此认定为本次当前故障，也未为此追加修改。

通过网页内置主题选择器保存 `Nous Blue`，刷新及服务重启后仍有效。未编写或替换 CSS、组件、字体；终端在浅色背景上保留原生金色强调文字。

## 实际验收

| 检查 | 结果与证据 |
| --- | --- |
| 浏览器真实发送 | 中文要求计算 128×7、写文件、读回核对，网页实际发送 |
| 模型与工具 | 网页 gpt-6.1-sol；Execute Code、Write File、Read File 全部成功，最终回复计算896且内容一致 |
| 文件独立核对 | `/workspace/web-chat-acceptance.txt` 实际内容匹配，SHA256 `3801deebe8114ab764e47f9e48018a1ac6236046cd0afa2dcd7e3c6ceed2d3a7` |
| 重启恢复 | 一次 dashboard 容器重启后，网页自行启动后台并进入ready；新建socket为10001/0600 |
| 主题持久化 | raw config dashboard.theme=nous-blue；刷新及重启后亮色显示保留 |
| 公网认证 | status auth_required=true/providers=[nous]；匿名config401 |
| 原约束 | main=gpt-6.1-sol；auxiliary原关闭项保持，余槽auto；MoA trace=false；Discord未启用 |
| 资源和发布 | 原image ID `sha256:598f0583092e6d0f3441d33c3951af83da01e2ceb2b79f11d4000b0ef0c01723`；dashboard1GiB、CLI3GiB；OOM=false；管理端口仍127.0.0.1:9119 |

网页真实响应与文件内容构成收发及工具验收，原生state.db同时确认该会话model=gpt-6.1-sol。已通过的 CLI/MoA/Skills 测试未重复执行。此批只做运行状态修复及原生主题设置，无镜像构建或代码迁移。[脱敏验收摘要](evidence/hermes-web-chat-20261118/ACCEPTANCE.json)，[重启后恢复历史对话的实际截图](evidence/hermes-web-chat-20261118/chat-light.png)。

重启后服务启动期间曾短暂返回502，待服务就绪后刷新恢复。冷启动可能需要几十秒。原官方390px移动端布局问题仍保留，本批未修复或重新宣称移动端视觉通过；无新增UI代码，未执行全套控件几何、前端控制台及响应式回归。

## 使用与回滚

[最短使用说明](../ops/HERMES_QUICK_START.md)。[当前聊天入口](https://sm.briconbric.com/chat?profile=default)。主题在左下调色盘切换，可随时改回原来的Hermes Teal。socket保持官方要求0600，勿用递归权限命令将其改成组可读写。聊天后台由原生启动机制管理，服务重启恢复已实测。

当前界面属于可信管理员，和独立UID10000的CLI具有不同权限，不应把管理页面的聊天能力当作多用户安全隔离。无需接入Discord即可直接在网页交互。

官方依据：[Dashboard 与聊天机制](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)，[主题定义](https://github.com/NousResearch/hermes-agent/blob/main/web/src/themes/presets.ts)。
