# SpringMonkey 自托管 Agent 替代方案调查

用户在 [三候选固定稳定版比较](AGENT_FINAL_COMPARISON_2026-11-16.md) 后明确选择 **Hermes 主选，Skills 生态优先**，当前部署准备见 [首批 Skills 与模型接入计划](HERMES_FIRST_BATCH_SKILLS_2026-11-16.md)。本文保留广泛候选事实与此前对照思路，不再构成多平台部署建议；未安装或执行 B1。

日期：2026-11-16，Asia/Tokyo。范围：近期 News、官方技术文章、GitHub 及本机适配分析。仅调查，无主机连接、安装、部署、推理请求或 Discord 接入。Hermes 原计划继续保留，本文不代表已决定更换。

## 1. 当前结论

当前按用户选择收口到 **Hermes**。此前调查将 nanobot、Agent Zero、goose、QwenPaw 纳入可比候选，相关能力事实保留。goose 适合重视 MCP/CLI 工具生态的使用方式，QwenPaw 适合重视中文生态与可视化管理的使用方式。下列分用途判断不改变当前主选，也没有本机横向实测。

* 想尽快获得带 WebUI、记忆、定时任务和多模型链的个人助手：优先核查 nanobot。
* 想要研究、浏览器、文件、终端集中在一个可视工作台：优先核查 Agent Zero。
* 想接入现成 MCP 工具并以 CLI 工作：优先核查 goose。
* 想接入中文平台、管理 Skills/Plugins 和多个 Agent：核查 QwenPaw，单独验证自动兜底。
* 想长期开发自己的 Harness：选择 Deep Agents 或 Pi 作为工程底座，另行承担服务、权限、任务调度与运维实现。

SpringMonkey 指刚重装的物理主机 `ubuntu-2625`，沿用当日已验 Ubuntu 26.10、i5-5200U、2 物理核/4 线程、约 7.14 GiB 内存，模型外置。此次不重新采样负载，也不安装本地模型。候选资源负担按组件结构判断，以下轻/中/重均非 RAM 实测值。

原 [B0](HERMES_B0_PREFLIGHT_2026-11-16.md) 的入口阻塞继续有效：现有兼容服务发布在 Windows loopback，SpringMonkey 到其私有上游端口超时。更换 Agent 软件不能直接消除该连接条件；未来试点仍需先落实主机可用的安全模型入口。

## 2. GitHub 当前数据与项目类别

公开 API 采样记录 16 个当前有效仓库，并保留一个失效旧路径的查询结果。读取 16 份当前 README、相关配置/许可及 8 个项目最新非预发布 release 元数据。Stars 是关注度指标，最近推送可包含文档和分支更新，不能单独证明质量、安全或稳定发布。数据源为仓库 GitHub API，原始记录见文末证据目录。

