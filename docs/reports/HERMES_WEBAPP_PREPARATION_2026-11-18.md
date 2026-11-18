# WebApp部署、屏幕接管、长任务与账号连接验收

状态：WebApp已发布，账号授权尚未完成。2026-11-18，Asia/Tokyo。用户选定 `https://smapp.briconbric.com`，原 `sm.briconbric.com` 控制台保留；浏览器观看与接管、长任务、账号连接继续分别验收。

## 已完成

- 保持Hermes v0.23.1；管理员容器已切换下列r3-screen镜像，CLI容器保持r2。
- 远端构建 `springmonkey/hermes-pilot:v0.23.1-r3-screen`，image ID `sha256:86cc211bf1b69da29db91c1068123bf1b56b256ea914ef898fd597cf0e32f3f3`，继承r2 `sha256:598f0583092e6d0f3441d33c3951af83da01e2ceb2b79f11d4000b0ef0c01723`。
- 增加官方Bot Screen所需TigerVNC/Xfce/Chromium，以及固定PM锁的cua-driver0.21.0。保留Agent及模型客户端；未升级Hermes核心。
- 隔离候选以UID10001/GID10000、3GiB启动，Screen start、随后status、stop均exit0。观察到1440x900显示、运行PID及仅私有Unix RFB socket。初期检查证明桌面存活，后续公网接管结果另列。
- 非root Nginx配置与driver运行契约通过。入口按Host将smapp转到WebApp9120、sm转到Dashboard9119，宿主继续仅127.0.0.1:9119。入口配置通过只读挂载覆盖镜像内旧候选，不为路由修改重复构建桌面依赖。
- 运行中容器使用Docker init，预算3GiB/1.5CPU/512pids，先执行官方WebApp启动命令保持gateway常驻，随后启动代理及原Dashboard。CLI保持r2及其原有限额。
- 独立 `SpringMonkey WebApp` 登录客户端已保存回调 `https://smapp.briconbric.com/auth/callback`，Portal显示仅本人。原Dashboard客户端及回调保留。Cloudflare新增smapp CNAME到ccnode，仅DNS；独立Let's Encrypt证书、Nginx配置及两张证书续期服务通过检查。
- 两个公网域名匿名 `/api/config` 均401；真实Nous登录进入WebApp，主模型显示gpt-6.1-sol。完成公开网页读取、文件写入和读回。等待60秒的工具运行期间关闭浏览器tab，重开后看到已执行工具及继续产出的结果；实际测试为60秒，没有将7200秒预算当作两小时实测。
- 文件浏览使用原生 `HERMES_DASHBOARD_FILES_ROOT=/workspace`；真实侧栏及Markdown预览通过。文件边界正例允许工作区成果，反例拒绝 `/opt/data/auth.json`，返回403。
- Bot Screen已实际显示1440x900桌面和Chromium公开网页；接管时原生computer_use capture返回human_has_control，Hand back后原Agent capture识别同一Example Domain。
- 固定Docker内部hostname为springmonkey-hermes，处理重建后Chromium将旧随机hostname视为其他主机的问题。仅在Screen及容器停止后清理该profile的三个Singleton符号链接，保留浏览器数据。

## 密码保存实际验证

已检查已安装固定版 `agent/vault_store.py`：秘密载荷使用Fernet加密，默认密钥为同目录0600文件。当前真实管理员home没有vault，未保存用户网页密码。

`acceptance_vault.py` 在临时目录生成合成随机密码，验证：

| 项目 | 结果 |
| --- | --- |
| 密文文件中查找明文密码 | 不存在，PASS |
| 暴露给模型的项目元数据包含密码 | 不包含，PASS |
| 新建VaultStore实例读回秘密 | 匹配，PASS |
| 密文和密钥权限 | 均0600，PASS |
| 篡改密文后的读取 | 拒绝，PASS |

合成目录已随测试退出清理。此项验证存储行为，没有向模型发送合成或真实密码，也没有创建真实账号登录。

安全边界：默认同机保存密钥与密文，取得两者或拥有同用户/root权限的程序可以解密。文件权限及加密不构成独立凭据代理。官方支持OS keychain及1Password/Bitwarden；无可用keychain时可退回文件模式，锁住的外部密码库不能用于无交互任务。OAuth令牌与浏览器Cookie采用各自的存储机制，本次密码测试不覆盖这些凭据。

## 计划配置及剩余验收

已增加WebApp、computer_use、cronjob及Bot Screen按需启动；headed=true、原生每Bot持久浏览器目录、空闲超时1800秒。单次Agent预算7200秒、最大工具迭代100；保留原审批模式。CLI宿主wrapper仍有900秒上限，长任务入口以WebApp/gateway为准。GPT主模型、MoA参考及辅助设置保持。

