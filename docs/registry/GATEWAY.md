# Gateway：从意图到工具与验证的导航

本页是 **人类读者** 的入口索引，与机器可读的 `tools_and_skills_manifest.json` 成对维护。新增工具或变更意图路由时，**必须**同步更新二者及 `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` 中的注册表与分类表。

---

## 1. 策略与流水线（先读）

| 文档 | 用途 |
|------|------|
| `docs/policies/SELF_ENHANCING_PIPELINE_AND_GATES.md` | 聊天→意图→任务→步骤→动作→工具→回归→报告；每步校准/复核 |
| `docs/policies/GOAL_INTENT_TASK_AGENT_SOCIETY.md` | Goal/Intent/Task/Step 分层与树状报告 |
| `docs/policies/AGENT_SELF_IMPROVEMENT_AND_TOOLSMITH_ARCHITECTURE.md` | 工具匠、失败分类、受控自增强 |
| `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` | 意图分类、工具注册表、Git 传播链 |
| `docs/policies/OPENCLAW_UPGRADE_POLICY.md` | 升级前检查；破坏本仓护栏则禁止该次升级 |
| `docs/policies/EXECUTION_AND_RECOVERY_LOOP.md` / `TASK_DELIVERY_STANDARD.md` | 执行环与交付证据标准 |

---

## 2. 意图（Intent）→ 仓库入口（速查）

下表与 `INTENT_TOOL_ROUTING...` 一致，仅作 **快速跳转**；权威行以该政策文件为准。

| Intent 类 | 首选动作 / 入口 |
|-----------|-----------------|
| 新闻配置/应用/验证 | `config/news/broadcast.json` → `scripts/news/apply_news_config.py` / `verify_news_config.py`；域说明 `docs/runtime-notes/news-task-domain.md` |
| 新闻多阶段 pipeline | `scripts/news/run_news_pipeline.py`；校验 `scripts/news/verify_broadcast_draft.py` |
| 手动重跑正式新闻 job | 宿主 `openclaw cron run <jobId>`；权威 `cron/jobs.json` |
| 定时任务查看 | `openclaw cron list --json` + 宿主机 `cron/jobs.json` |
| Discord 私信控制台入口 | `scripts/remote_fix_discord_dm_event_inbound.py`；必须走 Discord Gateway 事件触发，私信不得靠轮询作为正式入口 |
| 仓库同步 | `REPOSITORY_GUARDRAILS.md` 与既定 git/自动化；少手改 dist |
| 远程 OpenClaw 运维（本机统一入口） | `docs/ops/TOOLS_REGISTRY.md` + `scripts/openclaw_remote_cli.py` |
| OpenClaw 运行时护栏 / 补丁 | `scripts/openclaw/ensure_agent_society_runtime_guard.sh`；相关 `patch_*.py` 与 `docs/runtime-notes/preemptive-compaction-guard-2026-04.md` |

---

## 3. 工具登记（机器 + 人）

- **机器**：`docs/registry/tools_and_skills_manifest.json`（JSON，经 `scripts/registry/verify_tools_manifest.py` 校验）
- **人**：`docs/ops/TOOLS_REGISTRY.md`（场景→脚本矩阵）、`docs/CAPABILITY_INDEX.md`、`scripts/INDEX.md`（若存在）

---

## 4. 新增工具后的必做项

1. 在 `INTENT_TOOL_ROUTING...` 的 **Tool Registry** 与（如需要）**Intent Taxonomy** 各增一行。
2. 在 `tools_and_skills_manifest.json` 增加/更新条目，**并**在 `GATEWAY.md` 本页或上表增加 **可发现** 的链接或一行说明。
3. 为「通用化」写清 **参数与配置边界**；避免把可复用能力写死成单客户名/单渠道。
4. 运行 `python scripts/registry/verify_tools_manifest.py` 与（若适用）域内 `verify_*.py`。
