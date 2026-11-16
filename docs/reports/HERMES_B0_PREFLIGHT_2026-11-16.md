# Hermes B0 前置核查记录

日期：2026-11-16，Asia/Tokyo。关联：[试点主计划](HERMES_PILOT_READONLY_2026-11-16.md)。范围：只读核查、本地公开源码审查、文档与候选冻结。实际部署未执行，Discord 未接入。

## 结论与放行状态

本轮前置调查完成，B0 状态为 **HOLD**。Docker 安装条件和镜像候选已有证据，首批 Skills 的源码、依赖、许可证声明和权限需求已核查。当前接口存在主机可达性阻塞，三模型生成、额度和协议能力仍未验证。

已有网关仅绑定 Windows loopback，SpringMonkey 直达其私有上游端口的只读 TCP 探针超时。尚无已验证、可直接填入远端 Hermes 的安全兼容接口地址。调整监听、配置新代理或改变路由均属于后续部署变更，本轮没有执行。

## 1. 本机兼容接口与模型目录

本次最小范围读取 `.codex/config.toml`、现有 Sub2API runner 及其已指定的凭据投影。认证秘密只在内存中用于该既有服务的 GET 请求，未复制到报告、Git、远端或新的凭据文件。未读取 Codex OAuth 令牌、Discord token 或无关账户资料。

| 检查 | 结果 |
| --- | --- |
| Codex 全局 provider | 仍为 openai，未修改主模型与认证 |
| 已有兼容入口 | `http://127.0.0.1:39452/v1`，只对本机 loopback 发布 |
| 本机 GET `/models` | HTTP 200，41 个精确 model ID |
| 网关拓扑 | 已运行的 socat 容器转发到既有私有上游；只读 inspect，未启停或改配置 |
| SpringMonkey 至上游 | HTTP 探针返回 URLError；补充 TCP 分类为 TimeoutError，8 秒连接超时 |
| 推理请求 | 0；目录访问不证明模型生成、额度、工具或协议可用 |

本机 Codex 还声明了一个未被全局选中的 DeepSeek provider，配置为 Responses wire，未提供可据此确认的独立服务凭据。本轮没有借用 Codex OAuth 认证去试探该服务。

已列入候选的精确 ID：

| 角色 | 目录可见 ID | 当前判断 |
| --- | --- | --- |
| 主模型 | `gpt-6-astra` | 目录可见；部署时验证兼容服务的协议和实际返回模型 |
| DeepSeek 备用 | `deepseek-flash` | 正式名称可见，旧别名不纳入候选 |
| Qwen 备用 | `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S` | 仅发现此 Qwen ID；上游服务、资源和可用额度待实测，不能假定重装前后仍可生成 |

同一目录还列有 GPT、Claude、Gemini 等其他路由，本试点不自动启用。Qwen GGUF 名称不能证明模型在 SpringMonkey 本地运行，本轮也不会安装 Ollama 或下载权重。独立 DeepSeek/Qwen 云服务凭据和硬额度在本次所查配置中尚未确立。

读取到的现有网关客户端策略为 `request-retry=0`、`max-retry-credentials=0`、`max-retry-interval=3`、`routing.strategy=round-robin`。这是客户端投影观察，实际上游策略仍待服务侧确认。规划由 Hermes 负责跨模型顺序兜底，不改现有网关策略。

接口后续必须满足：SpringMonkey 可达的 HTTPS 或已批准加密私网入口，精确模型映射、协议和凭据作用域明确，至少一路独立故障域备用，费用可控。不得直接把 Windows 的 `127.0.0.1` 地址写入 Linux 容器。主路由若用 Responses，其备用可采用各自已验证的 Chat Completions 客户端，正式配置按冻结版 provider 解析器生成；本轮未发起 POST 来验证这些协议。

## 2. Docker 安装条件

