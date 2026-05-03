# Intent, Tool Registry, And Capability Accumulation

## Purpose

`汤猴` 的行为不应退化为「先理解消息 → 再让强模型临场发挥」。稳定、可复用的运维能力必须走 **意图路由 + 已注册工具**，才能把一次成功变成长期可调用能力。

本策略与下列文档同阶配合阅读：

- `SELF_ENHANCING_PIPELINE_AND_GATES.md`（自增强主链路与每步目标校准/成果复核）
- `OPENCLAW_UPGRADE_POLICY.md`（升级前检查；若破坏本仓护栏与传播链则禁止该次升级）
- `../registry/GATEWAY.md`（人类可读的意图 → 脚本/工具/验证/文档入口）
- `EXECUTION_AND_RECOVERY_LOOP.md`（执行、验证、恢复）
- `TASK_DELIVERY_STANDARD.md`（交付形态与证据）
- `REPOSITORY_GUARDRAILS.md`（仓库与权限边界）
- `DOCS_AUTHORITY_MODEL.md`（文档层级与授权）
- `../runtime-notes/news-task-domain.md`（新闻任务域）

## Strategy Propagation：Git 推送 + 宿主机 Pull（首选低成本路线）

**规范真源**在 Git 仓库（本仓 `SpringMonkey`）：策略文档、任务域配置、`scripts/` 下的应用/校验脚本、以及 **可版本化的** OpenClaw 补丁脚本（如 `scripts/openclaw/patch_news_router_v3.py`）都应先落在仓库里，再进入运行环境。

**强规则**：所有会约束或提示 OpenClaw 行为的规则，包括 prompt、路由、工具选择、任务执行、投递、定时任务、guardrail、自修复策略和补丁源，都必须通过 Git 传递，并且必须能由宿主机的自动 pull / 受控 pull 从远端取得。不允许把这类规则只手工上传到宿主机后当作已部署能力；手工上传最多是临时 hotfix，必须补齐 commit → push → host pull → 验证后才算 durable。

**推荐闭环**（比 SSH 上手改 `/usr/lib/node_modules` 更可审计、易回滚）：

1. 在开发侧或 `汤猴` 任务工作区镜像（如 `~/.openclaw/workspace/SpringMonkey/`）修改并提交。
2. `git push` 到约定远端（自主更新默认分支见 `REPOSITORY_GUARDRAILS.md`）。
3. 在网关宿主机上的仓库工作副本更新代码（常见路径如 `/var/lib/openclaw/repos/SpringMonkey/`，以现场为准）。**注意：**
   - 若工作副本停在 `bot/openclaw` 而策略在 `main`，应先 `git checkout main` 再 `git pull --ff-only origin main`，否则会与 `main` 分叉导致无法 fast-forward。
   - 若出现 `detected dubious ownership`，对 root 执行：`git config --global --add safe.directory /var/lib/openclaw/repos/SpringMonkey`（路径按实际填写）。
   - 若 `origin` 使用 `git@github-springmonkey:...` 等 **本机无法解析的 SSH Host 别名**，`git fetch` 会失败；可改为只读拉取用的 HTTPS，例如：`git remote set-url origin https://github.com/sunshaoxuan/SpringMonkey.git`（需要写回 SSH 推分支时再改回或配置 `~/.ssh/config` 中的 `Host`）。
4. **若变更包含「需写入 npm 包 dist」的补丁脚本**：pull 只更新磁盘上的脚本本身；仍须在宿主机 **执行** 对应 `python3 scripts/openclaw/...py` 并 **重启 gateway**（如 `systemctl restart openclaw.service`），补丁才生效。可将该执行步骤记入运维手册或日后做成受控 post-pull / timer（脚本入口仍应以仓库为准）。

**与 `DOCS_AUTHORITY_MODEL.md` 一致**：仓库描述策略与脚本，**不自动等于**宿主机权限或配置已被应用；但 **把策略与补丁脚本放进 Git 再 pull**，是落实「可积累能力」的默认传播方式，应避免只在聊天里口头约定、只在单机上手改 dist。

## Core Model (Two Paths)

### Path A — 已有成熟工具

```
intent 判定 → 工具注册表命中 → 直接调工具（脚本 / CLI / 任务域）→ 按标准验证与记录
```

模型职责限于：**选对意图、填对参数、解释结果**，而不是重新发明执行路径。

### Path B — 尚无正式工具

```
intent 判定 → 受控临时执行（有边界、可审计）→ 若同类任务重复出现 → 沉淀为正式工具 → 回写注册表与意图路由
```

临时执行仍须遵守 `EXECUTION_AND_RECOVERY_LOOP.md` 与 `TASK_DELIVERY_STANDARD.md`（证据、禁止空口完成）。

## Intent Taxonomy (Baseline)

