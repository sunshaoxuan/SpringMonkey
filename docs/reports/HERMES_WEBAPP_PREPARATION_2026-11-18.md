# WebApp、浏览器接管、长任务及账号连接准备

状态：候选准备，尚未发布。2026-11-18，Asia/Tokyo。用户已授权采用Hermes WebApp，并将浏览器观看与接管、长任务、账号连接列为必须能力；进一步确认Gmail、Microsoft 365及所列服务优先，并询问密码加密保存。

## 已完成

- 原固定Hermes v0.23.1、已验r2镜像及当前Dashboard继续运行。
- 远端构建 `springmonkey/hermes-pilot:v0.23.1-r3-screen`，image ID `sha256:86cc211bf1b69da29db91c1068123bf1b56b256ea914ef898fd597cf0e32f3f3`，继承r2 `sha256:598f0583092e6d0f3441d33c3951af83da01e2ceb2b79f11d4000b0ef0c01723`。
- 增加官方Bot Screen所需TigerVNC/Xfce/Chromium，以及固定PM锁的cua-driver0.21.0。保留Agent及模型客户端；未升级Hermes核心。
- 隔离候选以UID10001/GID10000、3GiB启动，Screen start、随后status、stop均exit0。观察到1440x900显示、运行PID及仅私有Unix RFB socket，控制权为Agent。该结果证明桌面进程可存活，公网观看与人工接管尚待发布后验收。
- 非root Nginx配置与driver运行契约通过。Nginx将同域名 `/app/` 转到WebApp9120，原根路径转到Dashboard9119，使用官方X-Forwarded-Prefix；宿主继续仅127.0.0.1:9119。当前尚未替换生产容器。
- 启动脚本准备使用Docker init，Dashboard预算3GiB/1.5CPU/512pids，先执行官方WebApp启动命令保持gateway常驻，随后启动代理及原Dashboard。CLI仍保持r2及其原有容器限额。
- 新建独立 `SpringMonkey WebApp` 登录客户端，引用存入本机DPAPI资料。Portal显示访问仅本人；回调已填 `https://sm.briconbric.com/app/auth/callback`，尚未SAVE，待用户确认。原Dashboard客户端及回调未改。

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

仓库模板为待发布候选，当前生产仍使用原配置。拟增加WebApp、computer_use、cronjob及Bot Screen自动按需启动；本地浏览器headed=true、保持原生每Bot持久浏览器目录，空闲超时1800秒。单次Agent预算从900秒调整7200秒、最大工具迭代100；保持原审批模式，后台写入不能绕过原审批。CLI宿主wrapper仍有900秒上限，长任务入口以WebApp/gateway为准。

| 必需项 | 当前判定 | 完成标准 |
| --- | --- | --- |
| 公网WebApp及原管理页 | 未完成 | 保存独立回调、部署、Nous本人登录、匿名拒绝、真实消息与文件输出、重启恢复 |
| 浏览器观看与接管 | 未完成 | 同一真实浏览器画面可见；接管时工具拒绝human_has_control，交回后继续；登录会话持久化 |
| 长任务 | 未完成 | 关页后后台继续、重开可看进度和成果；验证停止与恢复语义，报告实际测试时长；运行中进程崩溃不承诺无条件自动重放外部写入 |
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

以上修复复用原apt/PM缓存及有效检查，只重测直接受影响项。没有重复CLI、MoA或70Skills的既有全套测试。最终端到端验收尚未通过，当前不得宣布三项能力已上线。

## 依据

- [官方WebApp](https://hermes-agent.nousresearch.com/docs/user-guide/desktop)
- [Bot Screen](https://hermes-agent.nousresearch.com/docs/user-guide/features/bot-screen)
- [密码库及保护边界](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-vault)
- [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals)
- [Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)
- [Microsoft 365插件约束](https://hermes-agent.nousresearch.com/marketplace/microsoft365)
