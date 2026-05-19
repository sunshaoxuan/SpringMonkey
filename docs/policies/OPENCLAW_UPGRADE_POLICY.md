# OpenClaw / 汤猴 升级策略（与本仓改动共存）

## 原则

1. **本仓库 `SpringMonkey` 为策略与补丁真源**；上游 OpenClaw 升级是可选事件，不是默认动作。
2. **禁止「静默拆护栏」**：任何升级若会导致既有补丁失效、校验脚本大面积红灯、或运行时契约断裂，则 **在该次升级中禁止合并/上线**，直至完成迁移与验证。
3. **本策略优先于习惯性升级**：当要求「在不影响本仓改动的前提下才可升级」时，以本文件与相关 runtime 笔记为验收依据。

---

## 升级前必须通过的检查

在宿主机或 CI 中依次执行（具体命令以仓库 `scripts/` 与 `docs/runtime-notes/` 为准）：

0. **运行时补丁盘点**：`python3 scripts/openclaw/runtime_patch_inventory.py --fail-on-missing` 必须 exit 0。它会检查当前 OpenClaw 安装目录中是否仍存在 SpringMonkey 依赖的 runtime marker，并检查 delivery queue 是否仍有 `channel:<owner-user-id>` 这类错误目标。
1. **护栏脚本**：`scripts/openclaw/ensure_agent_society_runtime_guard.sh`（或等价）exit 0。
2. **与本仓补丁锚点一致**：若 OpenClaw 将逻辑从某 dist 包迁移到另一包名（例如 **preemptive compaction** 从 `selection-*` 迁至 `preemptive-compaction-*`），须已更新对应 `patch_*.py` 与 ensure 中的包名/路径校验，见 `docs/runtime-notes/preemptive-compaction-guard-2026-04.md`。
3. **已安装依赖与 Node 版本** 与 `docs/ops` 中基线说明不冲突（或已记录新基线）。
4. **服务可启动**：`openclaw.service` 能 `active (running)`，无因缺补丁导致的硬错误。

任一条未满足 → **本次不升级** 或先完成本仓 PR 再升。

---

## 若必须升级：最低流程

1. 在**非生产**或**可回滚快照**环境先升。
2. 跑全量护栏 + 关键 job 烟测（与 `OPENCLAW_RELEASE_ACCEPTANCE_AND_DRIFT_CONTROL.md` 协同）。
3. 记录本次 dist 差异中**影响补丁的符号/文件**到 `docs/runtime-notes/`，并更新相关 `patch_*.py` 的说明头。

最低命令：

```bash
python3 scripts/openclaw/runtime_patch_inventory.py --fail-on-missing
python3 scripts/openclaw_remote_cli.py upgrade-guard
python3 scripts/openclaw_remote_cli.py upgrade-verify
```

`upgrade-guard` 会在宿主机安装 `/usr/local/lib/openclaw/ensure_springmonkey_upgrade_resilience.sh`，并把它挂到 `openclaw.service` 的 `ExecStartPre`。这不是替代各个具体 installer，而是升级后的总闸门：先重放可重复 runtime guard，再盘点 marker，再修正关键目录权限。

---

## 原生 OpenClaw 2026.5.18 可吸收能力

2026.5.18 对我们有帮助，但不能替代 SpringMonkey 自增益闭环：

- 可吸收：
  - QA-Lab runtime parity / runtime tool drift hard-gate：适合做升级前后回归闸门。
  - local task followthrough：适合对齐我们的“pending / blocked / done 必须有证据”的报告标准。
  - final reply delivery / Discord final visible reply 修复：可降低“完成但不投递”的概率。
  - plugin build / validate / init：适合把部分 SpringMonkey helper 逐步迁成正式插件，而不是继续 patch dist。
  - approval-runtime credentials 修复：可减少批准后异步命令卡住。
- 不能指望原生直接提供：
  - 根据我们业务 baseline 自动生成/修改仓库代码。
  - 对 TimesCar、天气、长记忆、XHS 等本地能力做端到端验收。
  - 在没有 diff、commit、测试证据时自动拒绝“已完成”报告。

因此升级策略是：优先吸收原生 QA/插件化/投递修复，但 SpringMonkey 仍保留自增益验收门和业务 baseline。

---

## 与本仓自增强流水线的关系

`SELF_ENHANCING_PIPELINE_AND_GATES.md` 所描述链路的落地不依赖频繁升上游；若升级破坏 **工具登记、Gateway 文档、或 intent 路由表** 的可读性/可发现性，应回退或冻结升级直至修复。

---

## 相关文档

- `docs/policies/OPENCLAW_RELEASE_ACCEPTANCE_AND_DRIFT_CONTROL.md`
- `docs/policies/REPOSITORY_GUARDRAILS.md`
- `docs/policies/SELF_ENHANCING_PIPELINE_AND_GATES.md`
- `docs/runtime-notes/preemptive-compaction-guard-2026-04.md`
