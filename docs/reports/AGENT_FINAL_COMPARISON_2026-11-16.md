# SpringMonkey 的 Hermes、nanobot、Agent Zero 最终选型建议

日期：2026-11-16，Asia/Tokyo。状态：公开资料与固定稳定源码比较完成，最新选择已同步为 Hermes。未部署、未运行产品、未推理、未连接 Discord。原比较沿用当日主机配置；后续 Hermes 只读连通性复查单列在首批 Skills 计划中。

## 1. 最终推荐

**按用户最新选择，以 Hermes 作为 SpringMonkey 的主选，优先发挥 Skills 生态。** 目标仍为约 7.14 GiB 内存单机、外接 ChatGPT 兼容服务及 DeepSeek/Qwen、单任务研究和文件处理，逐步加入浏览器，不接消息渠道。

此前偏重资源与组件收敛的调查推荐 nanobot，属于历史建议。其稳定版跨供应商备用链、错误分类和文件读取的比较证据保留。当前用户将 Skills 生态列为主要依据，选型已调整为 Hermes；稳定版拒绝处理与在线文档的差异仍是部署前置。Agent Zero 的工作台及其资源、容灾证据维持原比较结论。

产品运行验收未开始，当前只更新计划。首批 Skills、依赖与模型入口的新证据见 [Hermes 首批清单](HERMES_FIRST_BATCH_SKILLS_2026-11-16.md)。B0 的入口、独立备用服务及额度、拒绝语义问题依然阻止部署。[B0 记录](HERMES_B0_PREFLIGHT_2026-11-16.md)

## 2. 比较对象与证据层级

本轮重新核对最新非预发布 release，固定提交后读取关键实现。下载文件核对 Git blob SHA 与内容 SHA256，没有执行第三方源码。