以下分类用于 **路由决策**；新增重复任务类时，应扩展本表并同步更新「工具注册表」与运行时意图路由（若宿主已打补丁，仓库侧须保持描述一致）。

| Intent ID | 典型用户表述（示例） | 首选执行方式 | 模型角色 |
|-----------|----------------------|--------------|----------|
| `chat_general` | 闲聊、解释概念、与当前宿主/仓库无强绑定操作 | 聊天引擎（如本地 instruct 模型）；不强行套工具 | 正常对话 |
| `news_rerun` | 手动重跑 09:00/17:00 新闻、按正式任务再执行一遍 | **禁止**把需求当成「临时搜新闻写摘要」。应使用正式 cron 任务定义：`openclaw cron run <jobId>`，权威 payload 以 `cron/jobs.json` 为准 | 仅确认已排队/已触发，不替代正式任务生成投递内容 |
| `news_config` | 改播报节奏、大纲规则、时间窗、编号、目标频道（任务域内） | 任务域：`config/news/broadcast.json` → `apply_news_config.py` → `verify_news_config.py`，见 `news-task-domain.md` | 编辑配置与跑脚本，不手改散落 `jobs.json` 绕过任务域 |
| `news_pipeline` | 需要可审计的多阶段成稿（编排→工人落盘→合并→主编→校验），而非单次 agentTurn 临场发挥 | 宿主/工作区：`python3 scripts/news/run_news_pipeline.py --job <name>`；`openai-codex/*` 必须通过 OpenClaw gateway/OAuth profile 调用，不得要求裸 `OPENAI_API_KEY`；Qwen/Ollama 仅作兜底 | 输出目录内 `final_broadcast.md` + 校验通过；再人工或脚本投递 Discord |
| `cron_inspect` | 查看/确认定时任务是否存在、表达式为何 | `openclaw cron list --json` 及宿主机上 `cron/jobs.json` 等**机器可读证据** | 展示事实状态，不臆测 |
| `discord_dm_control` | owner 在 Discord 私信中下达控制台指令，如 TimesCar 保留/取消/改时 | `scripts/discord/discord_dm_control_poll.py`；入口层必须记录入站事件并 ack，未支持的真实订单变更必须明确拒绝自动执行 | 只负责入口识别、状态记录和安全回报；真实订单写操作必须有专用执行器与确认页校验 |
| `repo_sync` | 拉取/同步 SpringMonkey 或工作区镜像、提交到约定分支 | 已配置的 git / 同步流程与 elevated 策略（以宿主配置为准）；**优先走既定自动化或脚本化路径** | 少自由发挥，多 `git status` / `rev-parse` 等证据 |
| `config_apply_verify` | 某任务域「应用配置 + 验证」类（新闻以外若日后增加） | 该域的 `apply_*` / `verify_*` 脚本对 | 同新闻任务域模式 |
| `adhoc_ops` | 单次排障、尚未归类、无注册工具 | 受控临时执行：先读 guardrail 文档，明确成功条件与证据，再动手机 | 执行完毕后评估是否升级为下表新工具 |

**禁止：**在已有工具覆盖的意图上，用「更强模型多写几段推理」替代 **一次正确的工具调用**。

## Tool Registry (Repository-Anchored)

下列条目为 **仓库内可指向的规范入口**；CLI 路径、systemd、Discord 补丁文件以宿主文档（如运维笔记）为准，但 **语义与优先级** 以本注册表为准。

| Tool ID | 作用 | 仓库或约定入口 | 验证要点 |
|---------|------|----------------|----------|
| `news.broadcast.config` | 新闻播报可调参数 | `config/news/broadcast.json` | `verify_news_config.py` 通过 |
| `news.apply` | 将配置应用到运行侧 | `scripts/news/apply_news_config.py` | 与 verify 成对使用 |
| `news.verify` | 校验新闻任务域一致性 | `scripts/news/verify_news_config.py` | 机器输出作为交付证据 |
| `news.pipeline.run` | 多阶段新闻稿：Codex（OpenAI 兼容 API）负责编排、逐条整理与终稿合并；Qwen（Ollama）仅作兜底；机械校验 | `scripts/news/run_news_pipeline.py`；成稿校验 `scripts/news/verify_broadcast_draft.py` | 标准输出含 `PIPELINE_OK`；默认跑 `verify_broadcast_draft`（可用 `--skip-verify` 调试） |
| `openclaw.cron.run` | 触发已注册定时任务 | 宿主：`openclaw cron run <jobId>` | 任务进入队列/执行记录；非「模型直接发文」 |
| `openclaw.cron.list` | 枚举定时任务 | 宿主：`openclaw cron list --json` | JSON 与 `jobs.json` 对照 |
| `discord.dm_control.poll` | Discord owner DM 控制台入站兜底；修复网关 DM inbound 静默时的控制面 | `scripts/discord/discord_dm_control_poll.py`；部署 `scripts/remote_install_discord_dm_control.py` | 新私信必须进入 `discord_dm_control_state.json` 并返回 ack；`保留这单` 写入 `timescar_user_decisions.json` |
| `chat.engine` | 无工具类对话 | 运行时模型路由配置 | 不涉及宿主机状态变更时不强制证据 |

