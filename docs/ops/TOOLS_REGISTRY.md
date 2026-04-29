# 工具注册表：设计原则、场景分裂与参数约定

**用途**：把「可复用能力」写成稳定契约，避免每次任务从零写脚本。  
**配套**：`scripts/INDEX.md`（脚本清单）、`scripts/openclaw_remote_cli.py`（统一入口）。

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **先登记、后实现** | 新能力先在本表与 `INDEX.md` 增一行，再写脚本。 |
| **按场景分裂** | 诊断、修复、安装插件、写入密钥应是**不同脚本**或不同子命令，避免一个巨型脚本里塞满 `if`。 |
| **参数外置** | 主机、端口、密码、LINE token 一律**环境变量或 CLI 显式参数**，**禁止**写进仓库。 |
| **可组合** | 复杂流程 = 多个小工具按固定顺序调用（见下「推荐流水线」），而不是复制粘贴远程 shell。 |
| **单一职责** | 每个脚本只做一件事；需要「一键恢复」时用 CLI 的 `recover` 组合，而不是把逻辑再抄一遍。 |

---

## 2. 场景 → 工具映射（远程 OpenClaw / 宿主机）

| 场景 | 症状或目标 | 工具（脚本） | 必备环境变量 / 参数 |
|------|------------|--------------|---------------------|
| 通用定时任务落地 | 普通 recurring task 需要真的落进 cron，而不是只在对话里宣称“已创建” | `cron/upsert_generic_cron_job.py` | `--name`、`--expr`、`--message-file/--message`、`--delivery-channel`、`--delivery-to` |
| 宿主机同步仓库 | 本地已 push，需要在汤猴机上 `git pull` | `remote_springmonkey_git_pull.py` | `OPENCLAW_SSH_PASSWORD`；可选 `OPENCLAW_RESTART_AFTER_PULL=1`、`SPRINGMONKEY_REPO_PATH` |
| 健康检查 | 不知服务是否活着、端口是否监听 | `remote_diag_openclaw_webhook.py` | `OPENCLAW_SSH_PASSWORD` |
| 配置迁移 | `Config invalid`、`legacy`、`doctor --fix` | `remote_openclaw_doctor_fix.py` | 同上 |
| 共享能力基线 | 让 Discord / LINE 共用同一套全局能力与 secret 入口 | `remote_enable_shared_channel_capabilities.py` | `OPENCLAW_SSH_PASSWORD` |
| 浏览器 / 出网能力加固 | 修复 Node TLS 证书链，安装 `xvfb` + Playwright，固化 browser 基线 | `remote_enable_browser_capabilities.py` | `OPENCLAW_SSH_PASSWORD` |
| 常驻浏览器后端 | 拉起 raw CDP Chrome backend，供 OpenClaw `browser` 工具长期复用 | `remote_enable_persistent_browser_backend.py` | `OPENCLAW_SSH_PASSWORD` |
| 浏览器守护规则 | 安装哨兵标签、标签阈值与内存阈值守护，避免常驻浏览器失控 | `remote_install_browser_guardrails.py` | `OPENCLAW_SSH_PASSWORD` |
| 真实浏览器 CDP 自修复 helper | `browser` 工具出现 `targetId` / tab / ref 漂移，或模型误称需要用户打开本机浏览器 | `remote_install_browser_human_control_helper.py`（部署） + `openclaw/helpers/browser_cdp_human.py`（运行时 helper） | `OPENCLAW_SSH_PASSWORD` |
| 能力认知刷新 | 更新 runtime 注入提示，让模型按当前宿主机能力说话 | `remote_refresh_capability_awareness.py` | `OPENCLAW_SSH_PASSWORD` |
| 长记忆修复 | 修复 `memory-lancedb` embeddings 路径与维度配置，重启 gateway 并做 recall 回归验证 | `remote_repair_memory_lancedb.py` | `OPENCLAW_SSH_PASSWORD` |
| 长记忆启动级自愈 | 为 `memory-lancedb` 安装 `ExecStartPre`/`ExecStartPost` 守护：启动前自动重打补丁，启动后自动校验 1024 维 embeddings | `remote_install_memory_lancedb_guard.py` | `OPENCLAW_SSH_PASSWORD` |
| qwen 超时三次重试 | 给当前 host `pi-embedded` bundle 加上 `qwen3:14b` 同模型超时三次内重试，并把现有 qwen cron 超时统一抬到 `1800` | `remote_install_qwen_timeout_retry_policy.py` | `OPENCLAW_SSH_PASSWORD` |
| 国际渠道预部署 | 启用国际向官方渠道插件并预注册空配置入口 | `remote_enable_international_channels.py` | `OPENCLAW_SSH_PASSWORD` |
| LINE 插件 | manifest / 插件未装全 | `remote_install_line_plugin_fix.py` | 同上 |
| LINE 密钥 + 启用 | 已有 token/secret，写入并 `enabled=true` | `push_line_credentials_remote.py` | `OPENCLAW_SSH_PASSWORD`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET` |
| LINE 首次结构 | 占位文件、`enabled=false` | `remote_line_openclaw_setup.sh`（在**宿主机 root** 执行） | 无密钥入仓 |
| LINE 密钥（bash） | 与上类似，偏宿主机直跑 | `remote_line_apply_secrets.sh` | `LINE_CHANNEL_*` 在 shell 中 export |
| LINE Webhook 公网入口 | 需把本机 `127.0.0.1:18789` 映射到 frps 公网 TCP 端口，供域名 HTTPS 反代 | `remote_frpc_line_webhook_map.py` | `OPENCLAW_SSH_PASSWORD`；可选 `FRPC_LINE_LOCAL_PORT`（默认 18789）、`FRPC_LINE_REMOTE_PORT`（默认 31879） |
| LINE TimesCar cron 故障排查 | `LINE` 上 TimesCar 任务失败、`NO_REPLY`、`not-delivered`、旧 session 污染 | 以 `cron/jobs.json` + session `.jsonl` + `line-timescar-cron-repair-2026-04.md` 为准；必要时重置相关 cron session 并重新 `cron run` | 不要在 LINE 聊天里临时改 prompt/权限来“自修复” |
| frpc 隧道诊断 | ccnode 上看不到 remotePort 时，在汤猴查日志/配置 | `remote_diag_frpc_tunnel.py` | `OPENCLAW_SSH_PASSWORD` |

**统一 CLI（本机）**：`python SpringMonkey/scripts/openclaw_remote_cli.py <子命令>`，子命令与上表对应，见该脚本 `--help`。

---

## 3. 参数与环境变量（通用）

| 变量 | 含义 |
|------|------|
| `OPENCLAW_SSH_PASSWORD` / `SSH_ROOT_PASSWORD` | 宿主机 root SSH（仅本机会话） |
| `OPENCLAW_SSH_PASSWORD_FILE` | 本机单行密码文件路径（可选） |
| （无变量时）`SpringMonkey/secrets/openclaw_ssh_password.txt` 或 `private/` 同名 | 见 `scripts/openclaw_ssh_password.py` |
| `OPENCLAW_PYTHON` | 可选；固定 Windows 上 `python.exe` 路径（见 `SSH_TOOLCHAIN.md`） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API 长期 token |
| `LINE_CHANNEL_SECRET` | LINE Channel secret |

远程脚本内**默认**连接：`ccnode.briconbric.com:8822`（若变更，应改为脚本顶部常量或未来 `OPENCLAW_SSH_HOST` / `OPENCLAW_SSH_PORT`）。

---

## 4. 工具分裂 vs 组合

**分裂（推荐默认）**

- `diag`：只读诊断，不改配置。  
- `doctor`：只跑配置修复。  
- `line-install`：只装插件。  
- `line-push`：只写密钥并启用 LINE。

**组合（流水线）**

- `recover`：`diag` → `doctor`（先拿证据再修配置，**不**自动 line-push，避免误开通道）。  
- 更重的「全量」组合**不**默认提供，以免一次误触改太多；需要时在 `INDEX.md` 用编号步骤写清。

---

## 5. 扩展新工具时的检查清单

1. 在 `TOOLS_REGISTRY.md`（本表）增加一行场景映射。  
2. 在 `scripts/INDEX.md` 增加条目与用法。  
3. 若适合远程统一入口，在 `openclaw_remote_cli.py` 增加子命令。  
4. 若需新依赖，写入 `requirements-ssh.txt` 或单独 `requirements-*.txt`，并在 `SSH_TOOLCHAIN.md` 补一句。  
5. **不**把密钥写入任何跟踪文件。

---

## 6. 与其它文档的关系

- `docs/CAPABILITY_INDEX.md`：全仓库能力总览。  
- `docs/ops/SSH_TOOLCHAIN.md`：本机 Python/paramiko 一次性配置。  
- `docs/policies/REPOSITORY_GUARDRAILS.md`：哪些不能进 Git。
- `docs/runtime-notes/openclaw-runtime-baseline-2026-04.md`：当前汤猴宿主机恢复基线。
- `docs/runtime-notes/line-runtime-baseline-2026-04.md`：LINE 接入与恢复基线。
- `docs/runtime-notes/generic-cron-task-domain-2026-04.md`：普通定时任务的通用落地与验收规则。

---

## 7. 汤猴运行时策略 / SpringMonkey：Git 同步默认流程（推荐）

**目标**：本地与网关宿主机上的 `SpringMonkey` 工作区**内容一致**，用 Git 作唯一通道，**不写**自定义文件同步逻辑。

| 步骤 | 谁做 | 做什么 |
|------|------|--------|
| 1 | 开发侧（本仓库） | 修改策略、脚本、`config/` 等；`git commit` 并 `git push`。 |
| 2 | 网关宿主机 | 在 **`/var/lib/openclaw/repos/SpringMonkey`**（路径以现场为准）执行 **`git pull`**。 |
| 3 | 网关宿主机 | 若变更需要落地到 OpenClaw（例如 `apply_news_config.py`、跑补丁脚本），按任务执行对应命令。 |
| 4 | 网关宿主机 | 需要重载网关时 **`systemctl restart openclaw.service`**（或你们既定的 supervisor 流程）。 |

**远程一键**：`scripts/remote_springmonkey_git_pull.py`（可选环境变量 `OPENCLAW_RESTART_AFTER_PULL=1` 在 pull 后重启 `openclaw.service`）。

**注意**：密钥与 `openclaw.json` 等**运行时机密**仍以宿主机为准；Git 里只放策略与非秘密配置模板（见 `REPOSITORY_GUARDRAILS.md`）。
