# SpringMonkey 重装与远程恢复验收

2026-11-16：已重装为 Ubuntu Server 26.10，内核 `7.3.0-10-generic`，主机名保持 `ubuntu-2625`。新系统首次启动和再次重启均通过，Wi-Fi、Tailscale SSH、FRP SSH 自动恢复。主机功能验收 PASS；本机旧测试文件清理存在文末所列策略阻塞项。

最终范围为干净 Ubuntu 及联网、SSH、防火墙、Tailscale、FRP 所需组件。OpenClaw、Docker、Chrome/Chromium 未安装。Discord 仅保留静态备份，不重连、不发送消息，不安装聊天服务或 Harness。

## 实际验收

| 项目 | 结果 |
| --- | --- |
| Ubuntu 26.10 原生启动及再次重启 | PASS，两次 boot-id 不同 |
| 真实 Wi-Fi | PASS，已连接、系统级配置、autoconnect=yes、默认路由正确 |
| Tailscale 原身份 | PASS，live、首次启动、再次重启均实际执行 SSH 命令 |
| FRP 0.72.0 | PASS，安装环境及两次新系统启动均完成固定主机密钥的 SSH 登录 |
| SSH 管理用户与 sudo | PASS，springadmin 公钥登录、免交互 sudo、权限检查通过 |
| SSH 与防火墙 | PASS，UFW active；OpenSSH root、密码及键盘交互认证均关闭 |
| 旧业务环境移除 | PASS，旧应用二进制及相关服务不存在 |
| Discord 静态保留 | PASS，本机 DPAPI 与新主机 root/0600 文件哈希相同；未重连 |
| 隔离安装与安全负例 | PASS，同盘 RAM 安装/重启、错盘、篡改、非 SSH 代理、root 登录拒绝、非 SSH 入站拦截、诊断写入边界、恢复入口拒绝等分别验证 |

正式证据：[真机验收](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/PHYSICAL_RESET_VALIDATION.json)、[新系统范围核验](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/NATIVE_ACCEPTANCE.json)、[同盘隔离验证](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/RAM_INSTALL_VALIDATION.json)、[失败诊断边界](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/PERSISTENCE_VM_VALIDATION.json)。真实 Wi-Fi 与生产身份结论取自真机；隔离测试使用虚拟以太网，未克隆生产身份。

## 连接与备份

现有 Tailscale 入口保持 `tailscale ssh root@ubuntu-2625`。FRP 使用 springadmin 的预置管理密钥，私钥保存在本机 DPAPI 恢复包，实际连接按准备时固定的主机公钥校验。原 root OpenSSH 密码入口已随重装移除。

Discord 连接、认证材料、公司/私有路由相关配置、DM 策略及旧配置副本已保留。额外核查当前/旧 credentials 目录，未发现独立 Discord 配对/允许列表文件。未采集聊天历史。

* 本机正式材料：[recovery](C:/workspace/codex-work/muse-selfhost-research-20261116/recovery)，包含 DPAPI 密文与公开校验元数据。
* 新主机文件：`/srv/springmonkey-preserved/discord/DISCORD_CONNECTIONS.json`，root 所有，0600，上级保留目录0700。
* Discord SHA-256：`e4b065c6ee5bfd20ee9393c9b26024bebb8a18277cf5a1872c6cc2cff9001179`。
* 原 Tailscale 稳定快照已加密保留，最新归档包含15文件且 DPAPI 还原通过，首轮快照另存。

## 输入与执行

官方基础 ISO SHA-256 为 `c8e9d797f718404bdb1e282f8466fe6f5f2e9f03c814bdf11b31326d45200929`，本机与远端整文件校验均通过。最终生产 ISO 仅在远端制作，SHA-256 为 `6b8bcff6e094ad5351cbee81942bed232abb2731e019816abdc5ec347deabb56`，manifest 为 `d295e914d5ef2532a91a1b63bc9a159f3bf688257da7bce6b7bed4c46a5ccd57`。

生产 payload 源码固定 `07c6a54ebfc63c9837d652703bff8ed1f633b1fe`；Windows 控制器固定 `04a1b618288a11a78bf1238fb584419bd088f89b`。源码已推送 `ops/ubuntu-reset-20261116`，安装前远端 Git worktree 与 payload 源码一致。控制器修复未改变有效 Linux 候选或重发重启。

首轮 one-shot 在未收到清盘确认时回到原 Ubuntu25.10，具体 live 失败阶段未保留。复核凭据/MAC/磁盘身份后增加150秒 Wi-Fi 关联、地址及路由等待，以及受保护的清盘前失败记录。第二轮控制连接曾 EOF，恢复跟踪同一次启动后，实际验证两条 live SSH 线路与内存/磁盘前置，才放行重新分区。

同盘启动使用原主机签名 EFI 链、官方签名内核、追加释放脚本的 initramfs、GRUB one-shot、toram。释放源 ISO 分区后仍要求精确磁盘身份、目标盘独占访问及足够内存。新系统使用独立 NetworkManager 配置，Tailscale 与 FRP 独立重连。旧系统及临时安装环境已随重新分区移除。

源码：[reinstall](../../scripts/reinstall/README.md)。来源：[Ubuntu 校验清单](https://releases.ubuntu.com/26.10/SHA256SUMS)、[autoinstall](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html)、[initramfs-tools](https://manpages.ubuntu.com/manpages/resolute/man7/initramfs-tools.7.html)、[Linux initramfs 格式](https://docs.kernel.org/driver-api/early-userspace/buffer-format.html)、[FRP v0.72.0](https://github.com/fatedier/frp/releases/tag/v0.72.0)。

## 本机清理限制

后续 FRP 下载、二进制准备与执行全部在远端完成，本机配置恢复包不含 FRP 二进制。旧文件 `C:/workspace/codex-work/muse-selfhost-research-20261116/fixture/payload/frpc` 的两次原生删除命令在执行前收到 `CreateProcess Rejected: blocked by policy`。该文件仍保留，未更改安全设置或切换工具绕过。此结果不能归因于 Windows ACL、OneDrive 或具体杀毒产品。其他临时材料的实际清理结果见 [清理回执](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/CLEANUP_RECEIPT.json)。

原生 PowerShell 已清理878个临时文件、3,201,310,171逻辑字节及17个空目录；61份保护材料的哈希保持一致。上述FRP文件和两个无法读取的Linux测试链接明确排除，承载它们的目录保留。主机验收PASS，本机清理按“存在排除保留项”交付。
