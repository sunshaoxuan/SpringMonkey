# Hermes 网页研究与管理页

2026-11-17，Asia/Tokyo。用户授权补齐网页研究能力，并新增公网管理页，域名sm.briconbric.com、Nous登录，已自行注册名称SpringMonkey的客户端。Discord及预算代理保持未接入。

## 状态

网页研究验收PASS。官方管理页在主机及FRP中继运行，公网发布尚待用户对已准备的Cloudflare DNS和Nous回调两项保存作动作时确认。HTTPS、完整OAuth登录、UI策略保存、浏览器控制台/网络/响应式及截图验收尚未完成，公网管理页整体验收保持未通过。

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

唯一现行配置为/srv/hermes-pilot/data/config.yaml：管理员UID10001拥有0640，GID10000可读；home根为root所有、GID10000、1770 sticky。旧/etc/hermes-pilot/config.json仅留root-only批次备份，运行不再读取。官方原子YAML保存的scratch实测保留0640/UID/GID；实际Agent不可写配置，对管理员owned测试文件删除被拒绝。没有配置同步桥或双读，完整UI保存仍待登录验收。

AGENTS和Skills仍只读，没有宿主根、Docker socket及SSH/Tailscale/FRP/Discord恢复材料挂载。凭据仅保存在root-only远端env及本机DPAPI恢复副本，剪贴板已清空，不进入Git。Nous个人账号实际注册成功，页面显示Only you，表单无付款项目；未订阅Nous推理或托管服务。

本机/login=200，/api/status返回auth_required=true及providers=[nous]，匿名/api/config=401。空闲一次采样Agent1.305MiB、Dashboard165MiB，不能推导浏览器任务峰值。Wi-Fi connected，SSH、Tailscale、FRP active。

## 公网准备与剩余项

待保存DNS：sm CNAME ccnode.briconbric.com、仅DNS；HTTPS由Nginx证书提供。计划路径为公网Nginx、既有FRP、SpringMonkey官方管理页。19119仅供公网服务器loopback使用，IPv4/IPv6专属INPUT drop规则已运行。既有SSH映射逐项比较未变，frpc verify后一次重启；中继实际认证状态检查PASS。

只新增sm独立Nginx站点、ACME webroot及专属防火墙unit，其他业务站点和证书不变。当前HTTP仅503维护页及ACME challenge，没有管理功能。预备TLS站点包括WebSocket及排除查询参数的访问日志。待DNS和Nous回调保存确认后签发独立Let’s Encrypt证书、启用HTTPS、验证完整OAuth及策略保存。当前无可用公网管理URL。

Gemini3.8-flash-high最小图片请求返回IMAGE_INPUT_OK；Pro最小请求失败，失败原文未输出。真正管理页视觉复核尚待登录后截图。

## 使用与回滚

研究入口保持sudo hermes-pilot chat。产出位于/srv/hermes-pilot/workspace/research-acceptance/e2e；非秘密实现见[脚本说明](../../scripts/hermes-pilot/README.md)。

暂停管理页只停止hermes-dashboard，保留研究CLI。撤销公网准备仅移除sm专属站点并nginx -t后reload、删除新hermes-dashboard FRP代理并验证、移除自有防火墙unit及带hermes-dashboard-loopback注释的两条规则。保留SSH代理、其他站点、证书、凭据、数据和恢复材料，不执行全局prune或刷新防火墙。

本批只证明真实资料研究链路，未证明独立Chromium沙箱、私网硬隔离、恶意页面安全、大文档容量或长期稳定性。AGENTS不能替代OS/网络隔离；arXiv脚本没有统一响应字节硬上限。本实例限可信单用户。

官方参考：[浏览器](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)、[检索](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search)、[管理页](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)、[arXiv API](https://info.arxiv.org/help/api/user-manual.html)、[FRP](https://gofrp.org/en/docs/examples/vhost-http/)。
