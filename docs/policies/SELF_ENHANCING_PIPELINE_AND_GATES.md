# 自增强汤猴：聊天入口到报告推送的流水线与关口

## 与现有策略的关系

本文件把 **可执行流水线** 与 **每步目标校准 / 成果复核** 写成固定关口；分层对象模型见 `GOAL_INTENT_TASK_AGENT_SOCIETY.md`，工具匠架构见 `AGENT_SELF_IMPROVEMENT_AND_TOOLSMITH_ARCHITECTURE.md`，意图与注册表见 `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md`。

**实现载体**：以本仓库 `SpringMonkey` 为真源；运行时优先 **已注册工具 + 校验脚本**，而非单次长对话临场发挥。

---

## 主链路

```text
聊天入口 → 意图识别 → 意图拆分 → 任务制定 → 步骤制定 → 动作制定
  → SKILL/工具选择（缺失则受控自研→测试→登记→再执行）
  → 回归意图检查 → 整理输出格式 → 推送报告
```

---

## 各阶段关口（目标校准 / 成果复核）

| 阶段 | 目标校准 | 成果复核 |
|------|----------|----------|
| 意图识别 | 显式/隐式目标与约束是否覆盖？控制类是否不误判？ | 多意图的依赖与并行结构是否保留？ |
| 意图拆分 | 子意图是否仍服务主目标？ | 结构可审计？ |
| 任务制定 | 每任务成功条件可验证？ | 证据（日志/退出码/产物）是否规定？ |
| 步骤制定 | 每步是否单一可观察结果？ | 避免多跳黑盒？ |
| 动作制定 | 是否走注册工具与最小 exec？ | 可复跑、可审计？ |
| SKILL/工具 | 通用化优先、业务进配置？ | 新工具经测试并更新 manifest 与 `docs/registry/GATEWAY.md`？ |
| 回归意图 | 是否仍对齐用户最初目标？ | 禁止伪完成。 |
| 输出与推送 | 任务域版式与交付标准？ | 见 `TASK_DELIVERY_STANDARD.md` |

---

## 反糊弄与反「业务写死」

- **无证据成功** 视为失败。可复用步骤应参数化进 CLI/配置；工具与框架层不写死客户名、渠道名或一次性业务常量。
- 工具匠路径须 **可测试、可回滚**；合并前通过仓库内 verify 或最小集成测试。

---

## 登记与 Gateway

每新增或重大变更工具、Skill、网关补丁：

1. 更新 `docs/registry/tools_and_skills_manifest.json`
2. 更新 `docs/registry/GATEWAY.md`
3. 若影响意图路由，同步更新 `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md`

---

## 与升级策略的关系

暂不升级上游 OpenClaw 时：以 **文档 + manifest + `scripts/` verify** 为主落地。若将来升级，须遵守 `OPENCLAW_UPGRADE_POLICY.md`，且不得在无迁移计划的情况下破坏本仓补丁与护栏。
