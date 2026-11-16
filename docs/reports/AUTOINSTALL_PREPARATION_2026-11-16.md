# SpringMonkey 自动重装与远程恢复准备

主记录：[TASK_GUIDE.md](C:/workspace/codex-work/muse-selfhost-research-20261116/TASK_GUIDE.md)。目标：最新 Ubuntu 26.10 amd64，清除旧业务环境，Wi-Fi 无人登录自动联网，SSH 用户/密钥/防火墙可用，Tailscale 优先且 FRP 兜底。用户已授权必需验证全部通过后执行重置升级。当前仍为准备与验证阶段，未执行真机重启、清盘、启动项切换或 Ubuntu 升级。

## 已保留的现场

* Wi-Fi 系统级自动连接配置及凭据：远端受保护配置，本机加密配置包；未在普通文档打印 SSID/PSK。
* Tailscale 原设备：原先 NeedsLogin，管理页面重新认证成功后，本机 tailscale ssh 实际返回原主机名且退出码 0。认证后版本 1.104.7、Running/Online/RunSSH 均符合预期，身份快照读取稳定且 DPAPI 还原验证通过；旧失效快照另存，不作为可恢复性的有效依据。
* Discord 当前及旧配置路径中的连接、令牌、guild/channel/DM 策略和相关绑定：已保存远端受保护副本与本机 DPAPI 副本，哈希/还原一致。不采集消息历史、不发送消息、不自动接入未来 Harness。当前配置观测为一个 guild/频道条目，包含 DM 策略；配置并不能证明未来新 Harness 的通道隔离已经验收。
* 现有 FRP 0.61.0 服务与原操作系统保留。最新 FRP v0.72.0 仅在远端独立目录 staging，配置 verify 通过，未替换现有服务。

本机正式恢复目录：[recovery](C:/workspace/codex-work/muse-selfhost-research-20261116/recovery)。远端准备根目录为 `/srv/springmonkey-reset-prep-20261116`，仅 root 可访问。真实状态/密钥不进入 Git 和外部模型上下文。

## 固定输入与实现

* 官方 ISO：ubuntu-26.10-live-server-amd64.iso，SHA-256 `c8e9d797f718404bdb1e282f8466fe6f5f2e9f03c814bdf11b31326d45200929`；本机和远端整文件校验均通过。
* 目标官方镜像包含 Intel 无线固件。无线网卡实测 Intel AC 3168/iwlwifi；这项软件清单证据不等于目标内核中的实际关联成功。
* Netplan 经实际 Ubuntu 26.10 generator 验证，使用 NetworkManager，Wi-Fi 按永久 MAC 绑定，独立生成安装环境及目标配置。networkd 不支持此 Wi-Fi match 形式的实测失败已修正。
* SSH：独立 springadmin 密钥登录、禁止密码和 root OpenSSH 登录、密钥/目录权限、sudo、预先固定的主机公钥用于连接校验。
* 首启实测发现 cloud-init 重建主机密钥，已加入 ssh_deletekeys:false。旧 fixture 修复后固定密钥登录通过；更新后的完整候选还需首次启动验证。
* 新系统 first-boot gate：NetworkManager 连通、地址和路由正确，账户密钥权限检查，UFW 按连接接口及 tailscale0 允许 SSH，再启动恢复线路。
* 两条恢复线路独立重连，Tailscale 启动不依赖 FRP 服务端 TCP 可达。安装环境中的已确认 FRP 保持运行，供安装期间诊断。
* 同盘启动候选使用官方签名内核与 initrd、GRUB one-shot 和 toram。清盘前检查内存介质、释放旧 ISO loop/分区、目标盘独占访问以及剩余内存；此路径正在隔离磁盘验证。
* 安装前 gate：精确磁盘路径/字节数/序列号/GPT 身份、payload 校验、Secure Boot、生产无线链路与 FRP 目标可达性；需实际穿过安装环境 FRP 完成 SSH 确认才继续。
* Tailscale 恢复材料使用重新认证后的原身份，保持原 RunSSH/WantRunning；不将生产身份启动到隔离 VM。

源码：[scripts/reinstall](../../scripts/reinstall/README.md)。镜像和 schema 来源：[Ubuntu 下载](https://ubuntu.com/download/server)、[官方校验清单](https://releases.ubuntu.com/26.10/SHA256SUMS)、[autoinstall](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html)。FRP 来源为维护者官方 release，详情见本机脱敏 [manifest](C:/workspace/codex-work/muse-selfhost-research-20261116/LATEST_FRP_REMOTE_MANIFEST.json)。

## 当前验证状态

| 检查 | 状态 |
| --- | --- |
| 错盘、payload 篡改/越界、额外或非 SSH 代理负例 | PASS |
| 官方 schema、Netplan 生成、SSH 主机密钥配对、bootstrap 语法 | 当前候选 PASS |
| 本机 DPAPI 还原/破坏密文拒绝 | PASS |
| 远端现有及最新版 FRP 配置校验 | PASS |
| 当前原设备 Tailscale 实际 SSH 登录 | PASS |
| Discord 连接配置备份完整性 | PASS，重连未测试 |
| 基础隔离安装及新系统 FRP SSH | 安装后最小修复通过，完整更新候选待同盘验证 |
| 磁盘介质未复制到内存时阻止释放/清盘负例 | PASS |
| 同盘 GRUB one-shot、RAM 介质、完整重装与再次重启 | 进行中 |
| 最新 FRP、UFW、管理用户、root 拒绝及非 SSH 入站负例 | 待同一隔离系统的后续检查 |
| 真机 live Wi-Fi、Tailscale 身份恢复及清盘前 SSH 确认 | 未执行 |
| 真机重置升级及清盘后最终回连 | 未执行 |

所有必需项通过前，整机重置验收保持未通过。下载和安装仿真耗时不构成跳过网络/身份/防火墙检查的依据。单盘、无独立控制台的恢复限制仍存在，软件备份不能使卡住的固件自行重启。

## 本机 FRP 策略与清理限制

用户指出本机杀毒策略禁止 FRP 后，已停止本机 FRP 下载、复制、执行及在 WSL/Docker 中运行；加密恢复包已去掉 FRP 二进制，后续只记录远端 hash。顶层 frpc/frps 文件检查为不存在。旧 fixture/payload/frpc 的删除先被复合命令策略拦截，后以唯一实际存在的单文件缩小范围删除仍被策略拦截，未改安全设置或换工具绕过。该旧测试文件仍需由受管终端的正常安全流程处理，不能报告本机已全部清理。
