# Hermes 通用能力扩充与安装回执

当前MoA已配置并真实验收：GPT-6.1 Sol汇总，DeepSeek/Qwen参考，辅助auto。见[配置与验收](HERMES_MOA_ACCEPTANCE_2026-11-17.md)。普通聊天主模型保持gpt-6.1-sol。


当前主模型：按用户后续要求已切换为 **gpt-6.1-sol**，DeepSeek、Qwen备用顺序保持。共享网关精确目录及真实响应同名验证通过；32.294秒真实Hermes任务成功写入并读回文件，原生CLI会话记录及有效配置确认新模型。仅model.default变化，原用户配置、权限及认证不变。本页B3跨域样例是在切换前完成并保留其原始证据，未冒充全部使用新模型重跑。见[模型切换验收](evidence/hermes-model-20261117/MODEL_ACCEPTANCE.json)。


2026-11-17，Asia/Tokyo。用户明确授权将既有调研中适合的成熟Agent工作流和Skills直接合批引入，保持Discord关闭。原六项为最小试点，交付覆盖不足；本次增加64项，共70项，默认启用，提供8个Hermes原生工作流入口。原固定版本、三路模型及拒绝终态补丁不变。

## 当前结果

已实际部署到SpringMonkey，管理页[Skills](https://sm.briconbric.com/skills)显示70/70 enabled，全部70项原生发现与读取、8个bundle解析无缺项。逐项业务语义没有分别执行70次生成；代表性跨域工具及真实Hermes任务通过。原生linter零error，240项advisory主要为上游命名、正文长度、工具写法和结构惯例，未将advisory说成安全证明。

8个入口是`/research`、`/office`、`/analyst`、`/planner`、`/developer`、`/reviewer`、`/web-qa`、`/writer`。用户可直接用自然语言下达任务，由Hermes选择已装Skills；无需逐项安装。入口使用同一Hermes及配置的模型，串行执行角色工作流。未安装其他独立Agent框架，未启用并行委派或额外Claude登录。

## 来源及版本

GitHub API于本次任务实时查询。星数是仓库关注度快照，每个Skill没有独立评分。以官方维护、许可、依赖和本机适用性作安装判断。VoltAgent集合用于发现，不把整个链接目录当可执行Skill。

| 实际内容来源 | Stars快照 | 安装源码commit |
| --- | ---: | --- |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | 264,070 | `3b4215785882` |
| [obra/superpowers](https://github.com/obra/superpowers) | 318,940 | `22f0b463e7a5` |
| [anthropics/skills](https://github.com/anthropics/skills) | 196,400 | `e4bb5d960d87` |
| [trailofbits/skills](https://github.com/trailofbits/skills) | 8,243 | `149d7b21f406` |
| [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | 34,270 | `1a2c79d4e6c4` |
| [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) | 36,360 | `e91a134584eb` |

Hermes使用当前已验固定v0.23.1源码，其他来源使用上表固定commit。逐文件Git blob SHA及SHA256核验，保留SOURCE.json、原许可和适配说明。来源文档按需加载，文本资源包约3.24MB；安装包SHA256为`0263252066c6c17eb5cf8551d3b0eca09cb9e6d0ddf174cd1678a1d1ec161000`。完整文件与路径见[安装清单](evidence/hermes-capabilities-20261117/INSTALL_MANIFEST.json)。

MIT、Apache-2.0和CC-BY-SA-4.0分别保留。Trail of Bits改编内容继续按CC-BY-SA-4.0标示来源与改动；Vercel按各Skill的MIT声明保留provenance，下载的仓库根无独立LICENSE文件。没有把全部第三方统一写成MIT。Python wheel和Debian包各自的license/notices留在镜像安装位置，Python依赖身份见[锁定记录](evidence/hermes-capabilities-20261117/PYTHON_DEPENDENCIES.json)。30个新增包均有许可元数据、分类或notice文件信号，累计87份许可相关文件；12个直接系统包均保留copyright文件，见[安装许可索引](evidence/hermes-capabilities-20261117/LICENSE_INVENTORY.json)。这属于部署许可与依赖审查，未作法律意见或完整供应链安全认证。

## 能力和运行依赖

新增64项如下。原有grounded-citations、arxiv、pdf、microsoft-office、meeting-action-items、document-to-action-items继续保留。

| Skill | 来源 | 许可 | 依赖或可用范围 |
| --- | --- | --- | --- |
| `one-three-one-rule` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `ascii-art` | NousResearch/hermes-agent | MIT | 文本/Pillow；pyfiglet、cowsay等可选示例未安装 |
| `creative-ideation` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `design-md` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `simple-english` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `social-media-content-calendar` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `decision-questionnaire` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `llm-wiki` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `rss-feeds` | NousResearch/hermes-agent | MIT | 标准库，20秒超时/4MiB响应上限 |
| `code-wiki` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `grill-me` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `hermes-agent-skill-authoring` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `python-debugpy` | NousResearch/hermes-agent | MIT | debugpy |
| `rest-graphql-debug` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `architecture-diagram` | NousResearch/hermes-agent | MIT | HTML/SVG，本地字体优先 |
| `humanizer` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `p5js` | NousResearch/hermes-agent | MIT | 浏览器，公开CDN示例按任务使用 |
| `popular-web-designs` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `weekly-review-planning` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `codebase-inspection` | NousResearch/hermes-agent | MIT | pygount |
| `dogfood` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `github` | NousResearch/hermes-agent | MIT | git/curl公共读取，gh未配置私人认证 |
| `requesting-code-review` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `spike` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `systematic-debugging` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `test-driven-development` | NousResearch/hermes-agent | MIT | 纯流程/现有文件与检索工具 |
| `blocked-page-recovery` | NousResearch/hermes-agent | MIT | 标准库；仅已批准公共URL，不传私有URL给归档服务 |
| `brainstorming` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `executing-plans` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `finishing-a-development-branch` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `receiving-code-review` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `using-git-worktrees` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `verification-before-completion` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `writing-plans` | obra/superpowers | MIT | 纯流程/现有文件与检索工具 |
| `frontend-design` | anthropics/skills | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `internal-comms` | anthropics/skills | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `mcp-builder` | anthropics/skills | Apache-2.0 | 设计与代码指南，未注册外部MCP服务 |
| `theme-factory` | anthropics/skills | Apache-2.0 | 附带主题资源 |
| `webapp-testing` | anthropics/skills | Apache-2.0 | Playwright与已装Chromium |
| `audit-context-building` | trailofbits/skills | CC-BY-SA-4.0 | 纯流程/现有文件与检索工具 |
| `differential-review` | trailofbits/skills | CC-BY-SA-4.0 | 纯流程/现有文件与检索工具 |
| `property-based-testing` | trailofbits/skills | CC-BY-SA-4.0 | Python Hypothesis已装；其他语言框架按具体项目依赖 |
| `sharp-edges` | trailofbits/skills | CC-BY-SA-4.0 | 纯流程/现有文件与检索工具 |
| `vercel-composition-patterns` | vercel-labs/agent-skills | MIT | 纯流程/现有文件与检索工具 |
| `vercel-react-best-practices` | vercel-labs/agent-skills | MIT | 纯流程/现有文件与检索工具 |
| `web-design-guidelines` | vercel-labs/agent-skills | MIT | 纯流程/现有文件与检索工具 |
| `analyze` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `build-dashboard` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `create-viz` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `data-visualization` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `explore-data` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `sql-queries` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `statistical-analysis` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `validate-data` | anthropics/knowledge-work-plugins | Apache-2.0 | pandas/NumPy/SciPy/matplotlib/seaborn/Plotly；本地数据 |
| `write-query` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `competitive-brief` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `metrics-review` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `product-brainstorming` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `roadmap-update` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `sprint-planning` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `stakeholder-update` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `synthesize-research` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `write-spec` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |
| `task-management` | anthropics/knowledge-work-plugins | Apache-2.0 | 纯流程/现有文件与检索工具 |

Office/PDF补齐LibreOffice Writer/Calc/Impress、Poppler、Tesseract英文/日文/简体中文、Pandoc、Graphviz及CJK字体；开发工具补齐gh、jq。13个直接Python包解析为30个新增包，锁定版本和wheel SHA256，binary-only/no-deps按锁安装。扩展解释器`/opt/skills-python/bin/python`通过.pth复用原文档库；原`/opt/hermes/.venv`及拒绝补丁未改。镜像`springmonkey/hermes-pilot:v0.23.1-r2`，本机image ID `sha256:598f0583092e6d0f3441d33c3951af83da01e2ceb2b79f11d4000b0ef0c01723`，Docker记录大小6,905,256,026 bytes。

Skills没有逐项常驻进程；上下文按需加载。CLI仍1.5CPU/3GiB/512pids，Dashboard仍1CPU/1GiB/256pids。实际工具样例在CLI同等限额内完成，峰值内存没有采样，不用空闲值推算。OCR和Office转换串行；大文件/长时任务没有全面容量测试。GUI Chat和独立多Agent并发不在本批运行验收内。

## 适配和权限

适配层将Read/Write/Edit/Bash等工具映射到Hermes原生工具，缺少独立子Agent时由当前Agent串行完成并说明局限。去掉会打印凭据的GitHub helper和Claude专用MCP评估runner，保留设计指南；RSS新增4MiB响应上限。正常任务不能安装依赖或修改已装Skills。代码与脚本按数据审查，不执行上游安装示例。

允许公开技术资料研究、用户批准的本地文件、工作区代码与输出。Skills和bundle只读挂载，未挂载宿主根、Docker socket、SSH/FRP/Tailscale或Discord恢复材料。私有账号、邮件/日历/外部tracker、发布、生产部署与远程写入仍需对应用户任务；本批没有配置账号或连接这些服务。没有GPU、本地大模型、付费音视频/图片服务或定时任务。需要这类独立资源的候选保留为未接入，未冒充已具备。

原root-owned1770共享home与固定版原生控制通道要求运行UID拥有home的契约冲突，真实CLI启动失败。本次使用原生私有home和managed scope修正，保留安全检查源码：CLI `/srv/hermes-pilot/cli-home` UID10000/0700；管理页 `/srv/hermes-pilot/data` UID10001/0700。旧会话资料保留在管理home，CLI新状态独立，工作区共享。

唯一管理员配置为`/srv/hermes-pilot/policy/config.yaml`，UID10001/GID10000/0640。两个home的config.yaml为同一文件的相对symlink；管理页RW目录挂载支持原生保留symlink的原子保存，CLI只读挂载policy并使用官方`HERMES_MANAGED_DIR=/opt/policy`，管理员已配置叶子覆盖本地shadow。未引入同步脚本、旧文件fallback或削弱原生控制通道验证。用户当前配置原字节SHA38c5f6...在迁移中保持，未恢复旧默认值。

原生managed scope对缺失/无效受管配置会fail-open，CLI仍具备容器内执行能力并持有自身模型凭据；本实例定位可信单用户，不能把这些机制说成多租户或完整恶意代码隔离。

## 验收证据

| 必需项 | 实际结果 |
| --- | --- |
| 70技能发现、读取、8bundle引用 | PASS，无缺项 |
| 数据与图表 | PASS，合成CSV总和45、均值15、线性斜率5；PNG及交互HTML |
| Office与PDF | PASS，DOCX/PPTX转PDF，文本回读及页数，XLSX公式重算45，Poppler真实渲染 |
| OCR | PASS，英文7419标记识别；jpn/chi_sim语言包存在，未测其准确率 |
| 开发与网页QA | PASS，2项合成pytest、pygount统计；真实Chromium点击，测试页Console与请求失败0 |
| RSS | PASS，PyPI真实发布feed、正常解析及4MiB超限负例 |
| Hermes真实跨域任务 | PASS，154.872秒、16工具调用，实际读取4 Skills，执行pandas/Decimal核对，写出并read_file读回JSON及中文PRD草案 |
| 执行审批 | PASS，-c和execute_code两次受限调用被拒绝，原任务使用允许的脚本继续成功；未放宽审批 |
| 运行目录、配置边界 | PASS，私有home UID10000，配置写拒绝、管理员canary删除拒绝、managed shadow覆盖通过 |
| 管理页保存 | PASS，实际Nous已登录页面Save，symlink/UID/0640保留，前后语义SHA相同 |
| 原生浏览器新home | PASS，官方Playwright页面真实导航、正文定位及截图 |
| 主机及公网认证 | PASS，Wi-Fi连接、SSH/Tailscale/FRP active，匿名config401，Nous gate有效，原端口与限额保留 |

真实Hermes的中文文档为未来CSV转Excel功能的需求草案，没有把该功能写成已实现。主要证据：[运行样例](evidence/hermes-capabilities-20261117/CAPABILITY_RUNTIME.json)、[最终CLI与权限](evidence/hermes-capabilities-20261117/FINAL_RUNTIME.json)、[部署状态](evidence/hermes-capabilities-20261117/POST_DEPLOYMENT.json)、[JSON输出](evidence/hermes-capabilities-20261117/hermes-result.json)、[中文输出](evidence/hermes-capabilities-20261117/hermes-brief.md)、[实际技能页](evidence/hermes-capabilities-20261117/skills-installed.jpg)。

官方UI源码未改，原手机390px的9px控件溢出保持已知限制。本批不重复旧桌面/手机视觉回归，不将本批工具PASS说成手机视觉PASS。管理页技能列表已实看，显示70/70，截图未含账号标识。

## 安装与回滚记录

授权依据为本次用户“把能引入的直接引入”。运行路径为SpringMonkey的approved-skills、data/skill-bundles、cli-home、policy和两个自有容器；安装输入及许可证随[固定安装包](evidence/hermes-capabilities-20261117/skills-package.tar.gz)保留。系统及Python扩展只在容器镜像中，宿主未装这些应用，未在Windows下载FRP。

原六项目录保留在`/srv/hermes-pilot/approved-skills.b3-rollback`，原r1镜像保留，部署前管理配置备份位于`/etc/hermes-pilot/b3-backup`。回滚需停止自有CLI/Dashboard，切回原Skills目录和r1 image ID后使用当前私有home启动脚本重建两容器；私有home和policy布局保留，以免恢复已证实不能通过原生控制通道的旧共享home。只撤销本批bundle和CAPABILITIES文档；保留用户配置、历史、工作区、证书和所有远程入口，不执行全局prune。

停止的历史容器仅供记录，带有旧挂载，不能直接start当作当前布局回滚。重建请参照[脚本说明](../../scripts/hermes-pilot/README.md)及当前主机实际挂载。运行时故障回滚未人为演练，不把保留回滚输入写成已验回滚成功。

未接入清单：其他独立Agent框架、动态大规模fan-out、GPU训练/推理、重型Jupyter kernel、平台专用Apple工具、私有服务账号及真实外部写入；部分上游可选示例仍需其各自资源。本批已装的通用工作流无需用户逐项补装。
