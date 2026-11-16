# Hermes 主选、首批 Skills 与模型接入计划

2026-11-17 策略更新：[固定版拒绝终态与累计USD10预算候选](HERMES_B0_POLICY_BUDGET_2026-11-17.md) 已准备本地代码与测试。未来所有模型和辅助调用进入同一独立预算入口，Hermes不直接获得上游key。六项Skills范围保持；GPT/Qwen计价上界缺证据，当前模板阻断启动，B0 HOLD，未部署。

日期：2026-11-16，Asia/Tokyo。用户已明确选择以 Skills 生态为优先，继续按 Hermes 推进。本文为当前选型与部署准备依据，替代上一轮 nanobot 首选建议；替代产品比较事实继续保留。状态：计划与只读核查完成，B0 总体 HOLD，禁止进入部署。

2026-11-17 更新：[三项阻塞补查](HERMES_B0_BLOCKERS_2026-11-17.md) 已关闭远端入口阻塞，DeepSeek 官方目录/余额及共享网关账面额度查询通过。用户说明 GPT/Qwen 同在 ccnode 的 HTTPS 服务，当前采用此形态。拒绝终态及试点费用停止机制仍未完成，六项首批 Skills 和资源/权限范围保持不变。第4节保留原入口调查过程，后续以本次补查为准。

## 1. 当前选择和冻结边界

主选 **Hermes**，nanobot 和 Agent Zero 保留为比较材料。丰富的官方流程、可选 Skills 与浏览器/文件能力符合用户偏好；每项依赖、权限及资源仍需核查，扩展数量不代替验收。

