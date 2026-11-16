# SpringMonkey 远程重置前检

日期：2026-11-16，Asia/Tokyo。主记录：[TASK_GUIDE.md](C:/workspace/codex-work/muse-selfhost-research-20261116/TASK_GUIDE.md)。

## 当前目标与用户纠正

用户要求清除全部旧环境，重装最新 Ubuntu，机器无人现场操作时自动恢复远程连接。用户确认主机为单机，无其他管理入口，现场只能晚间接触；接受 FRP 与 Tailscale，重装后至少一条线路实际可用。Wi-Fi 开机自动联网为独立必需项。Hermes 安装不属于当前批次。

## 只读证据

启动/磁盘/网络采样为 16:18:09，无线配置采样为 16:19:58。

* [启动及连接前检](C:/workspace/codex-work/muse-selfhost-research-20261116/RESET_PREFLIGHT.json)
* [Wi-Fi 脱敏前检](C:/workspace/codex-work/muse-selfhost-research-20261116/WIFI_PREFLIGHT.json)

已核对 hostname 为 ubuntu-2625，使用既有 known_hosts 校验的 FRP SSH。未执行软件卸载、登录变更、网卡切换、磁盘修改、引导修改、重启或重装。

| 检查 | 结果 |
| --- | --- |
| 启动 | UEFI，Secure Boot enabled，GRUB 2.14，默认项 0 |
| 磁盘 | 仅 /dev/sda，一块约 336 GiB 的磁盘；sda1 为 EFI，sda2 为现用 ext4 根分区，基本占满整盘的分区范围 |
| 备用系统 | 分区清单未显示第二个根分区或恢复分区；旧 Windows EFI 记录无法证明存在可用的 Windows 系统 |
| 独立恢复 | 用户确认无独立管理入口；未发现 /dev/ipmi0 或可用 watchdog 设备 |
| 当前联网 | wlp4s0 Wi-Fi connected，默认路由走该接口；enp2s0 有线接口 unavailable |
| 无线硬件 | Intel Dual Band Wireless-AC 3168NGW，当前驱动 iwlwifi，modinfo 可见签名 |
| 无线配置 | NetworkManager，system-wide，autoconnect=yes，WPA-PSK，PSK flags=0，IPv4/IPv6 自动获取 |
| 无线凭据 | root 可在内存中读取已保存的 SSID/PSK，仅输出可恢复布尔值；未输出或另存明文 |
| 无线开关 | 软件和硬件均 unblocked |
| FRP | ssh/frpc 均 enabled；已有 FRP 配置包含 22 端口及旧 OpenClaw 端口转发，存在认证设置 |
| Tailscale | enabled，当前 NeedsLogin，self_online=false，存在认证挑战 |

一条 findmnt 组合查询返回非零，挂载关系采用成功的 lsblk 与 df 结果核对；未据失败输出判定挂载异常。旧日志工具 last 不存在，不推导重启历史。未测试新安装介质中的无线驱动、固件、Wi-Fi 协商和实际重启连接。

## 自动恢复设计要求

重装后的最小系统为 Ubuntu、无线网络所需系统组件、OpenSSH，以及保持远程可达所需的 FRP/Tailscale。现有 OpenClaw 的 18789 转发不得作为新系统恢复内容，其他旧业务和定时器均不迁移。

安装环境和新系统两处都必须预置原无线网络所需配置，安装和首次启动不能依赖桌面用户登录、交互输入密码或旧根分区仍然存在。SSID/PSK、FRP 认证信息应经受保护的专用安装配置传递，避免进入普通报告、Git、终端输出或公开 seed URL。正式切换前需要验证目标镜像无线固件和驱动、Secure Boot、网络/DNS、FRP 二进制及 systemd 启动，以及 SSH 认证方式。安装所需依赖尽量随介质准备，避免首启依赖联网下载才能恢复远程通道。

Ubuntu 官方 autoinstall 提供网络与 SSH 配置，以及安装完成前的 late-commands，可用于设置目标系统远程接入；error-commands 仅在安装环境能运行时提供处理机会，不能替代独立救援。

来源：[Ubuntu 自动安装参考](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html)。

Tailscale 无人值守重新注册可以使用 auth key，但本机当前登录已失效，不能直接复制失效状态后宣称恢复；需要有效认证前置。配置所需的登录与访问授权必须在清盘前解决。

来源：[Tailscale Auth keys](https://tailscale.com/docs/features/access-control/auth-keys)、[Linux 无人值守运行](https://tailscale.com/docs/how-to/run-unattended)。

## 远程接入与恢复边界

两条现有软件通道均依赖同一主机成功启动与联网。当前只有一份根分区，清盘后旧系统及其中的回连服务消失。一次性 GRUB 启动项选择只能影响后续启动选择，不能让卡住的机器自行重启，也不能还原已擦除根分区。现有证据不足以建立重装失败后自动回到旧系统的路径。

因此可预置成功安装后的 Wi-Fi、SSH、FRP 自动启动，尚无法验收失败场景下完全无需现场处理。用户的最低约束仍未满足，不执行引导切换或清盘。此处停止源于已确认的启动、磁盘和单一网络依赖，用户对旧数据清理的授权保持有效。

## 完成标准与当前判定

| 验收项 | 当前状态 |
| --- | --- |
| 目标身份和既有连接来源 | PASS |
| 当前无线配置和凭据可恢复性 | PASS，仅旧系统只读核验 |
| 无人登录的 Wi-Fi 自动恢复 | 未验证，必须在目标系统实测 |
| 新系统重启后远程 SSH 实际连接 | 未验证 |
| 清盘失败后的无人值守恢复 | 缺失可验证路径 |
| 最新 Ubuntu 安装及旧业务清除 | 未执行 |

目前仅前检完成，整机重置未完成。未用包卸载代替全新安装，未触碰现有线路。