[Docker 官方 Ubuntu 安装文档](https://docs.docker.com/engine/install/ubuntu/) 当前明确包含 Ubuntu Stonking 26.10。SpringMonkey 只读核查结果：

| 条件 | 结果 |
| --- | --- |
| 系统 / 架构 | Ubuntu 26.10，stonking，x86_64 / amd64 |
| 根文件系统 | ext4，约 304 GiB 可用 |
| cgroup | v2，cpu、memory、pids、io 等 controllers 存在 |
| 防火墙工具 | iptables v1.8.11，nf_tables 后端 |
| 基础工具 | curl、gpg、systemctl、iptables 均存在 |
| Docker 与运行时 | 当前未安装；指定 docker.io/docker-ce/docker-ce-cli/containerd/containerd.io/runc/podman-docker 查询未发现已装项 |
| 包管理状态 | `dpkg --audit` 无输出，未要求重启 |
| Docker 软件源 | 当前未配置；远端可读取官方 stonking/amd64 索引 |
| 连通服务 | ssh、tailscaled、frpc 均 active，本轮 SSH 成功 |

已验证官方 InRelease 签名及 Packages.gz 的 SHA256，并将候选包摘要逐条与该签名索引匹配。公钥从 Docker 官方 HTTPS 地址读取，签名指纹为 `D3306A018370199E527AE7997EA0A9C3F273FCD8`。验签使用匿名内存文件及已有 gpgv，没有向远端安装 key、写软件源、刷新 apt 或安装软件。

| 官方 stable 候选包 | 精确版本 |
| --- | --- |
| docker-ce | `5:29.9.3-1~ubuntu.26.10~stonking` |
| docker-ce-cli | `5:29.9.3-1~ubuntu.26.10~stonking` |
| containerd.io | `2.4.2-4~ubuntu.26.10~stonking` |
| docker-buildx-plugin | `0.39.0-1~ubuntu.26.10~stonking` |
| docker-compose-plugin | `5.7.1-1~ubuntu.26.10~stonking` |

以上为采样候选，B1 安装前核对版本及 apt 依赖求解结果。首批 CLI 使用预构建镜像，buildx/compose 不构成任务运行必要条件，可按安装管理方式选择。当前没有执行安装模拟或运行时验证。

Docker 安装会创建 bridge/NAT 和防火墙规则，即使不发布应用端口也会改变系统网络状态。B1 应先保存相关基线，安装后分别验证 Tailscale 与 FRP 的实际 SSH；Wi-Fi、Tailscale、FRP 的原配置保持原样。容器不发布宿主端口，避免将 Docker 端口发布误当成受 UFW 入站规则保护。

## 3. 官方镜像候选冻结

GitHub 稳定 tag 已解析到实际 commit：

`v0.23.1` → `3b421578588243f920886e6fe79a6faa87ea026e`。

Registry 实查结果：`nousresearch/hermes-agent:v0.23.1`、`:stable`、`:latest` 在本次采样指向相同 index。`:0.23.1` 返回 404，原计划中的无 v 标签示意已纠正。正式部署使用固定 digest，不跟踪浮动标签。

| 项目 | 冻结值 |
| --- | --- |
| 多架构 index | `sha256:276d44685c65c0cb2a25f190b63c65c8906f9dc76486fb1c05ae71b5826bda08` |
| linux/amd64 manifest | `sha256:1a355ebc8981a4b72a28f4e47e347ba4f0f172b43dc876e5768d175a07c67b22` |
| config digest | `sha256:ed43b1c44a722eff23041b7db2f3866ac80edc33650104a684837830d3798cd3` |
| 镜像创建时间 | 2026-11-10T00:30:08Z |
| 压缩 layer 大小 | 1,120,826,950 bytes，约 1.04 GiB，39 层 |
| config User | root |
| Entrypoint | `/opt/hermes/docker/entrypoint-dispatch.sh` |

只读取 index、manifest 和小型 config blob，并计算摘要核对；未下载 layer，未在本机或远端拉取、创建或启动 Hermes 镜像。解压占用、二进制版本及镜像内部 install stamp 留待 B1 检查。镜像没有提供可直接据此核对的 OCI revision label，本轮没有验证构建签名或可复现构建。

镜像命名空间来自 [官方 Docker 指南](https://hermes-agent.nousresearch.com/docs/user-guide/docker)。启动行为按固定源码 [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/Dockerfile)、[entrypoint dispatcher](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/docker/entrypoint-dispatch.sh)、[stage2 hook](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/docker/stage2-hook.sh)、[main wrapper](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/docker/main-wrapper.sh) 审查：

* 初始 root 用于 s6、UID/GID、目录归属与状态初始化，随后通过 s6-setuidgid 以 hermes 用户运行 Agent。默认 hermes UID 为 10000，可用 HERMES_UID/GID 调整。
* 不能直接套用任意 `--user` 或预先宣称 `cap-drop=ALL` 能启动。B1 保留官方初始化契约，选择最小能力集后实际验证 Agent UID 和权限；no-new-privileges 也需与 s6 路径共同验收。
* 官方 compose 示例包含 host network 和 dashboard，本试点不直接使用该示例。生成单容器、bridge network、无端口发布、无 docker.sock 的配置。
* 根文件系统完全只读、状态内子目录只读挂载和初始化 chown 的兼容性未实测，不能提前宣称硬化通过。用户运行态仍要求非 root，策略受管理员维护。

## 4. 首批 Skills 审查

所有下述 Hermes 文件固定到同一 commit。仓库 [LICENSE](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/LICENSE) 为 MIT，三个生产力 Skill 的 frontmatter 也声明 MIT。需要保留版权及许可，依赖另按各自许可证处理。

| 项目 | 依赖及权限观察 | 首批决定 |
| --- | --- | --- |
| 内置 hermes-agent 指南 | MIT；包含配置、安装和委派指引，没有自动执行本体；框架将其视为 essential | 作为框架操作指南审查，禁止据此扩大安装/委派权限 |
| document-to-action-items | MIT；纯流程，使用 read_file/web_extract，提取依赖 PDF/Office；原文还包含创建外部 tracker 记录 | 允许本地引用与待办草案，外部 tracker 工具不启用，无渠道凭据 |
| pdf | MIT；Python 脚本依赖 pypdf/reportlab/pdfplumber，渲染涉及 pypdfium2 或 poppler；有按路径写文件的功能 | 首批仅文本/表格/元数据提取，输入输出限 workspace；不加载 OCR/nano-pdf 子流程 |
| microsoft-office | MIT；python-docx/openpyxl/python-pptx，渲染/重算还会启动 LibreOffice、poppler | 已审查依赖和边界，仍安排 B2；首批不需要整套渲染环境 |
| DDGS 搜索 provider | 官方源码在 MIT 仓库，插件声明 ddgs extra；无 API key，启动独立搜索子进程并设超时回收 | 作为无额外付费搜索 key 的候选；实际搜索可靠性及页面提取另在 B1 验收 |

原始来源：[PDF Skill](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/skills/productivity/pdf/SKILL.md)、[待办 Skill](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/skills/productivity/document-to-action-items/SKILL.md)、[Office Skill](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/skills/productivity/microsoft-office/SKILL.md)。读取关联目录全部 blob，39 个 Python 文件进行了 AST 解析和风险定位索引，重点逐行审查 pdf_read.py 及安装、OCR、渲染、外部写入相关路径。AST 成功仅证明语法可解析，未执行这些脚本，不能据此宣称安全扫描或行为测试通过。

### 依赖与许可证声明

按固定 [pyproject.toml](https://github.com/NousResearch/hermes-agent/blob/3b421578588243f920886e6fe79a6faa87ea026e/pyproject.toml) 与 uv.lock 对照，并查询对应发布版本的 PyPI 元数据：

| 直接依赖 | 固定版本 | 发布许可声明 |
| --- | --- | --- |
| pypdf | 6.21.4 | BSD-3-Clause |
| reportlab | 5.1.0 | BSD |
| pdfplumber | 0.11.10 | MIT |
| pypdfium2 | 5.14.0 | BSD-3-Clause、Apache-2.0 及原生依赖许可证 |
| ddgs | 9.16.0 | MIT |
| python-docx，B2 | 1.2.0 | MIT |
| openpyxl，B2 | 3.1.5 | MIT |
| python-pptx，B2 | 1.0.2 | MIT |

首批 PDF 与 DDGS 的 uv.lock 默认依赖闭包共 14 项，包含 cffi、charset-normalizer、click、cryptography、lxml、pdfminer-six、Pillow、primp、pycparser。发布声明分别为 MIT-0、MIT、BSD-3-Clause、Apache-2.0 OR BSD-3-Clause、BSD-3-Clause、MIT、MIT-CMU、MIT、BSD-3-Clause。pypdfium2 的底层 PDFium 及其第三方 notices 应随安装产物保留，不能统一标成 MIT。[pypdfium2 发布说明](https://pypi.org/project/pypdfium2/5.14.0/)

这是版本绑定的许可声明审查，范围不覆盖镜像所有软件或原生库全量审计。PyPI 当前这 14 项的漏洞列表为空，只作为该源的采样结果，不等于漏洞扫描或无漏洞保证。候选安装使用冻结锁及包摘要，B1 核对实际安装列表与 notices。

### 需要修正的依赖与权限假设

1. PDF SKILL.md 的前置说明称镜像提供提取库，但同提交 pyproject 明确将 `documents-pdf` 单列且不烘入镜像。Dockerfile 只选择 `documents`，因此 pdfplumber/pypdfium2 不能视为镜像必备。B1 由操作员预备锁定的 documents/documents-pdf 侧环境并验证 imports，运行中不允许 Agent 自行联网安装。
2. PDF 的文本脚本本体没有网络请求，`--tables --csv-dir` 会按给定路径创建目录并写 CSV。Skill 没有独立的 OS 权限清单，路径约束要由挂载、账号与工具边界实现；关闭某个 Skill 不会阻止 terminal 执行同类命令。
3. OCR 参考指向 PyMuPDF、marker、模型下载和额外推理；nano-pdf 也需要外部 LLM key。它们不在首批已选依赖闭包内，本轮不安装、不启用，后续需单独审查其软件与模型许可证及资源。
4. DDGS 是 optional extra，未被 Dockerfile 的直接 extras 或 all 选择，不能假定预装。它向公共搜索服务发送查询，仍需批准查询内容和实际网络验证；本轮未使用或复制其他项目搜索 key。
5. `skills.disabled` 影响常规发现；源码中的 skill_view 可解析已有文件，essential Skill 也不受普通禁用列表限制。因此禁用列表不能当作能力隔离。
6. 固定源码确认 `.no-bundled-skills` marker 可阻止后续整库播种。B1 在启动前预置空白 profile/marker，再放入审查过的子集并核对实际枚举。marker 和 Skill 目录需保护；外部 toolset、MCP、渠道、委派、自动安装均保持关闭。只读挂载与 stage2 同步的兼容性留作运行验收。

首批权限草案：读取批准文件及公开页面，在 workspace 写报告与提取产物；无宿主管理凭据，无 tracker/Discord/邮件 token，无宿主文件系统或 Docker socket。允许工具能够访问推理凭据的残余风险仍存在，需以独立低额度凭据和最小上下文控制。首批能力不是仅靠提示词即可保证的安全边界。

## 5. B0 验收与下一步

| 验收项 | 状态 | 意义 |
| --- | --- | --- |
| 已有配置和本机模型目录 | PASS，目录层面 | 41 ID，含三类候选；推理未测 |
| SpringMonkey 可用兼容入口 | 未通过 | 已有私有上游 TCP 超时，Windows loopback 无法直接复用 |
| Docker OS、软件源和包身份 | PASS，只读前检 | 官方支持，签名索引及候选摘要核对；未安装 |
| 镜像 tag、平台和 digest | PASS，元数据层面 | v0.23.1 固定 index/amd64；未拉层、未运行 |
| 首批 Skill 源码及许可、依赖边界 | PASS，条件准入 | 已选子集与排除路径明确；运行环境和权限必须在 B1 兑现 |
| 独立备用、硬额度及三路协议 | 未完成 | 目录不能证明配额与推理可用 |
| B0 总体放行 | HOLD | 入口和预算条件补齐后再更新，当前禁止进入安装 |

当前应先落实一个 SpringMonkey 可访问的安全接口入口，并明确 DeepSeek/Qwen 备用来源与额度。这涉及网关或新接口配置，保留为用户后续授权的有界变更。不得为使 B0 通过而擅自公开现有端口、修改 Sub2API、安装 FRP/Tailscale 新转发或接入 Discord。

正式机器可读候选及原始证据位于 [B0_CANDIDATE_MANIFEST](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/hermes-b0-20261116/B0_CANDIDATE_MANIFEST.json)。同目录保留接口脱敏结果、拓扑、两次不同诊断层次的连通证据、Docker 签名与包摘要、镜像元数据、源码树/哈希、直接及传递依赖许可元数据。源码读取失败的猜测路径已在 manifest 如实记录，采用 tree 中的实际路径补齐所需入口文件，未把 404 当作功能缺失。

本批仅新增本明细、更新主计划和任务记录，未修改用户 Codex/Sub2API 配置，未部署、安装、发起生成或发送 Discord 消息。