本轮查询 [最新稳定发布](https://github.com/NousResearch/hermes-agent/releases/latest)，仍为 v0.23.1，候选 commit `3b421578588243f920886e6fe79a6faa87ea026e`。沿用既有 registry 证据：linux/amd64 manifest `sha256:1a355ebc8981a4b72a28f4e47e347ba4f0f172b43dc876e5768d175a07c67b22`，多架构 index `sha256:276d44685c65c0cb2a25f190b63c65c8906f9dc76486fb1c05ae71b5826bda08`。二者是候选身份，当前尚未部署或运行验收。

本轮无安装、镜像 layer 下载、生成请求、程序修补、网关配置或 Discord 动作。远端只执行同一既有上游的匿名 TCP/路由查询及服务状态读取，源码仅作数据审查。Wi-Fi、SSH、Tailscale、FRP 和 Discord 静态保留资料不变。

## 2. 首批推荐清单

所有下述文件固定到同一稳定 commit，61 个关联源文件已核对 Git blob SHA 与内容 SHA256。九项 frontmatter 均声明 MIT，PDF/Office 的独立 LICENSE 也已读取；第三方库与模型另按各自许可处理。首批六个业务 Skill 按需加载，框架自带 hermes-agent 操作指南继续按 B0 的受限方式处理。

| 阶段 | Skill 与稳定路径 | 用途 | 依赖及权限 | 资源结论和准入条件 |
| --- | --- | --- | --- | --- |
| 首批 1 | `skills/research/grounded-citations` | 引用台账、来源/原文证据、报告核验 | Python 标准库；读取检索结果与工作区草稿，写任务专属 ledger | 无常驻进程或额外模型；每任务显式 `--ledger`，避免重置其他任务台账；不能把机械引用校验当事实正确性证明 |
| 首批 2 | `skills/productivity/document-to-action-items` | 将文档内容转为带定位的义务、期限和待办草案 | 纯流程，调用已准入 PDF/Office/文件工具；原文有外部 tracker 写入阶段 | 额外成本主要为模型上下文；仅本地草案，不启用 tracker、日历或消息工具 |
| 首批 3 | `skills/productivity/pdf` | 文本、表格、元数据提取，后续可扩展生成/合并 | pypdf/reportlab/pdfplumber；渲染涉及 pypdfium2 或 poppler | 预备 documents/documents-pdf 环境；首批不启用 marker、PyMuPDF OCR、nano-pdf；整份提取可能扩大内存，样例先限小文件 |
| 首批 4 | `skills/productivity/microsoft-office` | DOCX/XLSX/PPTX 读取和工作区草稿 | python-docx/openpyxl/python-pptx；输入只读、输出写新文件 | 基础读取/草稿纳入首批；LibreOffice 渲染、公式重算和长文档制作保留 B2；文本回读不代表版式验收 |
| 首批 5 | `skills/productivity/meeting-action-items` | 从已有会议文字整理决定、责任和待办 | 纯流程，读取用户批准的文字稿 | 不装音视频转写、不取 Teams/邮箱、不发布任务或消息；没有独立常驻服务 |
| 首批 6 | `skills/research/arxiv` | 论文元数据检索、摘要与文献线索 | Python 标准库/curl；访问固定 arXiv API，其他文献 API 按批准范围 | 默认每次 5 条、建议最多 10 条；全文 PDF 交给已准入流程；不运行文中未验证的额外 CLI |
| 条件候选 | `optional-skills/research/rss-feeds` | 技术博客/发布订阅的手动汇总 | Python 标准库，访问批准 feed；本轮不启用 cron | 20 秒网络 timeout，但 `--limit` 在整份下载/解析之后生效；源码没有响应字节上限。启用前补明确响应预算和受控网络路径 |
| 条件候选 | `skills/creative/architecture-diagram` | 架构图 HTML/SVG 草稿 | 声明 dependencies=[]，写本地 HTML；部分模板引用 Google Fonts | 不调用图片生成模型；启用前改用已批准本地字体/离线样式，并做真实渲染与截图验收 |
| 暂缓 | `skills/software-development/codebase-inspection` | pygount 代码体量/语言统计 | 需要 pygount；原安装示例含 `pip install --break-system-packages` | 不将此示例带入宿主或受管 Python；仅统计用途不足以成为首批新增包理由。需要时再锁定隔离依赖，排除 .git/node_modules/venv |

来源入口：[官方 Skills 目录](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog)、[grounded-citations](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/research/grounded-citations/SKILL.md)、[document-to-action-items](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/productivity/document-to-action-items/SKILL.md)、[pdf](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/productivity/pdf/SKILL.md)、[microsoft-office](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/productivity/microsoft-office/SKILL.md)、[meeting-action-items](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/productivity/meeting-action-items/SKILL.md)、[arxiv](https://github.com/NousResearch/hermes-agent/blob/v0.23.1/skills/research/arxiv/SKILL.md)。

原计划将 Office 整体留到 B2，本次明确调整为基础读取及草稿进入首批，渲染/重算仍属 B2。这是范围细化，未执行安装。浏览器是工具/运行时能力，另在 B2 加入容器内空白 profile，不当作一个 Skill 已经具备全部网络与页面权限。

### 依赖、许可与脚本审查结果

同版本 uv.lock 中 PDF、Office 及 DDGS 的默认依赖闭包并集为 **20 项**。复用此前有效元数据，并补齐新增 Office 项，记录在 DEPENDENCY_LICENSE_CLOSURE.json。它是版本与许可审查的候选集合，尚未执行平台依赖求解或安装。

| 直接依赖 | 版本 | 发布许可声明 |
| --- | --- | --- |
| pypdf | 6.21.4 | BSD-3-Clause |
| reportlab | 5.1.0 | BSD |
| pdfplumber | 0.11.10 | MIT |
| pypdfium2 | 5.14.0 | BSD-3-Clause、Apache-2.0 及原生依赖 notices |
| python-docx | 1.2.0 | MIT |
| openpyxl | 3.1.5 | MIT |
| python-pptx | 1.0.2 | MIT |
| ddgs | 9.16.0 | MIT |

Office 新增链还包括 et-xmlfile 2.0.0（MIT）、typing-extensions 4.16.0（PSF-2.0）、XlsxWriter 3.3.0（BSD-2-Clause）；其余依赖复用既有锁定结果。pypdfium2 的底层 PDFium notices 不能合并标成 MIT。PyPI 发布声明及其当前漏洞列表不是完整许可证或漏洞审计，未下载 wheel 检查内部所有原生组件。

新选的纯流程/标准库 Skill 无需增加独立 Python 包。RSS 文档称 Python 3.10+，脚本导入 datetime.UTC，实际有 Python 3.11+ 约束；冻结镜像的 Python 3.14 满足，但不能把文案的最低版本原样用于其他部署。arXiv SKILL 文本含旧 `ocr-and-documents` 引用和部分额外 API 示例，首批仅采用经审查的自带元数据脚本，PDF 定向到当前 pdf Skill。

Skill 中提及其他 Skill 不代表准入，正文安装示例不自动获得执行授权。RSS 的 urllib 请求不自动继承 Hermes web 工具的 SSRF 防护；受控 feed、重定向及响应预算必须共同处理。grounded-citations 的实际 ledger 写入及锁文件属于工作区状态，不授予修改管理员策略的权限。

## 3. 权限及资源规划

Skill 文件通常没有独立常驻内存。九项源码文本合计 379,125 bytes，仅反映本轮保留文件大小，不含解释器、库、模型调用、解析输入、浏览器或输出。主要负担来自模型上下文、PDF/Office 解析、OCR/渲染和浏览器进程，不能据源码大小推算 RAM。

沿用 SpringMonkey 当日已验的 7.14 GiB RAM、i5-5200U 及约 304 GiB 可用根盘。首个实例仍计划 CPU 1.5、内存 3 GiB、memory+swap 合计 3 GiB、pids 512、并发 1。它们是待实施上限，未配置或测量生效。available 低于 1.5 GiB 持续 60 秒或根盘低于 40 GiB 时停止自身任务的监测仍待部署验收。

| 类别 | 首批资源约束建议 | 尚待验证 |
| --- | --- | --- |
| 引用/待办/纪要流程 | 按需加载，输入分段，输出限当前任务目录 | token/request 与辅助调用实际费用 |
| PDF/Office | 初始样例不超过 10 MiB、PDF 不超过 20 页，单文件串行 | 这是样例预算，脚本本身未提供统一硬限制；超限拒绝、内存峰值和受损文件行为需测 |
| arXiv/RSS | 小批条目，网络超时和响应体上限分开控制 | 无界响应/重定向不因条目少而自动安全 |
| 浏览器 | B2，一个会话、至多两个页面 | 进程回收、下载、登录态及网络访问边界 |
| Office 渲染/OCR | 首批停用 | 后续启用需独立实测；不以 swap 补偿峰值 |

部署形态继续为官方镜像单外容器。root 初始化后 Agent 降权，严格工作区挂载；不挂载宿主根、docker.sock、SSH key、Tailscale/FRP 状态和 Discord 备份。管理员策略和已审 Skill 受保护，任务运行期不自动安装/更新/自改。只读挂载、s6 初始化及可用 capabilities 的组合必须实测。

toolsets、外部凭据和网络边界共同限制行为：不启用外部 tracker、日历、邮件、消息、宿主管理或委派。允许 terminal 的场景仍具有容器内账号权限，禁止将 Skill 提示词当 OS 安全隔离。公司/私人资料未来需要分隔时另行设计独立实例和目录，本次不导入。

## 4. 模型连通性：2026-11-16 历史采样

本轮在既有客户端指定服务上查询 GET `/models`，只在本机内存使用已有凭据，没有将 key 传入远端。该查询返回 HTTP 200，模型数仍为 41。匹配的现有 socat 容器仍只发布 Windows `127.0.0.1:39452`。

SpringMonkey 对同一已知私有上游只做匿名 TCP 连接，8 秒超时。只读路由查询返回出口 `wlp4s0` 且有网关，未显示该目标走 Tailscale；这说明本次查询使用 Wi-Fi 网关路径，不能据此单独确定路由、ACL、上游监听或网络策略中的哪一项导致超时。SSH、tailscaled、frpc 服务均 active，本轮实际 Tailscale SSH 查询成功。

逻辑链路为：本机 Windows loopback → 既有转发 → 私有上游 → 模型路由。SpringMonkey 当前未验证可访问该上游，Linux 容器内的 127.0.0.1 也不会指向 Windows。现在具备“本机目录可读”证据，缺少“SpringMonkey 可用模型入口”证据，不能通过换 model ID 或安装 Hermes 解决。

推荐的后续接入方向是：由原服务提供主机可达的 HTTPS 入口，或在已批准的加密私网中提供受限访问。需确认服务证书、鉴权、地域/数据范围和额度；不将 Windows loopback 代理作为无人值守主机的永久依赖。不新增公网监听、端口扫描、TailScale/FRP 转发或修改现有 Sub2API，当前不为排障尝试其他未授权入口。

## 5. 三路兜底的具体选择与未决问题

| 路由 | 本机目录观察 | 计划角色与条件 |
| --- | --- | --- |
| ChatGPT/OpenAI 兼容主路 | `gpt-6-astra` 可见 | 公网 `https://ccnode.briconbric.com:49530/v1` 已通过远端目录认证；协议/生成待 B1，账面额度可读、费用停止机制待收口 |
| DeepSeek | 官方直连目录确认 `deepseek-flash` | `https://api.deepseek.com` 既有独立 key 的目录/余额查询通过；不采用旧 Flash 别名，不改变本机 Codex 配置 |
| Qwen | `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S` | 用户确认与 GPT 同一公网网关；共享账面额度可读，上游运行、独立额度和真实生成未知 |

三个名字可见不等于三路可生成。当前链路拟为 GPT 网关 → DeepSeek 官方 → Qwen 网关，具备一路独立服务候选。GPT/Qwen 共享网关故障域，网关账面余额不能证明 Qwen 上游限额；不另开 Qwen 云账号或下载 GGUF。DeepSeek 余额也未为 Hermes 预留，试点费用停止机制保持未完成。

应用层由 Hermes 的原生 fallback_providers 负责有序切换，每路固定 provider/URL/key 引用与协议；GPT/Qwen 共享网关凭据，DeepSeek 引用独立凭据。现有网关客户端投影曾观测为 request-retry=0，不能据此证明上游所有层都零重试；部署前必须确认跨模型重试责任只落在一个负责层。应用配置不改变本机 Codex 全局 provider 或订阅认证。

| 项目 | 处理原则与现况 |
| --- | --- |
| 429/5xx/连接失败 | 有界重试后沿三路切换，实际次数与时延待 B1 故障注入 |
| 401/403/404 | 记录配置/权限/映射故障；备用成功不能掩盖待修项 |
| 小上下文备用 | 按已验证能力限制输入或压缩，不假定跨 provider 私有 continuation 可迁移 |
| 已执行工具 | 保存 tool-call/result，不自动重放有副作用动作 |
| 正常拒绝/content_filter | 既定要求保持终态；当前固定版存在差异，仍是放行阻塞 |
| 压缩/标题/视觉/embedding | 明确模型及预算，首批不启用未验证图像/语音/embedding；文本备用不承接未验证视觉任务 |
| 全链失败/额度耗尽 | 保留检查点并停止，不无限重试 |

拒绝处理的源码证据复用 [固定 v0.23.1 handler](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/agent/turn_truncation.py)。本轮额外查看 main 提交 `c3b90ccc70e353a6771a8c47de6e7777c5b79988`，同一 handler 仍包含备用激活调用。该观察没有完整验证 main 的所有下游门槛，不能据此宣称整个分支绝无修复，也不能将未发布 main 当作已通过候选。当前没有已证实满足该要求的升级闭环。

后续可接受路径是核对官方一致版本，或在用户授权后做最小、可审查的策略修正并验证。保持三路故障兜底与拒绝终态两个要求，不通过关闭全部备用或修改验收口径来宣称完成。本轮没有改 Hermes 源码、写插件或发起实际拒绝请求。

## 6. 同步后的批次与验收

| 批次 | 准备内容 | 放行条件 |
| --- | --- | --- |
| 当前 B0 | Hermes 主选、六项业务 Skill、20 项依赖候选、资源/权限、入口与三路方案 | 已完成文档与只读调查；整体仍 HOLD |
| 后续 B0 收口 | 复用已通过的公网入口及独立 DeepSeek 读证；补齐拒绝处理一致版本、试点费用停止机制、不可变镜像与完整依赖清单 | 静态候选完整，关键行为无已知冲突；实际安装仍需用户发起 |
| B1 最小部署与验证 | 六项首批业务 Skill 按需启用，文件与公开资料样例，逐路真实调用与错误注入 | 实际 route/费用可核对，工具不重放，状态恢复及资源/SSH保护通过 |
| B2 增强 | 单一浏览器、RSS 输入保护、架构图渲染、Office渲染/OCR按需 | 各项独立资源、权限和输出验收；不顺带接消息渠道 |

原 15 分钟/任务、30 次模型请求含重试/辅助、首次总费用建议 USD 10 为规划预算，未配置。供应商硬额度优先，缺少可执行限制时不启动无人值守任务。模板和实现先入 Git，秘密不入库；回滚只影响试点容器/目录/凭据，不清理远程连接与系统恢复资料。

## 7. 当前验收状态

| 项目 | 结果 |
| --- | --- |
| 用户选择与现行文档一致 | Hermes 主选，上一轮 nanobot 排序保留为历史分析 |
| Skill 来源/许可/脚本/资源审查 | 九候选固定源码已核查，六首批、两条件、一暂缓；没有运行批准 |
| 本机模型目录 | PASS，HTTP200/41，三类候选可见 |
| SpringMonkey 模型入口 | 2026-11-17 PASS，用户提供的公网HTTPS目录认证通过；旧私有上游仍超时，未改网络 |
| 三路实际生成/容灾 | 未执行；DeepSeek独立余额及网关账面额度已有证据，Qwen上游映射/能力和试点费用停止机制待验 |
| 拒绝终态 | 当前候选未通过，保留明确阻塞 |
| 整体 B0 | HOLD，禁止进入安装 |

正式证据在 [本轮目录](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/hermes-selection-sync-20261116)：SKILLS_SOURCE_MANIFEST、SKILL_DEPENDENCY_PERMISSION_INDEX、DEPENDENCY_LICENSE_CLOSURE、CONNECTION_REFRESH、MAIN_POLICY_OBSERVATION 及源码快照。本轮只读与文档完成不能当作运行、安全或资源测试通过。