| 项目 | Stars | 最近推送 UTC 日期 | 当前类别、许可与本机判断 |
| --- | ---: | --- | --- |
| [nanobot](https://github.com/HKUDS/nanobot) | 50,123 | 2026-11-16 | MIT；Python 个人助手，WebUI/CLI、记忆、自动化、MCP；优先候选 |
| [Agent Zero](https://github.com/agent0ai/agent-zero) | 19,879 | 2026-11-16 | 实际 LICENSE 为 MIT，API 未识别；Docker/Linux 工作台；优先可视化候选 |
| [goose](https://github.com/aaif-goose/goose) | 56,681 | 2026-11-16 | Apache-2.0；Rust 通用执行 Agent，CLI/API/Desktop，MCP；优先候选 |
| [QwenPaw](https://github.com/agentscope-ai/QwenPaw) | 37,814 | 2026-11-16 | Apache-2.0；个人助手、Console、Skills/Plugins；候选 |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | 33,377 | 2026-11-16 | MIT OR Apache-2.0，已查实际 MIT 文件；Rust 常驻 Agent，适合继续核查轻量运行 |
| [PicoClaw](https://github.com/sipeed/picoclaw) | 30,133 | 2026-11-05 | MIT；Go 轻量助手；可用于简单常驻任务，完整文档/浏览器链待验证 |
| [NanoClaw](https://github.com/nanocoai/nanoclaw) | 31,118 | 2026-11-16 | MIT；按 Agent 容器隔离，默认 Claude Agent SDK；多模型需额外 provider 路径 |
| [IronClaw](https://github.com/nearai/ironclaw) | 12,717 | 2026-11-09 | MIT OR Apache-2.0，已查 MIT 文件；WASM 能力权限、凭据隔离；候补 |
| [OpenHands](https://github.com/OpenHands/OpenHands) | 93,581 | 2026-11-16 | MIT 主仓库；Agent Canvas/SDK、代码与开发工作流；偏编码时再优先 |
| [OpenCode](https://github.com/anomalyco/opencode) | 227,209 | 2026-11-16 | MIT；编码 Agent/CLI；个人助手的常驻服务和任务管理需另行设计 |
| [Pi](https://github.com/earendil-works/pi) | 122,306 | 2026-11-16 | MIT；极简 Harness/SDK、扩展与 Skills；自主开发成本较高 |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | 31,325 | 2026-11-16 | MIT；规划、文件系统、记忆、子 Agent 的 SDK/Harness；需工程集成 |
| [Dify](https://github.com/langgenius/dify) | 161,269 | 2026-11-16 | 附加条件的 Apache 派生许可；可视工作流/RAG/应用平台；多服务部署负担较大 |
| [n8n](https://github.com/n8n-io/n8n) | 210,600 | 2026-11-16 | Sustainable Use License，企业部分另许可；业务工作流和连接器平台；可作后续补充 |
| [Khoj](https://github.com/khoj-ai/khoj) | 38,146 | 2026-08-02 | AGPL-3.0；个人知识、搜索与研究；当前推送较久，暂缓主选 |
| [Flowise](https://github.com/FlowiseAI/Flowise) | 55,568 | 2026-08-13 | 原仓库已归档；LICENSE 有不同代码区域条款，当前不推荐作为新试点主线 |

维护状态与来源修正：

* `block/goose` 的 API 重定向到 `aaif-goose/goose`，README 确认属于 Linux Foundation 下的 AAIF。
* `qwibitai/nanoclaw` 重定向到 `nanocoai/nanoclaw`。
* `mariozechner/pi-mono` 本次返回 404；从公开来源定位当前 `earendil-works/pi` 并重新核对。旧地址失败不能证明项目停止维护。
* [Flowise 页面](https://github.com/FlowiseAI/Flowise) 明确标记 2026-08-13 archive。此状态使历史高星榜单不足以作为新项目推荐。

## 3. 值得关注的近期动态

以下分清事件日期、发布版本和分析文章。功能新闻作为调查线索，稳定性仍以具体版本测试为准。

| 日期 | 一手动态或文章 | 对本次选型的意义 |
| --- | --- | --- |
| 2026-11-16 | [goose v1.59.2](https://github.com/aaif-goose/goose/releases/tag/v1.59.2) | 当天仍有稳定补丁发布，该版本修正 Databricks thinking blocks；不能从补丁推断所有模型兼容 |
| 2026-11-12 | [ZeroClaw v0.9.0](https://github.com/zeroclaw-labs/zeroclaw/releases/tag/v0.9.0) | 新增可选 OIDC dashboard 登录及权限、会话隔离改进；个人单用户暂不需要启用 OIDC |
| 2026-11-12 | [OpenHands v1.40.0](https://github.com/OpenHands/OpenHands/releases/tag/v1.40.0) | 软件开发平台继续更新，当前 README 支持多个 Agent 后端；应评估实际所需功能后再引入 |
| 2026-11-11 | [QwenPaw v2.3.0](https://github.com/agentscope-ai/QwenPaw/releases/tag/v2.3.0) | 插件系统/SDK、Code Mode、协作与模型相关能力更新；插件生态有扩张，升级兼容仍需逐项确认 |
| 2026-11-06 | [nanobot v0.4.1](https://github.com/HKUDS/nanobot/releases/tag/v0.4.1) | 涉及 TLS、shell sandbox、workspace 权限及恢复修正；轻量项目也持续处理可靠性问题 |
| 2026-11-05 | [LangChain: Agents Are Going Async](https://www.langchain.com/blog/agents-are-going-async) | 交互编排者保持可响应，后台子任务独立运行；任务通知仍为 beta |
| 2026-11-01 UTC | [Agent Zero v2.15](https://github.com/agent0ai/agent-zero/releases/tag/v2.15) | 多动作工具支持按 action 授权，文件读/写、定时任务列举/删除可分开控制 |

新闻评论补充：[TechRadar Pro 2026-11-11 的权限访问评论](https://www.techradar.com/pro/openclaw-is-creating-a-new-privileged-access-problem-for-security-teams)讨论自主 Agent 使用凭据和高权限工具的风险。该页面标记为 Opinion，此处只作舆论关注方向，不作为任何项目已被攻破或安全优劣的证据。

近期技术方向是状态持久化、可恢复长任务、可响应的后台执行、工具权限和可观测性。该方向可从上述一手公告归纳，不能据此声称每个项目都已经达到同等能力。

值得对照的早期工程文：[Anthropic，Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)，发布于 2025-11-26，强调初始化环境、分次推进与交接产物。其作用是方法参考，日期与本轮最新动态分别记录。综合这些资料，Harness、模型适配、状态、工具、权限和验收流程共同决定可用性；单纯增加 Agent/Skill 数量没有质量保证。

## 4. 重点候选的模型、扩展与边界

### nanobot：保留为资源与组件收敛的比较候选

当前官方文档提供 WebUI/CLI、会话、长期记忆、自动化、MCP、Skills 与 model presets。Python 3.11+，可走 Docker 或 Linux 服务。单实例配外部模型符合本机的规划方向；没有进行内存/吞吐对比。

稳定 tag [v0.4.1 的模型兜底指南](https://github.com/HKUDS/nanobot/blob/v0.4.1/docs/guides/configure-model-fallback.md)已确认 `agents.defaults.fallbackModels` 是有序 preset 链，各候选保持独立模型/服务参数。字符串是 preset 名称，不能直接填原始 model ID。该机制能表达 ChatGPT 兼容 → DeepSeek → Qwen。

注意：默认 workspace 限制属于应用边界，README 明确说明它不构成 OS sandbox。不同 topic/project 也不自动分离长期记忆，同一实例共享 agent profile、memory 和 skills。未来公司与私人环境应采用经验证的独立实例/数据目录，不靠聊天话题区分。模型逐路协议、拒绝终态、已执行工具后的切换仍要故障注入验证。

### Agent Zero：优先考察完整操作工作台

[官方仓库](https://github.com/agent0ai/agent-zero)提供 Docker 内 Linux 工作区、WebUI、terminal/browser/document 工具、Projects、Skills 与插件。对希望通过浏览器查看任务和文件的用法更接近完整 Agent 产品。服务端有无桌面的 SSH 安装路径，未来可只绑定 loopback，经现有 SSH 使用。

[安装文档](https://github.com/agent0ai/agent-zero/blob/main/docs/setup/installation.md)支持选择模型供应商及自定义接口；模型 preset 可分别设置 chat、utility、browser、embedding。[v2.15](https://github.com/agent0ai/agent-zero/releases/tag/v2.15)的 action 权限有助于限制首批任务范围。

当前核查没有确认与 Hermes 同等的、配置即用的跨供应商有序自动兜底契约。多个 preset、多个角色模型和遇错换模型并非同一件事；需查选定版本实现或使用经过验证的模型路由层。浏览器/桌面/多子任务会增加进程与内存，本机只规划一个实例、一个任务，不启用完整桌面与多 Agent 并发。辅助模型及 embedding 可能产生独立费用。

### goose：重视通用工具生态与 CLI 时优先

当前 [官方 README](https://github.com/aaif-goose/goose)明确定位通用 Agent，提供 CLI、API 和可选 Desktop，采用 Rust、Apache-2.0，支持 MCP 扩展。可用于研究、写作、数据和自动化，适合这台无桌面服务器选择 CLI 使用。

[供应商文档](https://github.com/aaif-goose/goose/blob/main/documentation/docs/getting-started/providers.md)包含 OpenAI-compatible 服务及 LiteLLM。三供应商有序自动兜底尚未在本轮确认，可将 LiteLLM 等兼容路由层列入独立选型，不能因为供应商很多便宣称自动容灾已经成立。MCP 扩展是工具进程，权限和凭据需要逐个收敛。

### QwenPaw：中文生态和 Console 管理有吸引力

[官方仓库](https://github.com/agentscope-ai/QwenPaw)提供 Console/TUI、长期记忆、多个 Agent、Skills、Plugins 和 MCP，并支持自定义供应商。外部模型模式符合本次条件，首批无需下载 QwenPaw-Flash 或启动本地推理。

[模型文档](https://github.com/agentscope-ai/QwenPaw/blob/main/website/public/docs/models.en.md)确认自定义 provider，支持多模型管理。自动供应商降级仍有 [公开功能请求 #4757](https://github.com/agentscope-ai/QwenPaw/issues/4757)；本轮所读模型文档未确认既定三路顺序兜底。开放 issue 本身不能证明当前代码完全缺少能力，需在冻结版查证。Console、多 Agent 及插件环境增加维护面，首批只启用单 Agent 和必要插件。

### ZeroClaw、PicoClaw、IronClaw、NanoClaw：各有特定优势

* **ZeroClaw**：Rust 原生运行时，有自定义兼容接口、workspace/命令策略及 sandbox 选择。稳定 [v0.9.0 provider 配置](https://github.com/zeroclaw-labs/zeroclaw/blob/v0.9.0/docs/book/src/providers/configuration.md)有同 provider 的 `fallback_models` 及跨 alias 的 `fallback`。它对部分 refusal 的继续切换语义需要与既定“正常拒绝终态”要求核对，不能原样照搬链路后宣称通过。
* **PicoClaw**：适合低资源常驻助手。README 自述的 10 至 20 MB 是特定核心场景，不包含浏览器、解析库和任务峰值，不能作为全套任务系统容量承诺。完整文档工作流需验证。
* **IronClaw**：WASM 工具能力权限、凭据处理和 Docker 执行值得关注。当前 README 已是 Reborn 布局，旧资料的数据库和路径信息可能过时，本轮不固定其数据库部署方案。进入候选 B0 后核对 release、默认存储与工具适配。
* **NanoClaw**：按 Agent 容器隔离与模板有价值。默认 Claude Agent SDK，README 说明其他 provider 通过 Skills 安装，支持 `/add-opencode` 路径。将该扩展路径与 ChatGPT/DeepSeek/Qwen 的工具语义一并验收，避免低估安装与后续维护成本。

## 5. 开发底座与工作流平台

| 路线 | 能提供什么 | 仍需自行负责的部分 |
| --- | --- | --- |
| [Deep Agents SDK](https://docs.langchain.com/oss/python/deepagents/overview) | planning、filesystem、Skills、memory、subagents；支持 LangChain 模型适配 | 自托管服务、入口、持久存储、工具沙箱、预算与部署。可组合 [ModelFallbackMiddleware](https://reference.langchain.com/python/langchain/agents/middleware/model_fallback/ModelFallbackMiddleware)，仍需端到端验证 |
| [Pi](https://github.com/earendil-works/pi) | 精简 Agent loop、CLI、SDK、扩展、Skills、多供应商统一 API | 权限系统与长驻助手产品层；README 明确默认使用启动进程的权限，需要自行容器化/沙箱化 |
| OpenHands / OpenCode | 代码仓库任务、开发工具及程序执行，有现成 CLI/服务路径 | 通用个人助手的日程、知识和生活任务流程需额外配置；OpenHands 多 sandbox 后端由操作员管理，不能给任务 Agent 宿主 Docker 管理权 |
| [Dify](https://docs.dify.ai/en/self-host/deploy/quick-start/docker-compose) | 可视工作流、RAG、工具和应用发布 | 多服务运维。官方最低 2 核/4 GiB，满足最低门槛不代表与浏览器任务共存有足够余量 |
| [n8n Tools Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent) | 业务连接器、工具调用、可视化工作流 | 为开放式任务设计流程、文件执行环境及跨会话记忆；节点与工具的能力不自动等于个人助手 Harness |

Deep Agents 开源 SDK 可自托管；新闻中的 Managed Deep Agents 由 LangSmith 托管。[2026-11-02 更新的官方介绍](https://www.langchain.com/blog/introducing-managed-deep-agents)说明其 public beta/cloud 路径。选择自托管时要核对 OSS 可用能力，不能把托管浏览器、调度和权限服务直接计入本地 SDK。

[Dify LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)带多租户及前端标识等附加条件；[n8n LICENSE](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)区分 Sustainable Use 与企业文件。它们的 Stars 很高，许可、运行组件及用途仍需独立判断。本文仅记录条款与适用范围，不作法律结论。

## 6. 推荐的下一轮对照方式

前次调查建议用 nanobot 对照轻量助手、多模型链，用 Agent Zero 对照完整工作台，现已完成固定源码比较。用户当前选择 Hermes，先推进其明确的 B0 收口。其他平台比较仅在后续有独立需求时重开，不在同一主机同时安装多套系统。

未来经用户授权测试时，统一使用同一个已可达、限额明确的兼容接口和相同任务样例：公开网页研究、本地脱敏 PDF 提取、带引用报告、三模型故障注入、容器重启恢复。记录正确率、来源可追溯性、请求数/费用、峰值内存、耗时、操作员干预和工具权限。先单任务，无 Discord、无生产数据、无宿主控制权。实际优胜者由该证据决定。

此次没有做上述产品安装或横向测试，没有为任一候选填运行 PASS。多框架均接同一不可达接口时会共享 B0 阻塞；应先解决接口可达与额度，再进入受控比较。

## 7. 证据与本轮验收

公开元数据、README 快照、release 与许可证保存在 [调查证据目录](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/agent-alternatives-20261116)，包括 GITHUB_CANDIDATES.json、OFFICIAL_SOURCES.json、DETAIL_SOURCES.json 及源码文本哈希。大部分材料取自当前默认分支，nanobot/ZeroClaw 的关键兜底文档额外读取稳定 tag。后续安装仍须重新冻结版本，当前文档快照不能替代运行验收。

本轮验收：近期消息有具体日期与来源，候选有当前 Stars/维护状态和类别，模型及许可差异明确，结合主机约束提出有条件排序，原 B0 阻塞保持。通过条件为调查/文档完成；实际协议、资源、工具隔离和任务效果未测试。
