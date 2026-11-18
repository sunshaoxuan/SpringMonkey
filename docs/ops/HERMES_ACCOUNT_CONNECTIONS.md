# SpringMonkey Hermes 账号接入

## 2026-11-18 Gmail 登录结果

用户已在 Bot Screen 尝试登录。Google 页面显示 “Couldn’t sign you in” 和 “This browser or app may not be secure”。记录为服务方拒绝当前登录环境。单凭页面无法确认命中的具体检测条件。暂停该远端网页登录路径。Google 为桌面应用提供系统浏览器加本地回环的 OAuth 授权流程。

- [Google 支持的浏览器](https://support.google.com/accounts/answer/7675428)
- [桌面 OAuth 流程](https://developers.google.com/identity/protocols/oauth2/native-app)

## Gmail 首批试点

1. 用户指定复用已改名为 SpringMonkey 的 Google Cloud 项目。先查看现有 OAuth 客户端、受众和 Gmail API 启用状态，再为 Hermes 新建设计为 Desktop app 的专用客户端。试点仅需 Gmail API。已有客户端、项目受众和发布状态的变更均须先评估其对现有应用的影响。公司账号遵循组织第三方应用策略。
2. 在用户本机常用浏览器完成 Google 授权。首批只请求 `https://www.googleapis.com/auth/gmail.readonly`。该权限可读取邮件正文及设置，Google 将其列为受限范围。试跑仅查询用户指定的测试邮件，并限制结果读取字段。日历和 Drive 单独评估。
3. 本机回环只用于正式授权回调。采用支持 state 与 PKCE 的流程，验证回调与当前授权请求绑定。避免将回调地址、认证码或令牌写进聊天、工作区和模型上下文。候选工具的代理专用回调实现未核验到 state 与 PKCE，试点不采用该分支。
4. 在 SpringMonkey 用独立运行身份和受限目录保存令牌，先验证持久化与缓存权限。授权完成后只用指定的合成测试邮件验收查询和读回，核对实际授权范围、重启后续用及撤销行为，再确定交给 Hermes 的接口。

Google 公布的 Gmail API 标准用量无额外费用。官方列出的每日计费门槛为每项目 8,000 万配额单位，超量收费计划另行公告。共享项目的实际配额与用量需在控制台确认。本次试点为手动查询指定测试邮件，现有项目的结算配置未变更。

Google Workspace CLI 固定为 `0.22.5`。固定版 `--scopes` 接受完整、逗号分隔的权限 URI，直接使用自定义列表。默认及 `--readonly` 预设覆盖多个服务，首批使用显式 URI。上游二进制通过固定发布包 SHA256 校验。原候选构建因 npm 12 阻止 postinstall 导致缺少 gws。Google 外部应用处于 Testing 状态时，带 Gmail 范围的刷新令牌七天到期。生产长期使用另核对项目发布状态和组织策略。

- [固定版作用域与回调源码](https://github.com/googleworkspace/cli/blob/v0.22.5/crates/google-workspace-cli/src/auth_commands.rs)
- [Google Cloud OAuth 客户端配置](https://developers.google.com/workspace/guides/create-credentials#oauth-client-id)
- [Google Auth Platform 受众与数据权限](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [固定发布包](https://github.com/googleworkspace/cli/releases/tag/v0.22.5)
- [Gmail 权限范围](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail API 用量与计费](https://developers.google.com/workspace/gmail/api/reference/quota)
- [Google 刷新令牌有效期](https://developers.google.com/identity/protocols/oauth2#expiration)

SpringMonkey 上的隔离候选镜像 `sha256:15e482b8a7c266b134faa01823b425979a17e456901a7db944d31205e8b52946` 已通过发布包 SHA256 检查。在无网络、无生产配置挂载、只读根文件系统、UID 10001 的容器中实测 `gws --version` 返回 0.22.5，`gws auth login --help` 显示自定义权限参数。候选镜像尚未切换为生产镜像。真实授权、实际邮件读取、撤销和令牌持久化待验证。

已在登录后的 Google Cloud 控制台核对 SpringMonkey 的 OAuth 客户端列表，创建前页面显示暂无 OAuth 客户端。经用户确认，已创建名为 `SpringMonkey Hermes Gmail` 的桌面应用客户端，并勾选用于 AI 智能体。Google 显示创建成功，本机下载的 JSON 已验证是目标项目的桌面客户端凭据。凭据尚未部署到 SpringMonkey。

已在目标项目开启 Gmail API，控制台跳转到 Gmail API 管理概览。Google Auth Platform 显示应用为外部、发布状态为测试。已核对控制台 Google 账号与用户已连接的 Gmail 账号一致，并将该账号加入测试名单，回读确认只有这一名测试用户。

本机 Edge 完成了 Google 的测试应用确认及用户授权。请求仅含 Gmail 只读，回环地址和 PKCE S256 参数已验证，错误 state 的合成回调返回 HTTP 400。授权回调将令牌用 Windows DPAPI 加密保存。SpringMonkey 实际刷新令牌并调用 Gmail `getProfile`，结果为 HTTP 200。验收输出仅包含成功信号。

## Hermes 运行时接入与验证

当前 WebApp 和 CLI 共用宿主机的 Gmail 只读服务。systemd 通过主机密钥加密凭据，服务使用专用动态用户。加密文件为 root 所有、0600。主机密钥位于同机未加密磁盘，由系统权限保护。Hermes 容器使用已有的只读技能目录访问 Unix socket，权限为 root:10000、0660。凭据目录未挂载到容器。已有容器镜像无需切换。

在 Hermes 中使用 `gmail-readonly`。它可检查连接、按条件查找最多十封邮件，再按消息 ID 读取少量邮件头、摘要及最多 12,000 字符的纯文本。查询和读取由用户明确的任务触发。当前接口未提供 HTML 和附件读取。

两容器实际 `status` 和原生 `skill_view` 通过。Hermes CLI 的真实对话加载技能并执行状态命令，返回 `connected: true` 和 `gmail.readonly`。Gmail 真实空搜索通过，空结果的 HTTP 204 映射为空列表。无关 UID 无法连接 socket，POST、非法消息 ID、未知操作均被本地拒绝。邮件纯文本解析用合成样例通过，验收没有打开真实邮件正文。公网 WebApp 无会话仍跳转 Nous 登录。

如需停用接入，先停止并禁用 `hermes-gmail-readonly.socket`，然后停止 `hermes-gmail-readonly.service`。如需撤销持续访问，在 Google 账号的第三方连接页面撤销对应授权。

- [服务和技能源码](../../scripts/hermes-pilot/gmail)
- [Gmail getProfile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile)

## 长期授权迁移

Google 对外部测试应用发出的 Gmail 刷新令牌设有七天期限。迁移方案是在品牌资料齐备后把该 OAuth 应用发布至生产状态，再由所有者同意一次新授权。新令牌通过作用域、Google 刷新和 Gmail `getProfile` 检查后才切换服务器加密凭据。短期回滚保留原凭据，前提是它仍在有效期内。

已将旧项目的 OAuth 品牌名称由 `BoBGia` 改为 `SpringMonkey Hermes`。经所有者同意，公开了 [应用介绍](https://smapp.briconbric.com/gmail) 和 [Gmail 数据隐私说明](https://smapp.briconbric.com/gmail/privacy)，并将这两条 URL 及 Google 要求的注册域名 `briconbric.com` 保存到品牌资料。两页采用 Nginx 精确路径规则，静态文件由现有只读挂载提供。经所有者明确授权发布后，控制台回读为外部、正式版。

浏览器在 1024×900 和 390×844 验证页面、链接导航、水平无溢出和链接热区。无脚本异常和网络失败。公网匿名 GET 两页均 HTTP 200，主页仍跳转到 Nous 登录，匿名 `/api/config` 返回 HTTP 401，未匹配的 Gmail 子路径仍走原认证路由。应用名、首页、隐私链接和域名均收到 Google 品牌保存回执。

发布外部 OAuth 应用后，其他 Google 账号也能发起授权。本机 Edge 完成了所有者的新授权。授权请求通过仅 Gmail 只读、离线访问、回环、PKCE 和无效 state 拒绝检查。

已在 SpringMonkey 验证新旧刷新令牌不同，但经 Google `getProfile` 比对为同一邮箱。新令牌刷新与 `getProfile` 均返回 HTTP 200，作用域恰为 Gmail 只读。Google 未返回刷新令牌固定到期时间，外部测试应用的七天期限不适用于这次正式版授权。撤销、带 Gmail 权限时修改 Google 密码、六个月未使用等仍可能使令牌失效。

已原子替换服务的加密凭据并重启 Gmail 只读服务，两容器的连接状态均通过。Hermes 真实对话加载 `gmail-readonly` 并成功调用状态命令，返回 `connected: true`、`gmail.readonly`，命令退出码 0。旧密文保留于宿主机 root 专用回滚目录，文件权限 0600。Hermes 容器保持原镜像，WebApp 匿名访问仍要求 Nous 登录，匿名配置请求返回 HTTP 401。验收期间未读取真实邮件正文。

- [Google 应用受众与发布状态](https://support.google.com/cloud/answer/15549945)
- [个人用途验证例外](https://support.google.com/cloud/answer/13464323)
- [应用首页、隐私说明与网域要求](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
- [Google OAuth 刷新令牌失效条件](https://developers.google.com/identity/protocols/oauth2#expiration)

## 其他验收状态

| 项目 | 状态 |
| --- | --- |
| Microsoft 365 与 OneDrive | 待接入。已检查 Hermes Marketplace 的 Microsoft 365 插件版本约束，当前已部署 Hermes 0.23.1 在其支持范围外。PnP CLI 默认持久令牌缓存未加密。 |
| GitHub 私有账号 | 待接入。公开仓库读取沿用既有能力。 |
| 密码库 | 复用前批隔离合成凭据的加密及重载验证。真实账号密码、WebApp 填充和服务端真实登录持久化待验。 |
| 手机视口 | 待针对真实窄屏验收。 |
| Discord | 关闭。 |

工作区规则已同步到两容器。允许为用户指定的服务准备连接，正式授权仍由账号所有人完成。已验证两容器内文件与宿主机摘要一致。SpringMonkey 的既有 WebApp 继续由 Nous 登录保护。

- [Microsoft 365 插件](https://hermes-agent.nousresearch.com/marketplace/microsoft365)
- [PnP CLI 连接持久化说明](https://pnp.github.io/cli-microsoft365/concepts/persisting-connection/)