新增工具时：**在本表增加一行**，并在 `Intent Taxonomy` 中增加或收窄 `intent`，必要时在运维笔记中记录运行时补丁文件。

## Controlled Ad Hoc Execution (Path B Detail)

当意图落在 `adhoc_ops` 或尚未注册时：

1. **Preflight**：读 `REPOSITORY_GUARDRAILS.md` 与相关 runtime-notes；明确是否允许自主改仓库、改哪条分支。
2. **Success condition**：写清「怎样算完成」（可机器验证优先）。
3. **Execute**：最小变更面；避免与任务域脚本职责重复的「手搓链路」。
4. **Verify**：满足 `TASK_DELIVERY_STANDARD.md`（证据、剩余风险）。
5. **Record**： durable 规则写入 policy 或 runtime-note；单次事件写入 `docs/reports/`（若适用）。

## Formalize Into Tool (Accumulation Loop)

满足以下 **任一** 条件，应启动沉淀（人类或自主在 `bot/openclaw` 上提案均可）：

- 同一 intent 在短周期内 **重复** 出现，且步骤稳定；
- 失败模式与「缺少脚本/缺少单一入口」强相关；
- 需要可重复验证（apply/verify 类）。

**沉淀步骤（检查清单）：**

1. 新增或整理 **脚本/CLI 封装**（单一入口、非交互、可日志化）。
2. 在 **工具注册表** 增加 `Tool ID` 与路径说明。
3. 在 **意图分类表** 中将原 `adhoc_ops` 细化为独立 `intent`，并写明「禁止再走临时路径」的边界。
4. 更新 **任务域文档**（如 `news-task-domain.md` 模式）或新建 `docs/runtime-notes/<domain>.md`。
5. 若宿主使用 Discord 前置路由：将「调工具而非改模型 prompt」同步到运行时补丁说明（运维文档记录补丁路径即可，密钥不进仓库）。
6. 首次落地后按 `EXECUTION_AND_RECOVERY_LOOP.md` 做一次完整验证并留报告摘要。

## Relation To Runtime Patches

宿主上的 `pi-embedded-*.js` 等补丁实现 **具体如何** 截获消息并调用 `openclaw cron`；本仓库策略描述 **应当** 遵守的路由优先级。升级 OpenClaw 覆盖补丁后，须按本策略回归：新闻重跑仍须绑定正式任务，而非纯模型生成。

已知问题：仅依赖 `classifyDiscordIntent === news_task` 时，长指令易被判为 `chat` / `task_control` 从而跳过 `cron run`。仓库内 **v3** 补丁在启发式命中时强制升格为 `news_task`，见 `docs/runtime-notes/discord-news-manual-rerun-intent-override.md` 与 `scripts/openclaw/patch_news_router_v3.py`。  
另：**v4** 必打——网关若以 `User=openclaw` 运行，在进程内调用 `runuser` 会失败并导致整段意图路由返回 `null`（日志里 `classify failed: ... runuser`），须改用直接执行 `openclaw cron run`，见 `scripts/openclaw/patch_news_router_v4.py`。  
**v5** 必打——手动重跑启发式命中时须 **先于 Ollama 分类器** 定型为 `news_task`，否则 Ollama 不可用时会 `classify failed` / 路由 `null` 并退回默认聊天模型；见 `scripts/openclaw/patch_news_router_v5.py` 与 `scripts/openclaw/test_manual_news_heuristics.py`。  
**v6** 必打——为分类 `fetch` 加超时；路由 `catch` 回退 **Codex**；Discord 下 ollama 主链路前 **generate 探针** 失败则切 **Codex**（与上游 FailoverError 链路互补）。见 `scripts/openclaw/patch_news_router_v6.py`。  
**v7** 必打——`queueFormalNewsJobRun` 不得在网关内使用 **`spawnSync` 调 `openclaw cron run`**（事件循环死锁）；须 **async `spawn`**。见 `scripts/openclaw/patch_news_router_v7.py`。

Discord owner DM 控制台不得只依赖 gateway 事件消费成功；若 Discord REST API 可见私信但 OpenClaw journal 无入站记录，必须启用 `discord.dm_control.poll` 作为机械入口兜底。该入口的最低合格标准是：每条 owner 私信要么路由到已注册工具，要么返回“未支持/未执行”的明确 ack，并落入 `discord_dm_control_state.json`，不得静默无响应。

## When To Stop Elevating Model Freedom

若某类任务已注册工具，却仍以「换更强模型」为主要手段，视为策略违背：应回到 **工具失败分类 → 下一合法路径 → 证据**，而不是加长推理链。