| 对象 | 当前稳定版 | 发布时间 UTC | 固定 commit |
| --- | --- | --- | --- |
| [Hermes](https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.1) | v0.23.1 | 2026-11-10 01:42 | `3b421578588243f920886e6fe79a6faa87ea026e` |
| [nanobot](https://github.com/HKUDS/nanobot/releases/tag/v0.4.1) | v0.4.1 | 2026-11-06 15:55 | `3404fe83e22b7b2cb3edae1348ed45dd9b8ad051` |
| [Agent Zero](https://github.com/agent0ai/agent-zero/releases/tag/v2.15) | v2.15 | 2026-11-01 23:52 | `ba9b67df0f54ac78106ae85c552ef5d2458f7c9a` |

证据优先顺序：固定源码中的实际控制流程、同版本说明、在线文档、README 概述。源码观察仍受未执行的限制。Stars、Skill 文件数和 advertised footprint 均不用于推导质量或实测性能。

## 3. 五项对照总表

| 领域 | Hermes v0.23.1 | nanobot v0.4.1 | Agent Zero v2.15 |
| --- | --- | --- | --- |
| 多模型兜底 | 原生跨供应商链、单独凭据、冷却与辅助调用路由；部分拒绝路径需要修正验收判断 | 原生 preset 顺序链、独立参数、错误分类和熔断；流式切换有明确限制 | 模型预设、角色模型及同模型重试；尚未确认一等三供应商顺序容灾配置 |
| Skills | 稳定树有 44 bundled、141 optional、1 plugin Skill 定义，官方目录与审核 pin 机制较完整 | 11 个内置 Skill 定义，workspace/Apps/ClawHub 扩展；更多业务流程需要选取、适配 | 7 个 skills/ 定义及 18 个插件内 Skill，UI 中按需/固定加载，与 Profiles/Projects 联动 |
| 浏览器 | 内置本地 Chromium/CDP，另有云端与其他 engine 选项 | 本轮核心工具树未发现同等级内置浏览器，主要通过 MCP 加入 | 内置 Docker 浏览器与可观看、交互的 Canvas，另有可选宿主连接 |
| 文件 | 现成 PDF/Office Skills 丰富，PDF 提取部分依赖需侧环境准备 | read_file 已直接支持 PDF、DOCX、XLSX、PPTX 文本读取，核心依赖包含读取库 | 文档查询、解析/索引/OCR、文件浏览和 LibreOffice 等完整路径 |
| 权限与资源 | 初始 root 后降权，需容器挂载/cgroup；镜像已有 Chromium 等较广依赖 | 初始 root 后 setpriv 降权，应用路径边界及可选 bwrap；基础镜像较收敛，MCP 需另审 | Docker 是主要宿主边界；工具 action 授权细，Kali/搜索/Office/本地 embedding 等组件需控制 |

Skill 数量来自固定 Git tree 的 SKILL.md 文件计数，排除 tests/templates；不能把 optional、插件和实际启用数混用。三者仓库主许可均为 MIT，外部插件、模型和原生依赖另审。

## 4. 多模型兜底：nanobot 与 Hermes 领先，细节不同

### Hermes

稳定源码 [chat_completion_helpers.py](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/agent/chat_completion_helpers.py)逐项绑定备用模型的 provider/client，在当前任务中切换，并记录实际路由和原因。凭据、接口协议和 provider pool 重新绑定，适合跨服务备用；[error_classifier.py](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/agent/error_classifier.py)区分额度、认证、超时、404、请求格式和策略错误。辅助压缩/视觉等还具有独立路径，因此需要防止辅助调用意外转到其他收费服务。

重要修正：[在线兜底文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers)描述部分 refusal 为终态；固定 v0.23.1 的 [turn_truncation.py](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/agent/turn_truncation.py)中 `handle_content_policy_refusal` 实际包含调用备用激活器的路径，激活器本身没有对该 reason 提供统一拒绝门槛。只要有可激活候选，就存在继续切换的代码路径。此为源码结论，未以生成请求复现，不等于所有拒绝或所有 adapter 都必然触发。

因此，原计划“内容拒绝保持终态”仍是验收要求，**v0.23.1 尚不能凭在线文档判为满足**。需要选取行为一致的后续版本或经过独立授权的最小修正再测试；本轮不改源码。先前报告的对应描述已补充撤回与限制，不能继续使用旧结论放行。

### nanobot

稳定 [fallback_provider.py](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/nanobot/providers/fallback_provider.py)为请求级包装器，先耗尽当前 provider 的有界重试，再按 preset 顺序尝试。每个备用保留自己的模型、输出参数、reasoning 和 provider 状态能力。

| 情况 | 固定源码观察 |
| --- | --- |
| 超时、连接、429、过载、5xx、额度不足 | 符合类别或结构化错误条件时允许切换 |
| 认证及 401/403 | 有切换路径；不能据此掩盖待修复的配置故障 |
| 普通 400/404/422 | 默认不切换；模型 ID 错误需要明确修复 |
| refusal/content_filter/context_length/invalid_request | 在正常分类路径明确列为不切换；结构化错误和网关映射仍需实测 |
| 已输出部分流式文本 | 通常停止跨模型切换以避免重复；timeout 存在分段恢复例外 |
| 主路连续失败 | 3 次后熔断，冷却 60 秒；源码默认值，不是本机测试结果 |
| provider continuation / 原生压缩 | 不兼容的 state 不直接交给新 provider；需要原生压缩继续状态而备用无法承接时会跳过 |

它不保证所有跨模型切换都无损，尤其是 provider 独占状态、较小上下文和半截流式输出。与其文档配合，足以将它列为原生多模型主候选。三路均需独立调用，再做故障注入；已经执行的工具不能因模型切换重放。

### Agent Zero

读取固定 [models.py](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/models.py)、[litellm_transport.py](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/helpers/litellm_transport.py)及模型 preset 实现：已核查路径对同一模型做瞬时错误重试，通常要求尚无流式块才重试；Responses 与 Chat Completions 之间存在协议兼容恢复。该协议恢复不能当作跨供应商三路容灾。

多个 preset，以及 chat/utility/browser/embedding 分工，提供选择不同模型的能力。本轮没有确认与前两者同等级的一等有序跨供应商链，不能简单判定它完全不存在任何 LiteLLM/插件扩展路径。要实现用户要求，需要额外验证受支持配置，或增加明确负责容灾的模型路由服务，带来更多部署与费用归因工作。

三者共用一个网关时都共享该网关故障域；换 Agent 不改善不可达入口。应至少一路备用具有独立服务和额度，三路上下文可发送范围一致，拒绝终态与工具不重放须纳入检查。

## 5. Skills：Hermes 现成覆盖最广，三者都需要权限边界

**Hermes** 的优势是官方 bundled/optional 内容、搜索安装、插件 catalog 与 source pin 体系，且前序 B0 已审查首批 PDF/待办/Office 依赖。按需加载能减少常驻提示量。其优势来自可审查的任务流程覆盖，不能仅用 Skill 数或 Stars 推导成功率。默认播种、自修改和 skill_view 可见性需要按现有 B0 方案收敛。

**nanobot** 的 [SkillsLoader](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/nanobot/agent/skills.py)读取内置与 workspace 下的 SKILL.md，处理禁用项和可用条件，也能通过 Apps/ClawHub 扩展。它能承接标准结构的单项技能，但 Hermes 的特定工具名、辅助模型、路径、脚本和 metadata 不会自动变成等价能力。首批只需研究与报告流程，直接文件读取已覆盖相当一部分需求。

**Agent Zero** 的 [Skills 说明](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/docs/guides/skills.md)提供按需加载及 UI pin，活动 Skill 会进入每轮 protocol；Profiles 定角色，Projects 管工作区/记忆/秘密。插件内还包含 browser、office、document-query 等专用 Skill。其优势是可视管理与工具联动，执行脚本和插件仍需逐项审核。

共同原则：不整包导入、不自动更新、不让 Agent 管理员权限安装插件。记录 source commit、依赖和外部域名，保持管理员策略与工作输出分开。Skill 是任务指令，文件可读/可写和出网权限依然由工具、账号、容器和凭据决定。

## 6. 浏览器和文件处理

### 浏览器

* **Hermes**：固定版 browser 工具及同版说明包含本地 Chromium/CDP，适合直接加入动态页面任务。在线页面还有多种云浏览器与 profile 选项，不能将在线新增细节全部当成固定版实测。选择容器内独立空白 profile；不复制真实 Chrome 登录态、不开放 CDP 公网端口。browser_exec 能批量执行浏览步骤，模型和超时需限制。
* **nanobot**：稳定核心有 web_search/web_fetch 和 MCP 客户端；本轮所查工具树没有找到与上述两者同等级的内置交互浏览器。[MCP presets](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/docs/mcp-presets.md)包含 Browserbase，其他浏览器可经 MCP 加入。若选择本地 Playwright MCP，需要再核版本、Node/browser、profile、目录和生命周期；本轮未安装或验证该组合。首批公开资料提取无需先启动 Chromium。
* **Agent Zero**：[同版 Browser Guide](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/docs/guides/browser.md)有内置 Docker browser 和可观看/交互的 Canvas，截图、标注和人工介入的产品能力较完整。另有宿主浏览器连接方式，本试点不启用宿主 connector。

可视页面理解可能调用视觉/辅助模型，不能让未经验证的文本 DeepSeek/Qwen 路由无条件承担视觉备用。三者都应限制为一个浏览会话、少量页面，访问登录网站前再定义专门凭据和权限。

### 文件

**nanobot 比前次概述更完整。** 固定 [filesystem.py](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/nanobot/agent/tools/filesystem.py)和 [document.py](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/nanobot/utils/document.py)直接读取 PDF/DOCX/XLSX/PPTX，返回可分段文本；核心 pyproject 已包含 pypdf/python-docx/openpyxl/python-pptx。文件工具有 100 MiB 上限及单次 PDF 页范围限制，实际入口之间页上限不同，不能概括为所有解析器同一上限。文本读取不证明公式计算、版式渲染、扫描 OCR 或复杂表格正确。

**Hermes** 有丰富的 PDF/Office 操作 Skill。已知稳定镜像选择 documents，pdfplumber/pypdfium2 等 documents-pdf 侧环境仍需准备，不能让 Agent 首次任务临时联网安装。读取、生成和版式验收可以分阶段加入。

**Agent Zero** 的 [Document Query 插件](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/plugins/_document_query/README.md)包含解析、索引、OCR、并发和超时控制；源码还提供固定 LibreOffice 安装路径。默认 embedding 在 CPU 本地运行，查询索引、OCR 和 Office 转换可能增加 CPU/内存及辅助调用。外接主模型不能消除这些本地成本。

本轮只读源码，未生成、渲染或验证实际文档。扫描件、财务工作簿、长 PDF 及带宏文件均不作为“默认可处理”保证。

## 7. 权限隔离：容器与工具权限各自验收

| 边界 | Hermes | nanobot | Agent Zero |
| --- | --- | --- | --- |
| 镜像启动 | root 初始化 s6/归属后降为 hermes | root 初始化数据归属后经 setpriv 降为 nanobot | Kali 基础容器，初始化和 supervisor 可管理系统；本轮不宣称 Agent 进程 UID 已实测 |
| 文件/工具策略 | 命令审批、文件写限制、toolsets；terminal/backend local 在外容器内执行 | restrictToWorkspace 是应用限制；read/write 工具有路径控制；shell 可关闭或选择 bwrap | Profile 可按 tool/action allow/block，支持明确拒绝优先；默认继承策略不能直接当白名单 |
| shell 与网络 | 任意代码工具应视为拥有其运行账号的容器权限 | bwrap 仅作用于对应 shell；源码未加 unshare-net，文档也明确网络不隔离；stdio MCP 有自身权限 | 通用 terminal 可能实现其他被禁工具的相似功能，不能用某个 action 禁用证明数据隔离 |
| 多用户/数据 | profile/会话边界需配合各自路径与凭据 | 同实例 topics/projects 共享长期记忆；WebUI 是可信管理员界面 | Projects 是逻辑作用域，不能当每项目独立 OS 容器 |

权限依据：[nanobot 安全指南](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/docs/guides/secure-local-ai-agent.md)、[shell sandbox](https://github.com/HKUDS/nanobot/blob/3404fe83e22b7b2cb3edae1348ed45dd9b8ad051/nanobot/agent/tools/sandbox.py)、[Agent Zero tool_policy](https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/helpers/tool_policy.py)、[Hermes 安全说明](https://hermes-agent.nousresearch.com/docs/user-guide/security)。部分 Hermes 同版 Markdown 下载遇 429，保留错误证据，使用已取得固定源码及在线说明限定结论，未反复下载。

未来三者统一采用单外容器、最小工作区挂载、无 privileged/host network/docker.sock/宿主 SSH key、无 Tailscale/FRP 状态及 Discord 备份。禁止把 Agent 账号加入宿主 docker 管理组。公司与私人数据将来需要互不信任边界时使用独立实例和目录，另行评估 OS 隔离。

nanobot Dockerfile 中运行 venv 可写、启用渠道可安装依赖；Hermes 初始化有播种/迁移，Agent Zero 有插件安装/自更新路径。冻结候选时均需禁用任务运行期间自动更新，准备依赖与只读策略。容器内推理凭据可能被同权限代码读取，独立低额度 key、最小输入和出网约束仍是必要条件。三者本轮均未获“安全通过”。

## 8. SpringMonkey 资源与安装负担

硬件沿用当日已验：i5-5200U，2 物理核/4 线程，7.14 GiB RAM，约 304 GiB 根盘可用，4 GiB swap；主模型全部外接。可用内存 6.64 GiB 是前序采样，当前未重测。

| 资源维度 | Hermes | nanobot | Agent Zero |
| --- | --- | --- | --- |
| 固定源码基础 | Debian/Python、Node、Chromium、FFmpeg 等 | Python 3.12 slim、bubblewrap、WebUI 静态产物；Node 主要用于构建，浏览器额外安排 | Kali 基础、搜索服务、浏览器、LibreOffice 等组件 |
| 部署负担判断 | 中等，原生浏览器减少后续拼装 | 基础较收敛；加浏览器后仍承担 Chromium/MCP 成本 | 更高，需控制默认本地 embedding、OCR、桌面及子 Agent |
| 已有磁盘证据 | B0 registry 压缩 layers 1.04 GiB，解压与数据目录未测 | 本轮未查匹配镜像 digest 的体积 | 本轮未查匹配镜像 digest 的体积 |
| 依赖复现 | Hermes B0 已核部分锁定依赖，镜像 pin 已取得 | pyproject 多处版本范围，B0 需锁解析结果、镜像及 MCP 依赖 | 基础镜像/包和插件多，需固定运行镜像与启动后安装选择 |
| 当前主机适配 | 当前主选，须单实例/单任务实测 | 资源和组件收敛方向的比较候选 | 可试验，完整工作台峰值和常驻成本更不确定 |

以上负担为组件分析，**不是实测 RAM 排名**。不提供未经测量的“闲置只占几十 MB”或“三者必定可流畅运行”结论。磁盘容量充足不能补偿 CPU 和物理内存峰值；swap 也不能当作任务容量扩展承诺。

为保护远程连接，未来首个 Hermes 实例采用原试点的保守上界：CPU 1.5、内存 3 GiB、memory+swap 合计 3 GiB、pids 512、顶层并发 1。这些是**计划中的硬上限，尚未启用，也没有运行充分性的证据**。浏览器如作为子进程应计入同组预算，至多一个会话/两个页面。预算触顶时减少功能或停止试点，先记录实测，不直接提高宿主负载。

保留 available 低于 1.5 GiB 持续 60 秒或根盘低于 40 GiB 时停止自身任务的规划，实际监测实现留待授权部署。安装 Docker 对 bridge/NAT 的影响及 Tailscale/FRP 实际重连仍需验收，不能因只用外部模型省略。

## 9. 最终候选与部署前剩余事项

选择 **Hermes 单实例、外部三路模型、按需开放六项业务 Skills**。首批为 grounded-citations、document-to-action-items、pdf、microsoft-office、meeting-action-items、arxiv。RSS 和 architecture-diagram 满足各自权限及离线渲染条件后再开放；codebase-inspection 延后。原生浏览器放入 B2 的有界会话验收。

nanobot 与 Agent Zero 保留比较资料，当前不启动这两套产品。Hermes 的拒绝处理差异必须解决后再按原验收要求放行。Skills 内容、依赖和执行权限分别审查，仓库星数和集合规模不能充当安全或兼容性证明。

下一步依赖依次为：Hermes 可访问的安全模型入口、三路模型映射与独立额度、拒绝语义、受控依赖环境；未来另获部署指令后，B1 验证三路独立推理、故障切换、工具不重放、文件样例、重启状态及资源保护。本轮只做计划与只读核查，不执行部署或推理，不更改 Codex 主 provider 或 Sub2API。

正式版本、tree、Skills 计数、源码及哈希保存在 [本轮证据目录](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/agent-final-comparison-20261116)。原始树均完整，未截断。三处下载 429 和不在稳定树的猜测路径如实保留，不能用于推断功能缺失。

本轮通过的是调查、版本绑定和选型文档更新。运行基准、完整安全审计、UI 视觉及端到端验收尚未执行。Hermes 主选保持原恢复边界、B0 HOLD、暂不部署及不接 Discord 的限制。