| 必需项 | 当前判定 | 完成标准 |
| --- | --- | --- |
| 公网WebApp及原管理页 | 核心通过 | 独立回调、部署、本人登录、匿名拒绝、真实消息及文件输出、重建后历史及文件保留；最终截图另存 |
| 浏览器观看与接管 | 控制闭环通过，账号待验 | 同一真实浏览器画面、人工输入、human_has_control、交回后原Agent capture均通过；真实账号登录持久化仍待用户登录 |
| 长任务 | 关页继续通过 | 实测sleep60期间关页，重开后有进度及成果；预算7200秒未作两小时压测；运行中容器崩溃不保证自动重放外部写入 |
| Gmail/Google Drive | 未完成 | 选择正式连接路径、服务OAuth授权、最小读写范围、真实只读检查和受控写入审批 |
| Microsoft 365/OneDrive | 未完成 | 同上；Marketplace microsoft365插件标注要求>=0.21.3,<0.22，当前0.23.1需采用兼容路径，不强装该旧约束插件 |
| GitHub及其他网页系统 | 未完成 | 逐服务授权；普通网页走同一可接管浏览器，MFA及登录由用户完成 |
| 密码库实际UI填充 | 未完成 | 密码遮蔽录入、域名匹配填充、错误域名拒绝、日志与会话无秘密泄露 |

允许Hermes以后发现成熟连接器、编写并测试Skills；新增账号授权、权限扩大、安装高权限插件及生产性写入仍按对应授权处理。当前保留70项只读Skills，未放宽为任意自修改。

## 已解决的候选问题

1. PM拒绝具名包与--tools-only同时使用，改用官方具名安装。
2. 基础镜像VOLUME /opt/data使构建期工具不可见，改用隔离构建home，通过PM校验后复制同字节driver到/opt/pilot并显式指定路径。
3. Nginx非root默认fastcgi等临时目录不可写，明确改为/tmp。
4. Xfce启动后立即停止，日志确认UID10001缺少passwd记录；镜像补充相同UID/GID账户元数据，未设密码、未授权sudo，新候选存活检查通过。
5. Portal页面与官方注册API均HTTP400拒绝/app路径回调。经用户选定改用smapp独立根域名，没有绕过Portal验证。
6. 配置控制器使用既有hermes_yaml；原PyYAML导入失败发生在写入及停服务之前。首轮就绪不通过自动恢复r2，后将冷启动窗口及认证302纳入就绪判定，保留失败日志。
7. 初次空桌面computer_use按键返回No active window，保留审批限制。原生dock打开浏览器后，截图及交回流程通过。
8. 最终刷新时多项静态资源502。内层Nginx日志明确worker_connections are not enough，容器未重启、未OOM，约813MiB/3GiB。将连接上限256改为2048，语法检查后仅reload Nginx。随后完整页面加载记录HTTP错误0、failedLoads0、WebSocket101，屏幕重开及Bot控制状态恢复。

## 最终UI证据与范围

固定版原生UI，没有修改前端组件或CSS。真实桌面视口2698×1524、远端屏幕1440×900，数据为公开测试网页和合成任务。真实浏览器完成聊天、文件预览、屏幕观看、人工输入和交回；原控制台重新加载后TUI ready。

截图视觉复核：Gemini 3.1 Pro图片最小请求两次均upstream_error；3.8 Flash High图片验证及正式复核成功。它认为亮色外壳、浏览器和控制条清晰，同时标记双层滚动、长页下缘裁切及dock贴边风险。主Agent确认公开长页面需滚动，未修改原生布局，也未据此声明像素几何或全场景视觉PASS。

窄屏未完成：viewport工具请求1280×900后，读取实际innerWidth仍为2698；已reset，未用无效视口冒充响应式检查。当前推荐桌面使用，手机布局和操作热区没有验收。

正式证据：[逐项结果](evidence/hermes-webapp-20261118/ACCEPTANCE.json)、[运行身份与源码摘要](evidence/hermes-webapp-20261118/DELIVERY_MANIFEST.json)、[公网认证](evidence/hermes-webapp-20261118/PUBLIC_BOUNDARY.json)、[最终真实屏幕](evidence/hermes-webapp-20261118/smapp-screen-final.png)、[接管状态](evidence/hermes-webapp-20261118/smapp-takeover.png)、[独立视觉意见](evidence/hermes-webapp-20261118/GEMINI_VISUAL_REVIEW.txt)。配置、Python及JSON静态检查通过，远端入口和启动脚本摘要与交付源码一致。

账号现状：当前Nous Portal连接器目录显示54项，搜索Gmail和Microsoft均No app matches；该目录不能作为两项账号已接入的证据。网页登录可使用可接管浏览器，正式API连接另选兼容OAuth路径。没有连接邮箱、网盘或Discord，也没有保存真实密码。三项总体完成仍受账号授权及真实登录持久化验收限制。

以上修复复用原apt/PM缓存及有效检查，只重测直接受影响项，没有重复CLI、MoA或70Skills全套测试。r2和本批停止的容器仅作为本次切换回滚资料，未并行运行旧入口。

## 依据

账号后续核查见 [SpringMonkey 账号接入](../ops/HERMES_ACCOUNT_CONNECTIONS.md)。

- [官方WebApp](https://hermes-agent.nousresearch.com/docs/user-guide/desktop)
- [Bot Screen](https://hermes-agent.nousresearch.com/docs/user-guide/features/bot-screen)
- [密码库及保护边界](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-vault)
- [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals)
- [Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)
- [Microsoft 365插件约束](https://hermes-agent.nousresearch.com/marketplace/microsoft365)
