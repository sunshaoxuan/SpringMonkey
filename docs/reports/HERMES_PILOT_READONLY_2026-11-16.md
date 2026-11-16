# SpringMonkey 重装后 Hermes Agent 试点部署计划

最新选型结论见 [三候选深入比较](AGENT_FINAL_COMPARISON_2026-11-16.md)：按当前单机资源与首批研究/文件任务，研究推荐 nanobot 第一、Hermes 第二、Agent Zero 第三。用户尚未发起安装或切换，本文保留为 Hermes 候选计划。固定 Hermes v0.23.1 的部分内容拒绝处理存在备用切换路径，与在线说明有差异；下文“拒绝保持终态”继续作为验收要求，当前未获源码/运行通过。

更新：2026-11-16，Asia/Tokyo。状态：B0 只读核查完成，入口及额度条件未满足，总体 HOLD，实际部署未开始。第 1 至 8 节为现行计划，末尾旧报告仅作历史证据。最新版本绑定、主机条件、接口与 Skills 审查以 [B0 明细](HERMES_B0_PREFLIGHT_2026-11-16.md) 为准。

用户追加要求的 [替代方案调查](AGENT_ALTERNATIVES_2026-11-16.md) 已比较 nanobot、Agent Zero、goose、QwenPaw 等现行候选。建议未来与 Hermes 做统一样例对照，当前没有决定替换或安装。SpringMonkey 始终指本次重装的 ubuntu-2625 主机，非另一套软件。

## 1. 目标和授权范围

在 SpringMonkey 上规划单用户 Hermes Agent，主模型使用用户选定的 ChatGPT/OpenAI 兼容接口，备用依次为 DeepSeek、Qwen。首批支持公开资料研究、文件分析、带来源的报告和工作区文件生成，通过 SSH CLI 使用。Discord 连接资料保持静态保留，后续接入独立安排。

首轮为公开资料调查、一次远端资源只读探针及文档更新；追加 B0 获授权读取本机既有接口配置、认证查询模型目录、检查远端安装条件并读取 registry 元数据与固定源码。未安装 Docker、Hermes、Skills 或插件，未修改远端配置，未发起生成请求。Wi-Fi、Tailscale、FRP、SSH 维持既有配置。FRP 二进制禁止下载、复制或运行到用户本机。

结论：Hermes 已有框架、工具调用、状态、Skills、MCP 和原生跨模型兜底等必要组成，适合作为该主机试点基础。本机运行质量、三模型协议兼容性和故障恢复尚待实际验收。公开资料无法证明它复刻 Meta Muse.AI 的内部机制，也不足以承诺相同产品体验。

主指导文档：[TASK_GUIDE](C:/workspace/codex-work/muse-selfhost-research-20261116/TASK_GUIDE.md)。重装证据见 [重装验收报告](AUTOINSTALL_PREPARATION_2026-11-16.md)。历史 Ubuntu 25.10、旧 OpenClaw、旧 Docker、旧网关和旧负载结果均不再作为部署输入。

## 2. 重装后的主机基线

2026-11-16 20:37 JST，经既有 Tailscale SSH 运行 stdin Python 探针，远端未落脚本。证据：[HOST_POSTRESET_PLAN.json](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/hermes-pilot-20261116/HOST_POSTRESET_PLAN.json)。正常连接可能产生系统审计日志。

| 项目 | 现行证据 |
| --- | --- |
| 系统 / 内核 | Ubuntu 26.10 / 7.3.0-10-generic |
| CPU | 4 逻辑线程；前序硬件证据为 i5-5200U、2 物理核 |
| 内存 | 总计 7.14 GiB，available 6.64 GiB |
| Swap | 4 GiB，未使用 |
| 根盘 | 总计约 328.62 GiB，可用约 304.15 GiB |
| 即时 load | 1/5/15 分钟均为 0.0；本次未做持续压测 |
| 连通性 | ssh、tailscaled、frpc 均 active，本次实际 SSH 成功 |
| Wi-Fi / 两路恢复 | 当日重装验收覆盖 Wi-Fi 自动联网及 Tailscale、FRP 两次原生启动后 SSH |
| 应用 | 当前 Docker 不存在；重装验收确认旧 OpenClaw、Chrome/Chromium 等已移除 |
| GPU | 前序硬件证据为 Intel HD 5500；方案全部外部推理 |

资源允许规划一个受限实例。浏览器、OCR、Office 转换需单独测峰值。单次空闲采样无法证明长期稳定。旧运维索引中的应用描述属于历史，重装后的实际基线以当日验收和本节为准。

