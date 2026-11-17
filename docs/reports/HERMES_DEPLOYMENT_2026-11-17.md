# SpringMonkey Hermes 首批部署

[后续批次](HERMES_RESEARCH_AND_DASHBOARD_2026-11-17.md)：网页研究、HTTPS、Nous登录及桌面配置保存已验收；管理页已上线https://sm.briconbric.com/config。390px手机视口控件溢出9px，响应式验收未通过。原无browser/dashboard及只读单文件bind为首批历史。

2026-11-17，Asia/Tokyo。用户已授权部署Hermes，并允许从已登录Edge取得指定Sub2API账号的Key。此前暂不部署的限制已更新。Discord未接入，费用预留与USD10预算代理已取消。

## 部署结果

主机 `ubuntu-2625`，Ubuntu26.10，i5-5200U，约7.14GiB内存。官方Docker CE29.10.0。Hermes固定v0.23.1，commit `3b421578588243f920886e6fe79a6faa87ea026e`。

基础镜像 `nousresearch/hermes-agent@sha256:1a355ebc8981a4b72a28f4e47e347ba4f0f172b43dc876e5768d175a07c67b22`。

运行镜像 `springmonkey/hermes-pilot:v0.23.1-r1`，实际ID `sha256:9fb9594e7cb3ce4332230104ec8a1fd6996448e227d9ffa0f17ee6f2234735fa`，约4.78GB。启动器使用实际image ID。包含两文件拒绝终态补丁、六项已审Skills及同版本uv.lock中的20项PDF/Office/DDGS依赖，构建时核对版本与源码摘要。许可证沿用[首批审查](HERMES_FIRST_BATCH_SKILLS_2026-11-16.md)，原生组件notices的审查边界保留。

容器 `hermes-pilot` 直接以UID/GID10000运行，CPU1.5、内存3GiB、memory+swap合计3GiB、pids512，no-new-privileges、实际CapEff0，restart unless-stopped。不启动s6、消息gateway、dashboard，不映射宿主端口。

持久目录 `/srv/hermes-pilot/data`、`/srv/hermes-pilot/workspace`。管理员配置 `/etc/hermes-pilot/config.json`、AGENTS.md和六项Skills只读挂载。文件工具写入根为 `/workspace:/opt/data`。宿主根、Docker socket、SSH、Wi-Fi、Tailscale、FRP恢复资料与Discord备份均未挂载。

## 模型与首批Skills

| 顺序 | 模型 | 入口及证据 |
| --- | --- | --- |
| 主模型 | gpt-6-astra | 用户指定HTTPS `/v1` 节点，真实Hermes会议文件读写与读回成功 |
| 第一备用 | deepseek-flash | https://api.deepseek.com，容器真实生成HTTP200及标记匹配 |
| 第二备用 | hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S | 与GPT共用节点，容器真实生成HTTP200及标记匹配 |

GPT/Qwen共用网关，具有共同故障域；DeepSeek为独立入口。未承诺三家独立额度，未继续调查定价或设置费用预留。用户指定Key已安全取得，剪贴板已清空，本机恢复副本DPAPI加密，远端凭据文件root-only0600，未进入Git。

启用grounded-citations、document-to-action-items、pdf、microsoft-office、meeting-action-items、arxiv，共56份Skill文件。首批覆盖引用、批准文字稿的待办、PDF文本、Office基础读取/草稿及arXiv元数据。浏览器、OCR、音视频转写、Office渲染/重算、额外插件、委派和定时任务保留后续范围。

`api_max_retries=2` 为两个备用切换提供内置重启额度。`max_concurrent_sessions=2` 供CLI前端与内部执行端共用，宿主flock保持实际用户入口并发1。入口最多900秒，任务最多30轮。可用性故障按原生机制切换；内容及供应商策略拒绝保持终态。

## 验收

脱敏证据：[evidence/hermes-deployment-20261117](evidence/hermes-deployment-20261117)。完整构建上下文和历史诊断保留在本机任务目录的正式evidence中。

| 项目 | 实际结果 |
| --- | --- |
| 运行权限及资源限制 | PASS，UID10000、CapEff0、只读配置/Skills、无端口和敏感宿主挂载 |
| GPT会议任务 | PASS，退出0，文件标记、Alex/Sam及两日期匹配，真实读回 |
| 两备用真实生成 | PASS，各自HTTP200及标记匹配 |
| 三路故障切换 | PASS，完整安装AIAgent对模拟503接口实际依次请求三路，第三路返回标记 |
| 拒绝终态 | PASS，模拟SSE content_filter只请求主路一次，未请求备用；既有12项源码回归及补丁应用结果复用 |
| PDF及Office | PASS，PDF Skill提取，DOCX/XLSX/PPTX生成后基础读回；未验证视觉版式和公式重算 |
| 容器重启 | PASS，会议文件SHA256保持，最终配置可加载，重启后真实CLI读文件并返回标记，单任务锁及备用Key解析通过；没有重启整台主机 |
| 主机回连 | PASS，Wi-Fi connected、SSH/Tailscale/FRP active，Tailscale实际执行、FRP独立SSH及主机指纹匹配 |

真实接口分别测试，未人为制造生产网关故障，故障切换控制流使用本地模拟服务。web/DDGS和arXiv公网检索未作本批端到端验收。启动仍有可选pnpm版本未就绪提示，相关浏览器能力未启用。长任务、大文档、受损文档资源峰值和宿主低资源自动停止尚未验证或实现。

容器模型客户端需要读取密钥，同容器终端进程也有环境可见性。本实例适用可信单用户及经批准输入；AGENTS和web工具防护不构成宿主网络出口隔离，任意终端代码仍可能访问网络，不适用于恶意代码或多租户执行。

## 使用及回滚

在SpringMonkey管理员SSH会话内运行 `sudo hermes-pilot chat`。工作目录 `/srv/hermes-pilot/workspace` 在Hermes内对应 `/workspace`。普通用户未加入Docker组；无Discord和公开网页入口。

停止 `sudo docker stop hermes-pilot`，恢复 `sudo docker start hermes-pilot`，均保留数据及远程网络服务。撤销时先核对自有容器标签，仅停止/删除该容器，保留工作区和密钥待管理员决定，不执行全局prune或卸载远程服务。

非秘密实现见 [scripts/hermes-pilot](../../scripts/hermes-pilot/README.md)。启动器拒绝覆盖既有容器，重建须核对目标、镜像和持久目录。

重启后小型真实任务35.1秒，Docker采样内存最高373.3MiB，CPU采样最高149.36%，进程数最高41。这些为本次小任务样本，不能推导长任务或大文档峰值。
