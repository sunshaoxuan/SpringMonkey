# SpringMonkey 主机只读核验与 Hermes Agent 试点方案

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