## 3. 版本、容器及资源约束

最新稳定发布采样为 [v0.23.1](https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.1)，发布于 2026-11-10。B0 已解析 tag 实际 commit 为 `3b421578588243f920886e6fe79a6faa87ea026e`，并验证 registry 的 `v0.23.1`、stable、latest 指向同一 index，实际无 v 的 `0.23.1` 标签返回 404。index 与 amd64 manifest digest 已冻结在 B0 明细；只读元数据，未下载 layer 或运行镜像。固定 digest，停用自动追踪 main。

选择官方容器路径，已读取稳定 tag 的 [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/Dockerfile) 与 [配置示例](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/cli-config.yaml.example)。B0 确认 Docker 官方支持 Ubuntu 26.10，远端可取 stonking/amd64 包索引且签名及摘要核对通过；镜像压缩层约 1.04 GiB，解压占用待安装验收。PDF 提取库与 DDGS 并非都已烘入镜像，按 B0 清单准备依赖。[官方 Docker 指南](https://hermes-agent.nousresearch.com/docs/user-guide/docker)

建议目录 `/srv/hermes-pilot/{state,workspace,policy,backups}`，按镜像 `/opt/data` 约定生成挂载。state 为私有会话与记忆，workspace 为任务输入输出，policy 为管理员维护的指令与已审核 Skills，backups 为严格权限或加密的备份。策略只读挂载和初始 Skills 播种的关系在 B0 核验，禁止假定未经验证的安装参数能实现白名单。

官方镜像以 root 初始化 s6 和目录后，降权到 hermes 运行 Agent；不套用任意 `--user`。设置 `terminal.backend=local`，工具在容器中运行。不给 privileged、host network、sudo 或 docker.sock；不挂载宿主根、SSH 私钥、Tailscale/FRP 状态、Discord 备份。capabilities 和 no-new-privileges 与该初始化契约共同验证，不预填硬化 PASS。写权限限于状态、工作区和必要临时路径，Docker 管理权限留给操作员。

首批通过现有 SSH 使用 CLI，不新增公网端口。Hermes 对外提供的 OpenAI-compatible API server 与上游模型接口是两个方向，试点无需启动该 API server。后续 UI 如有需要，采用 loopback 加 SSH 隧道，另行做鉴权及 UI 验收。

| 规划约束，当前未生效 | 建议值 / 验收 |
| --- | --- |
| CPU | 1.5 个逻辑 CPU，核对 cgroup 实际限制 |
| 内存及总内存含 swap | 3 GiB / 3 GiB，禁止容器消耗宿主 swap |
| 进程数 | 512，核对正常任务峰值 |
| 并发 | 1 个顶层任务，首批关闭委派 |
| 浏览器 | B2 开放，至多 2 个页面，验证超时清理 |
| 数据 | 10 GiB 软预算及日志轮转；普通卷没有天然硬配额 |
| 主机保护 | available 低于 1.5 GiB 持续 60 秒，或根盘可用低于 40 GiB，停止试点任务；部署时落实监测，只终止自身容器 |

## 4. 三模型接入、兜底和预算

调用方向：用户 → Hermes 单一任务循环 → 主 ChatGPT 兼容路由 → DeepSeek → Qwen。SpringMonkey 承担编排、工具和状态；模型在外部运行。Hermes 配置不改动用户本机 Codex 的全局 provider、模型和订阅认证。

ChatGPT OAuth、OpenAI API key 和第三方兼容网关是不同接入方式。本方案按用户要求使用 `base_url + key + model ID` 的兼容路由；若后续选择 ChatGPT 订阅，改走 Hermes 独立 Codex OAuth 路径，并重新验证 Responses 协议。不能从 ChatGPT 登录状态推定兼容接口凭据已具备。[官方供应商指南](https://hermes-agent.nousresearch.com/docs/integrations/providers)

部署前冻结三条实际路由的服务来源、HTTPS URL、精确 model ID、凭据引用、协议、上下文窗口、工具/流式能力、费用与配额。凭据通过安全渠道进入受限配置，不写 Git、日志或聊天。旧 OpenClaw 模型名与旧网关可达性结果不再复用。

B0 已从现有本机网关获取 41 个 model ID，主候选 gpt-6-astra、DeepSeek 正式 ID deepseek-flash 以及一个 Qwen GGUF 路由目录可见。网关只发布 Windows loopback，SpringMonkey 访问其私有上游 TCP 超时，尚无可填入远端的已验证安全入口。独立备用与额度也未确立，因此三路配置仍为草案，生成和故障注入保留 B1。

独立服务候选：DeepSeek 官方当前列出的正式模型包含 `deepseek-flash`，兼容 base URL 为 `https://api.deepseek.com`；部署时再通过该服务的 `/models` 确认账号能力，不使用旧别名。Qwen 可走阿里云 Model Studio 的 OpenAI-compatible 接口，其域名包含 workspace 与地域，API key 必须与地域匹配，不能统一拼成任意域名的 `/v1`。下方 Qwen URL 只是结构占位，实际应保留官方给出的 `/compatible-mode/v1` 路径。供应商兼容文档的北京示例与迁移说明存在地域拼写不一致，冻结时以目标 workspace 控制台和地域端点文档交叉确认。来源：[DeepSeek 接入](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[模型目录](https://api-docs.deepseek.com/api/list-models/)、[Qwen 兼容接口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)。这些均为公开文档观察，未使用任何账号发出模型请求。

以下是非执行性结构草案，占位符须替换。主路由凭据由官方设置工具生成并核验其引用。本段只表示结构，不是可直接部署的完整配置。

```yaml
model:
  provider: custom
  default: "<CHATGPT_EXACT_MODEL_ID>"
  base_url: "https://<CHATGPT_GATEWAY>/v1"
fallback_providers:
  - provider: custom
    model: "<DEEPSEEK_EXACT_MODEL_ID>"
    base_url: "https://<DEEPSEEK_ENDPOINT>/v1"
    key_env: HERMES_DEEPSEEK_API_KEY
  - provider: custom
    model: "<QWEN_EXACT_MODEL_ID>"
    base_url: "https://<QWEN_ENDPOINT>/v1"
    key_env: HERMES_QWEN_API_KEY
```

采用现行 `fallback_providers`。稳定 tag 的 [fallback_config.py](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/hermes_cli/fallback_config.py) 确认了有序列表、逐路由 `key_env` 及去重逻辑。[官方兜底指南](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers) 的详细错误语义及检查命令须在选定镜像验收，main 文档不能替代稳定镜像实测。

| 情况 | 预期行为及验收 |
| --- | --- |
| 429、暂时性 5xx、连接中断 | 有界重试后沿链切换，记录原因、实际路由和耗时 |
| 401 / 403 / 404 | 显示凭据、权限或模型映射故障及切换，保留修复项 |
| 400 / 上下文超限 / schema 不兼容 | 分类定位、按已验证能力调整参数或压缩，避免无限重试 |
| 空答或非法响应 | 验证解析及有界切换，区分 reasoning-only 与真正空答 |
| 拒绝或 content_filter | 保留终态，禁止通过备用模型绕过 |
| 全链失败或超预算 | 保存检查点，明确失败，停止任务 |
| 工具已执行后模型失败 | 保留 tool-call/result 关联；本地有副作用动作不自动重放，注入测试要求动作计数一次 |

三路各自验证中文、流式、JSON、工具参数/结果、reasoning 参数和上下文边界；不用一次成功掩盖另一路失败。文本备用无法替代未验证的视觉能力。模型切换可能增加上下文输入和缓存失效费用。

三个模型共享同一网关时，网关、账户与网络故障域仍共享。建议至少一路备用使用独立服务和独立额度，部署时核对实际供应商。Hermes 与网关的跨模型重试只保留一个负责层，避免次数相乘。

压缩、标题等辅助调用也显式绑定批准路由，按实际日志验证；首批停用图像、语音、嵌入服务。第三方备用能够接收哪些上下文需事先明确，默认不导入公司资料、私人消息或生产凭据。

预算建议：每任务 15 分钟、30 次模型请求，含重试和辅助调用；首次试点总费用建议上限 USD 10，均待实施。优先供应商侧硬额度，CLI 提示不能当作硬费用限制。缺乏可靠额度或停止机制时仅开展人工在场的小样本。请求超时、重试和总期限使用统一预算，字段及效果按稳定版验证。

## 5. GitHub 扩展调查

公开搜索按 Stars 排序，查询 `hermes skills in:name,description` 和 `awesome hermes agent in:name,description`，补查官方及通用 Skills/MCP 项目。元数据采样为 2026-11-16 20:32 JST，共记录 37 个仓库、读取精选 12 个 README。Stars 是关注度指标，GitHub 没有统一插件评分。本轮未运行第三方代码，未完成安全审计。

完整元数据：[GITHUB_REPOSITORIES](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/hermes-pilot-20261116/GITHUB_REPOSITORIES.json)；README blob SHA 及发布来源：[SOURCE_MANIFEST](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/hermes-pilot-20261116/SOURCE_MANIFEST.json)。最近推送可以包含任何分支更新。API 许可证字段为空或 NOASSERTION 时仍需查实际 LICENSE。

| 仓库 | Stars | 最近推送 UTC 日期 | 类型、许可证观察及决定 |
| --- | ---: | --- | --- |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | 263,784 | 11-16 | 官方框架及 Skills，MIT；第一优先，固定稳定版本 |
| [0xNyk/awesome-hermes-agent](https://github.com/0xNyk/awesome-hermes-agent) | 6,027 | 10-27 | Hermes 生态索引，API 为 NOASSERTION；优先发现候选并逐项回源 |
| [ZeroPointRepo/awesome-hermes-skills](https://github.com/ZeroPointRepo/awesome-hermes-skills) | 683 | 11-02 | Hermes Skills 索引，MIT；研究和文档候选池 |
| [ksimback/hermes-ecosystem](https://github.com/ksimback/hermes-ecosystem) | 1,355 | 11-16 | Hermes Atlas 导航站，API 许可证未识别；交叉发现即可 |
| [anthropics/skills](https://github.com/anthropics/skills) | 195,642 | 11-14 | 通用 Skills，README 声明 Apache 2.0、API 未识别；按目录 LICENSE 复核后适配 |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) | 37,231 | 11-15 | 通用 Skills 索引，MIT；补充来源，逐项适配工具与依赖 |
| [obra/superpowers](https://github.com/obra/superpowers) | 318,304 | 11-03 | 开发工作流及宿主适配，MIT；后续编码阶段择取，整套接入待评估 |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 79,619 | 09-18 | Claude Skills 索引，API 许可证未识别；补充发现，外部写连接器暂缓 |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | 39,721 | 11-15 | 浏览器 MCP，Apache-2.0；B2 备选，先比较 Hermes 自带浏览器 |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 92,037 | 11-12 | MCP 参考服务及索引，API 为 NOASSERTION；按需选只读服务并查目标许可 |
| [outsourc-e/hermes-workspace](https://github.com/outsourc-e/hermes-workspace) | 6,827 | 11-05 | 独立 Web 工作台和多 Agent 能力，MIT；后续 UI 候选，首批 CLI 无需引入 |
| [apoapostolov/hermes-agent-awesome-plugins](https://github.com/apoapostolov/hermes-agent-awesome-plugins) | 53 | 11-16 | 插件集，MIT，多数面向 Desktop；personal 树声明调用 Desktop 内部接口，暂缓 |
| [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) | 5,717 | 06-17 | DSPy/GEPA 演化管线，API 许可证未识别；首批暂缓 |

另查到 `mergisi/awesome-hermes-agent` 为 6 Stars、`frankxai/awesome-hermes-agents` 为 8 Stars，本轮不作为高关注来源。索引许可证不覆盖所有外链，实际内容、脚本和授权需逐项审核。

Skill 是按需流程和资源，Plugin 可加载 Python/hooks，MCP 是单独工具服务，workspace/Agent 项目可能是完整系统。SKILL.md 标准提供迁移基础，工具名、宿主指令、依赖和 SDK 仍需适配。机制来源：[Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)、[Plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)、[Plugin Catalog](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugin-catalog)。

## 6. 首批能力包和准入

首批一个实例顺序完成资料收集、整理、核验。关闭委派、自改策略、自动安装扩展、外部写入与定时任务；允许在工作区提出技能草稿供审阅。

| 能力 | 首选来源 | 纳入条件与边界 |
| --- | --- | --- |
| 网页研究 | Hermes 内置搜索、提取 | 给出来源和日期，事实与推断分开；搜索服务不可用时显式失败 |
| 文档转待办 | 官方 `productivity/document-to-action-items` | 稳定 tag 已读，MIT；仅生成有定位的草案，关闭外部 tracker 工具 |
| PDF 文本 | 官方 `productivity/pdf` 选定子集 | B0 已补齐固定源码、MIT 及依赖审查；仅文本/表格/元数据，侧环境与权限在 B1 实测 |
| Office 文件 | 官方 microsoft-office 或 Anthropic 对应单项 | 按需求二选一，检查依赖和实际文件渲染，后续批次 |
| 报告核验 | 内置文件工具、任务记录及核验清单 | 输出仅在 workspace，保留引用与不确定性 |
| 浏览器 | 优先 Hermes 自带，Playwright MCP 备选 | B2 启用，空白独立 profile，限制页面、下载与可访问目标 |

目录来源：[Bundled Skills](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog)、[Optional Skills](https://hermes-agent.nousresearch.com/docs/reference/optional-skills-catalog)。核验冻结版本的初始化播种和实际启用项，不使用未经验证的 `--no-skills` 安装参数。document-to-action-items 本身包含创建外部记录阶段，必须通过工具权限关闭该能力。

每项记录精确 commit、路径、许可证、Hermes 版本要求、依赖/安装脚本、工具权限、网络目标、凭据与回滚。Plugin 优先采用官方目录固定审阅 SHA，检查 `requires_hermes`，审核时间范围不替代本次检查。首批无需额外记忆数据库、RAG 或常驻 hooks。

审批采用 manual 方向，无人值守危险命令拒绝，具体字段按稳定版验证。[官方安全说明](https://hermes-agent.nousresearch.com/docs/user-guide/security)。命令审批、文件工具限制和容器权限分别覆盖不同边界；容器内进程可能读取自身推理凭据，使用独立低额度凭据、最小上下文与挂载限制降低影响。

## 7. 后续部署批次、验收和回滚

以下均为待执行计划，实际安装需用户后续发起部署指令。

| 批次 | 变更及依赖 | 验收与停止条件 |
| --- | --- | --- |
| B0 冻结候选 | Ubuntu 的官方 Docker 安装路径、镜像身份、真实三路模型目录/协议/费用、Skills 许可证与依赖、UID/目录、预算 | 脱敏清单和生成配置完整；依赖缺证据则停止 |
| B1 最小端到端 | 安装确认后的容器运行时，单 CLI 实例，三路模型，研究及工作区文件工具 | 逐路真实调用、受控故障注入和固定研究样例，记录实际路由与成本 |
| B2 文档及浏览器 | B1 通过后按需增加 PDF/Office/单一浏览器方案 | CPU/内存/超时回收、文档及页面产物检查；消息渠道保持关闭 |
| B3 可选自动化 | 独立授权的只读定时任务 | 去重、预算、无人值守拒绝、停止及恢复验证；Discord 独立安排 |

B1 正式检查冻结镜像、配置、Skills commit、输入及模型映射后集中运行，预计 30 至 60 分钟，受 API 时延影响。同输入只跟踪原运行，具体失败才修复并重跑受影响项。

| 必需检查 | 通过标准 |
| --- | --- |
| 三路协议 | 各路独立完成中文、流式、JSON/tool call，映射和辅助调用可解释 |
| 故障链 | 主路由 429/503 切 DeepSeek，再失败切 Qwen，全失败停止；记录重试与耗时 |
| 错误分类 | 401/404 可见，参数错误不无限重试，拒绝终止，长上下文按已验能力处理 |
| 副作用 | 本地样例在工具完成后注入模型故障，动作计数仍为一次；真实外部写禁用 |
| 质量 | 两个固定公开问题及一个脱敏文档，事实可回源，无法确认的内容显式标记 |
| 状态 | 重启自身容器后会话、配置和输出恢复，主机无需重启 |
| 隔离 | 无宿主敏感挂载、socket、提权或新增公开端口，策略写入被权限拒绝 |
| 预算 | 重试和辅助调用计费可核对，额度及超预算停止有效 |
| 主机保护 | 任务期间实际 SSH 重连成功，原联网配置不变，资源停止策略有效 |

部署实现和模板先入 Git 分支，再由批准流程应用。秘密和会话私有数据不入库。保留镜像 digest、配置及 Skills 版本、脱敏验收、受限备份。回滚仅停止本试点容器、撤销试点凭据或额度、恢复自身状态。Docker 的卸载单独检查其他消费者，禁止全局 prune。Wi-Fi、Tailscale、FRP、SSH 和 Discord 静态保留资料不在删除范围。

## 8. 本轮验收结果

| 项目 | 结果 | 证据与局限 |
| --- | --- | --- |
| 主机只读资源核验 | PASS | HOST_POSTRESET_PLAN；自动恢复复用当日重装验收 |
| 官方框架、稳定版本与扩展机制调查 | PASS | release、稳定 tag 配置/Dockerfile/fallback、官方文档 |
| GitHub 候选分类 | PASS | 37 仓库元数据及 12 README；未执行代码，未完成逐项安全审计 |
| 分批计划、预算、隔离和回滚 | PASS，文档层面 | 第 3 至 7 节，建议配置均未生效 |
| 安装、三路推理、故障注入 | 未执行 | 等待未来 B0/B1，实际 URL/model ID/额度待冻结 |
| PDF 及首批依赖、许可和权限审查 | B0 条件准入 | 已补齐固定源码与首批传递依赖声明，按 B0 子集执行；运行态尚未验收，第三方整包未纳入 |
| Discord | 范围外 | 未读取 token、未发消息，维持静态保留 |

本轮完成标准为调查与计划。部署验收未开始，不能据此宣称三模型已运行成功或扩展已安全安装。

## 历史报告，重装前采样，仅供追溯

以下内容保留原文。环境、连接状态和拟议路径全部属于重装前历史，现行部署判断以以上第 1 至 8 节为准。

# SpringMonkey 主机只读核验与 Hermes Agent 试点方案，历史

日期：2026-11-16，Asia/Tokyo。主目标：在 SpringMonkey 自托管 Muse 类个人助手，外接兼容模型并具备多模型兜底。本批授权为本机连接资料调查、远端只读核验和方案细化，暂不部署。

## 请求终态与实际终态

用户已确认调查对象为 Meta Muse.AI。已定位既有连接资料，利用本机已有凭据经 FRP SSH 登录，验证目标主机为 ubuntu-2625。基础证据采样时间为 15:32:14 至 15:32:20，补查为 15:34:20。SSH 使用已有 known_hosts 并拒绝未知主机密钥。未安装、拉取镜像、修改配置、重启、恢复 Tailscale 登录或发起模型推理。

结论：资源证据支持开展单用户、有资源限制的 Hermes 试点。长期生产可用性尚未验证。宿主系统已经结束支持，正式接入真实业务凭据前应先以独立变更完成受支持系统的升级或迁移；该操作不属于本批授权。

## 连接来源与证据

已有运维入口：

* [能力索引](../CAPABILITY_INDEX.md)
* [SSH 工具链](../ops/SSH_TOOLCHAIN.md)
* [主机访问约束](../ops/HOST_ACCESS_REDACTED.md)
* 本机历史任务脚本给出了已有密码文件位置。本次仅在 SSH 客户端内存中读取，未输出密码，未复制凭据。

本批主指导文档及原始证据保留于独立调查目录：

* [TASK_GUIDE.md](C:/workspace/codex-work/muse-selfhost-research-20261116/TASK_GUIDE.md)
* [基础只读证据](C:/workspace/codex-work/muse-selfhost-research-20261116/HOST_EVIDENCE.json)
* [历史负载及运行状态补查](C:/workspace/codex-work/muse-selfhost-research-20261116/HOST_FOLLOWUP.json)

上述 JSON 不含认证秘密。未复制原始环境变量、凭据、完整服务启动命令、消息内容及任务 Prompt。远程探针从 stdin 执行，未向远端写入脚本。SSH、访问日志等系统自行生成的审计记录仍可能发生。

## 实测配置与负载

| 项目 | 实际结果 |
| --- | --- |
| 系统 | Ubuntu 25.10，内核 6.17.0-41-generic，x86_64 |
| CPU | Intel Core i5-5200U，2 个物理核、4 个逻辑线程 |
| 内存 | 总计 7.14 GiB，采样时 available 5.71 GiB |
| Swap | 总计 4 GiB，已用约 620 MiB；5 个一秒增量样本的 si/so 均为 0 |
| 根文件系统 | ext4，总计约 328.62 GiB，可用约 249.54 GiB，df 占用 20% |
| 存储设备 | 系统报告非旋转块设备，标称 336G；未做物理设备性能测试 |
| 即时 load average | 0.03 / 0.03 / 0.00 |
| 短时 CPU | vmstat 增量样本 idle 99% 至 100%，无明显 I/O wait |
| 已有当日历史 | sar 当日约 00:00 至 15:30，CPU 平均 idle 97.68%、iowait 0.07%；平均 load 0.03 / 0.06 / 0.05 |
| 资源压力 | 采样时 PSI memory/io 的 avg10/60/300 均为 0 |
| OOM | 最近 24 小时可读内核日志未匹配到 OOM 关键记录；不等于全时段证明 |
| GPU | PCI 枚举看到 Intel HD Graphics 5500；nvidia-smi 不存在。本方案使用外部推理 |
| 虚拟化 | systemd-detect-virt 返回 none；CPU 有 VT-x，/dev/kvm 存在，未实际创建 VM |
| Docker | 服务 active，服务端 29.7.2，cgroup v2/systemd，driver 报告 overlayfs；docker ps -a 无容器 |

当日 sar 为离散区间统计，无法排除区间内瞬时峰值，也未覆盖所有周任务及未来并发。仅凭当前空闲不能承诺上线后的持续容量。

## 现有业务与异常边界

OpenClaw 运行中，healthz 返回 HTTP 200。服务 User=root，MemoryCurrent 约 564 MiB；常驻浏览器服务 User=openclaw，MemoryCurrent 约 659 MiB。两项均未配置 MemoryMax。HTTP 200 证明该健康端点响应，未验证 LINE、Discord、推理或定时任务的端到端功能。

运行中的系统定时器包括长任务监督、浏览器守护、cron 失败自愈、快照、仓库同步、日志保留和恢复备份。现有 OpenClaw 与浏览器分别监听 loopback 的 18789 和 18800。试点不占用或连接这些入口，不复用现有浏览器 profile、渠道机器人及状态目录。

当前 OpenClaw 配置列有 OpenAI 兼容 completions 网关，路径为 /v1，来自主机的 TCP 连接成功。配置的主模型为 openai-codex/gpt-5.3-codex-spark，备用项为带 openai-codex 前缀的 Qwen3.8-27B GGUF 模型。配置还列有其他型号。这些均为配置观测，未查询实时模型目录或验证推理，不能当作可调用模型清单。provider 名称也不能证明实际认证机制或底层供应商。

需单独记录的状态：

* Tailscale 服务进程 active，但 backend 为 NeedsLogin、self_online=false。FRP SSH 本次可用；现阶段没有经过验证的双通道冗余。
* failed units 包含 dmesg.service、ollama-keepalive-qwen.service、openclaw-update.service。本批未调查其根因或修复。
* 未找到文档所指的 /var/lib/openclaw/.openclaw/cron/jobs.json。此次没有进一步追查当前业务调度存储位置，因此未给出 Agent 内部任务数量或完成率。
* Ubuntu 官方确认 25.10 于 2026-07-09 结束支持。容器共享宿主内核，镜像更新无法覆盖宿主支持状态。

来源：[Ubuntu 官方 EOL 公告](https://lists.ubuntu.com/archives/ubuntu-announce/2026-July/000325.html)。以上异常不触发本轮修复或扩大调查。

## 建议试点架构

选择一个固定 digest 的 Hermes 稳定官方镜像，整体运行在专用 Docker 容器。terminal.backend=local 的执行范围限定在这个外层容器内；不挂载宿主 Docker socket，不给 privileged，不复用 OpenClaw 的执行权限。这一结构只需要单容器，避免同机嵌套 Docker 及把宿主控制权交给 Agent。

官方文档区分了整体运行于 Docker 与使用 Docker terminal backend 两种模式，并给出含浏览器时的内存预算。[Hermes Docker 文档](https://hermes-agent.nousresearch.com/docs/user-guide/docker)

这是一种适合非敏感试点的边界：工具与 Hermes 状态仍在同一容器，Agent 执行代码可能读取容器中的模型凭据。本方案使用专门试点 Key、限制额度，仅接入测试数据。需要更强的容器外凭据服务时，作为后续独立需求设计与验收。宿主上的既有 root 进程也属于信任边界，此次容器化无法防御宿主 root 被控制。

建议资源及停止预算如下，实施时验证具体镜像与参数兼容性：

| 项目 | 试点预算 |
| --- | --- |
| 同时进行的任务 | 1，不开放 delegate_task，不并发后台任务 |
| CPU 上限 | 1.5 个逻辑 CPU 的时间配额，与物理核数区分 |
| 容器内存 | 硬上限 3 GiB，memory+swap 总上限同为 3 GiB；试点容器不扩大宿主换页压力 |
| 进程上限 | 初始 512，包含浏览器子进程，按实际失败证据调整 |
| 浏览器 | 1 个页面为起始状态，最多 2 个标签；使用独立 profile |
| 数据与产物 | 初始软预算 10 GiB，宿主可用空间低于 40 GiB 时停止试点任务 |
| 日志 | 单文件 10 MiB、最多 3 份；保留必要脱敏任务证据 |
| 内存停止条件 | 宿主 available 连续 60 秒低于 1.5 GiB，或试点出现 OOM，停止试点并检查受影响项 |
| 单任务预算 | 15 分钟和 30 次模型请求双上限，先到即停止；原生限制不足时暂不启用无人值守任务 |
| 模型额度 | 专用凭据，试点累计预算建议 USD 10；以提供方或网关可执行额度限制落实 |

根盘为 ext4，不能套用依赖特定存储条件的容器磁盘硬限额。10 GiB 是容量管理预算，实施阶段需检查占用并执行停止策略，不能报告为已生效的内核硬配额。

路径规划采用 /srv/hermes-pilot，包含部署清单、data 和 artifacts。容器仅挂载这两个数据子目录；不挂载 /etc、/root、/var/lib/openclaw 或仓库目录。首次启动的权限、容器运行 UID 与浏览器兼容性通过固定镜像验证，失败不自动提升为 privileged。

第一阶段从既有 FRP SSH 进行交互，沿用连接主机时的认证。无需新增公网监听、FRP 映射或修改 Tailscale。若后续需要消息入口，再启用专用测试机器人并限制为用户本人；现有 LINE/Discord 机器人保持原配置。

## 模型与 Skills 具体范围

接入方式：现有兼容网关作为主路由候选，DeepSeek 与 Qwen 作为显式配置的备用路由。实施时先读取各端点实际模型目录及账户可用型号，并分别验证，不固定本次未测试的 ID。不给 Hermes 现有 OpenClaw 的完整配置或主凭据，申请或复用已获授权的限额试点 Key。

使用 Hermes 原生 fallback_providers，保持单一重试责任方。若现有网关也有备用策略，先确认并统一两层总时限与请求预算。图片任务单列能力组；具备相应输入能力且通过测试后方可参与视觉备用链。

官方提供 hermes fallback check 静态解析及 --live 最小请求验证。本轮均未执行，未来先做静态检查，再在模型调用授权范围内做实际请求。[Fallback Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers)

试点只引入四类 Skill：带原始来源引用的公开资料研究、Markdown/PDF 文档产出、测试网站的浏览器只读操作、试点目录内的定时产物生成。Skills 来源、脚本权限和依赖固定版本，自动生成的 Skill 保留为候选。禁止接入真实邮件发送、订单、生产数据库或生产部署动作。

保留人工审批，后台执行遇到待审批动作时停止；不自动批准无人值守请求。选用 local 后端的外层容器场景需要验证审批行为。[Hermes 安全文档](https://hermes-agent.nousresearch.com/docs/user-guide/security)

## 未来实施批次与验收

部署前置：用户授权实施；受支持宿主系统完成独立升级或迁移验收；固定镜像 digest；检查试点 Key 权限和额度；确认目录预算及停止机制。当前均未执行。

第一批只完成容器、文本与文档、模型接入及恢复验收，候选冻结后统一检查：

1. 宿主目录和凭据读取负例被拒绝，容器无宿主 socket，无额外公网入口，数据权限正确。
2. 每个模型完成文本、流式工具参数、工具结果续答、取消和失败反馈。注入 429、503、超时后按显式链路切换，无限循环或超预算均为失败。
3. 同一公开研究任务能核对原始来源，文档内容与产物可打开。持久状态备份、容器重建、记忆恢复分别验证。
4. 模拟写入试点文件后连接中断，恢复时通过操作记录核对结果，目标写入只发生一次。
5. 执行全过程记录宿主 available、CPU、swap、试点 cgroup 与现有 OpenClaw/浏览器状态。触发预算则停止试点，保留既有服务。

第二批在第一批有效证据之上加入独立浏览器、定时任务及可选测试消息入口。浏览器使用固定测试网站和测试数据，核对真实截图、交互、console、网络及受支持视口；定时任务验证中断恢复、取消及重复触发保护。文档产物按格式检查引用及渲染。按用户的后续需求决定是否进入第二批。

回滚仅针对试点：停止并移除试点容器；先保存需要保留的脱敏记录和产物，再按清单清理试点目录、镜像及专用网络；撤销试点 Key 与测试机器人权限。禁止使用全局 Docker prune，不修改现有 OpenClaw、Chrome、FRP、Tailscale 及其定时器。备份恢复试点状态前须明确旧凭据是否仍可使用。

## 本轮验收矩阵

| 项目 | 判定与证据 |
| --- | --- |
| 已有连接来源和目标身份 | PASS，工具链资料、既有 known_hosts 和远端 hostname 对应 |
| 主机配置及当前负载 | PASS，基础 JSON 和当日 sar 补查；短时/区间统计局限已注明 |
| 现有业务与资源共存边界 | PASS，服务/cgroup、端口、定时器及失败项记录 |
| Hermes 具体试点方案 | PASS，资源、目录、凭据、模型、Skills、验收、停止和回滚条件已定义 |
| 本批只读边界 | PASS，远端仅查询；模型和部署动作未执行 |
| 主机系统升级、Hermes 运行验收 | 未执行，属于后续授权范围 |

本报告 PASS 仅覆盖调查与方案交付，不代表试点已部署或产品已经达到 Muse 的运行质量。
