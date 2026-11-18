# SpringMonkey Hermes 账号接入

## 2026-11-18 Gmail 登录结果

用户已在 Bot Screen 尝试登录。Google 页面显示 “Couldn’t sign you in” 和 “This browser or app may not be secure”。记录为服务方拒绝当前登录环境。单凭页面无法确认命中的具体检测条件。暂停该远端网页登录路径。Google 为桌面应用提供系统浏览器加本地回环的 OAuth 授权流程。

- [Google 支持的浏览器](https://support.google.com/accounts/answer/7675428)
- [桌面 OAuth 流程](https://developers.google.com/identity/protocols/oauth2/native-app)

## Gmail 首批试点

1. 使用专用 Google Cloud 项目，仅启用 Gmail API。建立 Desktop app OAuth 客户端，按账号所属组织选择受众。公司账号遵循组织第三方应用策略。项目和客户端均待创建。
2. 在用户本机常用浏览器完成 Google 授权。首批只请求 `https://www.googleapis.com/auth/gmail.readonly`。该权限可读取邮件正文及设置，Google 将其列为受限范围。试跑仅查询用户指定的测试邮件，并限制结果读取字段。日历和 Drive 单独评估。
3. 本机回环只用于正式授权回调。采用支持 state 与 PKCE 的流程，验证回调与当前授权请求绑定。避免将回调地址、认证码或令牌写进聊天、工作区和模型上下文。候选工具的代理专用回调实现未核验到 state 与 PKCE，试点不采用该分支。
4. 在 SpringMonkey 用独立运行身份和受限目录保存令牌，先验证持久化与缓存权限。授权完成后只用指定的合成测试邮件验收查询和读回，核对实际授权范围、重启后续用及撤销行为，再确定交给 Hermes 的接口。

Google Workspace CLI 固定为 `0.22.5`。固定版 `--scopes` 接受完整、逗号分隔的权限 URI，直接使用自定义列表。默认及 `--readonly` 预设覆盖多个服务，首批使用显式 URI。上游二进制通过固定发布包 SHA256 校验。原候选构建因 npm 12 阻止 postinstall 导致缺少 gws。Google 外部应用处于 Testing 状态时，带 Gmail 范围的刷新令牌七天到期。生产长期使用另核对项目发布状态和组织策略。

- [固定版作用域与回调源码](https://github.com/googleworkspace/cli/blob/v0.22.5/crates/google-workspace-cli/src/auth_commands.rs)
- [固定发布包](https://github.com/googleworkspace/cli/releases/tag/v0.22.5)
- [Gmail 权限范围](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Google 刷新令牌有效期](https://developers.google.com/identity/protocols/oauth2#expiration)

SpringMonkey 上的隔离候选镜像 `sha256:15e482b8a7c266b134faa01823b425979a17e456901a7db944d31205e8b52946` 已通过发布包 SHA256 检查。在无网络、无生产配置挂载、只读根文件系统、UID 10001 的容器中实测 `gws --version` 返回 0.22.5，`gws auth login --help` 显示自定义权限参数。候选镜像尚未切换为生产镜像。真实授权、实际邮件读取、撤销和令牌持久化待验证。

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
