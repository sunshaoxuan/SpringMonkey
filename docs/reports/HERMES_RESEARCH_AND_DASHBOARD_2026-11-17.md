# Hermes 网页研究与管理页

当前扩充见[70 Skills与8工作流安装回执](HERMES_CAPABILITY_EXPANSION_2026-11-17.md)。私有运行home与单一policy配置替代本页旧共享home，当前源码和配置以新回执为准。


2026-11-17，Asia/Tokyo。用户授权补齐网页研究能力，并新增公网管理页，域名sm.briconbric.com、Nous登录，已自行注册名称SpringMonkey的客户端。Discord及预算代理保持未接入。

## 状态

网页研究验收PASS。用户已授权并完成DNS和Nous回调保存，官方管理页已在[公网配置页](https://sm.briconbric.com/config)运行。HTTPS、Nous登录、原生配置保存、桌面功能/控制台/网络检查PASS；证书自动续期已配置并验证。390像素手机视口存在官方UI控件向右溢出约9px，响应式项FAIL，整体视觉验收保留未通过项；本批未修改官方前端。

## 已完成研究能力

复用固定v0.23.1镜像、拒绝补丁和三模型路线；无需重新构建或下载浏览器。实际browser-harness0.1.13及镜像Chromium可用。启用browser工具集，local/headless、空白profile、use_real_profile=false、空闲60秒回收；批准范围为一会话、最多两页，不接入个人浏览器资料。

DDGS首查出现DNS Query Refused，原生keyless rescue由Exa返回真实结果。当前明确使用Exa作为search/extract后端，已真实验证，没有新增搜索Key或搜索订阅。免费上游的容量和可用性不构成长效SLA。

arXiv沿用已审官方Skill脚本。真实查询带cs.AI分类和max3，选取ReAct原论文2210.03629v3，保留首次提交2022-10-06和更新2023-03-10的区别。

## 真实资料输出

- [中文报告](evidence/hermes-research-dashboard-20261117/report.md)
- [四条一手来源](evidence/hermes-research-dashboard-20261117/sources.json)
- [实际网页截图](evidence/hermes-research-dashboard-20261117/browser.png)

研究主题：低配自托管网页研究Agent的浏览器隔离与可靠性。真实Hermes CLI退出0、154.5秒，34项工具事件包含web_search、browser_exec、terminal运行arXiv脚本、web_extract、write_file及read_file，执行记录观察到论文ID、分类参数及来源域名。输出报告3700字节、来源1161字节、PNG33164字节；下载后SHA256与远端一致。截图780×437，主Agent已实际查看。

配置布局迁移及截图脚本print路径修改后，仅复测其直接消费者浏览器cache/profile和截图，真实导航及截图再次PASS。其余有效检索、研究文件及旧模型/拒绝回归证据复用。

## 官方管理页及权限

独立hermes-dashboard容器使用镜像预构建web_dist，UID10001/GID10000、cap-dropALL、no-new-privileges、CPU1、内存及memory+swap合计1GiB、pids256、unless-stopped，宿主仅127.0.0.1:9119。Agent仍为UID10000、CPU1.5、3GiB、pids512，无宿主端口。

唯一现行配置为/srv/hermes-pilot/data/config.yaml：管理员UID10001拥有0640，GID10000可读；home根为root所有、GID10000、1770 sticky。旧/etc/hermes-pilot/config.json仅留root-only批次备份，运行不再读取。真实UI原子保存请求/api/config返回200，保存前后语义SHA256一致，仅文件序列化格式改变；UID10001/0640及模型、备用路由、审批和安全策略保持一致。实际CLI Agent UID10000不可写配置，对管理员owned文件删除被拒绝。没有配置同步桥或双读。该边界验证仅覆盖CLI身份；管理页及其可能启动的工作进程使用管理员UID10001，GUI Chat未作本批验收。

AGENTS和Skills仍只读，没有宿主根、Docker socket及SSH/Tailscale/FRP/Discord恢复材料挂载。凭据仅保存在root-only远端env及本机DPAPI恢复副本，剪贴板已清空，不进入Git。Nous个人账号实际注册成功，页面显示Only you，表单无付款项目；未订阅Nous推理或托管服务。

公网/login=200，/api/status返回auth_required=true及providers=[nous]，匿名/api/config=401。实际Edge利用现有Nous会话登录成功。保存后空闲一次采样Agent3.852MiB、Dashboard179.3MiB，不能推导浏览器任务峰值。Wi-Fi connected，SSH、Tailscale、FRP active。

## 公网发布及验收

已保存DNS：sm CNAME ccnode.briconbric.com、仅DNS；HTTPS由Nginx证书提供。实际路径为公网Nginx、既有FRP、SpringMonkey官方管理页。19119仅供公网服务器loopback使用，IPv4/IPv6专属INPUT drop规则已运行，外部实际连接被阻断。既有SSH映射逐项比较未变，frpc verify后一次重启；中继实际认证状态检查PASS。Nous回调已保存为https://sm.briconbric.com/auth/callback，个人客户端保持Only you。

只新增sm独立Nginx站点、ACME webroot、证书及专属防火墙unit，其他业务站点和证书不变。HTTP返回308至HTTPS，TLS1.3和域名校验通过；证书到期时间为2027-02-15 09:59:30 UTC。TLS站点包括WebSocket及排除查询参数的访问日志，避免OAuth code进入访问日志。Nginx语法和reload通过。

原生certbot timer及常见cron路径未发现续期任务。本批新增hermes-dashboard-cert-renew.timer，每日UTC03/15时23分加最多30分钟随机延迟，仅运行certbot renew --cert-name sm.briconbric.com。条件deploy hook只在该证书续期后nginx -t并reload。shell语法、systemd verify、匹配/不匹配hook分支、实际未到期renew退出0及timer active/enabled均PASS；未强制续签，未来真实到期续签尚未发生。Let’s Encrypt免费。Cloudflare Universal SSL也免费，其边缘HTTPS要求开启代理；当前DNS-only直接访问源站，保持现有免费证书。[Cloudflare官方说明](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/)。

Gemini3.8-flash-high最小图片请求返回IMAGE_INPUT_OK；Pro最小请求失败，失败原文未输出。实际桌面截图经主Agent查看及Gemini复核，无可见截断、重叠或加载缺失。1024×768视口开关右边界975.5px，位于视口内。390×844视口开关右边界399px，溢出9px，响应式FAIL。页面源代码未改，V2/V7/V8针对新增或修改控件的像素预算不适用；本次为官方现成管理页部署验收。

真实页面刷新记录49项网络响应，无请求失败或HTTP>=400；第一方Console警告/错误0，浏览器扩展日志单独排除。点击原生Save时未改业务值，以验证持久化能力。用户可从Config的Security页调整安全和审批策略；更改策略的实际放行/拒绝结果需要对应新策略单独验收。

- [桌面实拍1024×768](evidence/hermes-research-dashboard-20261117/admin-security-1024.jpg)
- [完整桌面实拍2698×1518](evidence/hermes-research-dashboard-20261117/admin-security-desktop.jpg)
- [手机实拍390×844，已知溢出](evidence/hermes-research-dashboard-20261117/admin-security-mobile.jpg)
- [匿名公网HTTP/TLS检查](evidence/hermes-research-dashboard-20261117/PUBLIC_HTTP.json)
- [浏览器检查及控件边界](evidence/hermes-research-dashboard-20261117/UI_BROWSER_CHECKS.json)
- [保存后配置语义及权限](evidence/hermes-research-dashboard-20261117/UI_CONFIG_AFTER.json)
- [自动续期验证](evidence/hermes-research-dashboard-20261117/CERTIFICATE_RENEWAL.json)

## 使用与回滚

研究入口保持sudo hermes-pilot chat。产出位于/srv/hermes-pilot/workspace/research-acceptance/e2e；非秘密实现见[脚本说明](../../scripts/hermes-pilot/README.md)。

暂停管理页只停止hermes-dashboard，保留研究CLI。撤销公网发布仅移除sm专属站点并nginx -t后reload、删除新hermes-dashboard FRP代理并验证、移除自有防火墙unit及带hermes-dashboard-loopback注释的两条规则；停用专属证书renew timer并移除对应service/timer和条件deploy hook。保留SSH代理、其他站点、证书、凭据、数据和恢复材料，不执行全局prune或刷新防火墙。

本批只证明真实资料研究链路，未证明独立Chromium沙箱、私网硬隔离、恶意页面安全、大文档容量或长期稳定性。AGENTS不能替代OS/网络隔离；arXiv脚本没有统一响应字节硬上限。本实例限可信单用户。

官方参考：[浏览器](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)、[检索](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search)、[管理页](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)、[arXiv API](https://info.arxiv.org/help/api/user-manual.html)、[FRP](https://gofrp.org/en/docs/examples/vhost-http/)。
