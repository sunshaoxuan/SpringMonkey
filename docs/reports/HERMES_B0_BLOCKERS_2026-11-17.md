# Hermes B0 三项阻塞补查

最新状态：用户已授权并完成首批Hermes部署，当前实施与验收以[2026-11-17部署报告](HERMES_DEPLOYMENT_2026-11-17.md)为准。本文后续为历史调查或规划，原暂不部署及预算阻塞已被更新。Discord保持未接入。

2026-11-17 最新纠正：用户最新要求取消费用预留及费用停止机制，该项不再构成B0阻塞。原接口已通过，拒绝终态本地补丁已验证；此文保留此前调查，预算相关前置已撤回。暂不部署、不接Discord。

后续获授权的本地实现见 [拒绝终态与USD10预算候选](HERMES_B0_POLICY_BUDGET_2026-11-17.md)。此前官方修复未找到的结论保持；现已另备固定版本地补丁和费用入口候选。模板因GPT/Qwen实际计价上界缺失继续阻断，B0 HOLD，本机候选不代表远端已应用。

日期：2026-11-17，Asia/Tokyo。采样约 01:34 至 01:42 JST。主选仍为 Hermes；本轮仅查询和更新计划，无部署、安装、推理、网关/网络修改或 Discord 接入。

## 1. 当前结论

| 原阻塞 | 本轮证据 | 当前判定 |
| --- | --- | --- |
| SpringMonkey 模型接口超时 | 旧私有目标不在主机 Wi-Fi 直连网段，无匹配 Tailscale 子网路由，TCP 超时；用户补充的公网 HTTPS 入口在主机上 TLS 和认证 GET 均通过 | 主机模型目录入口 PASS；旧私有路径保持不可达，计划采用已验证公网地址 |
| DeepSeek/Qwen 独立入口及额度 | DeepSeek 官方模型目录、余额 GET 通过；GPT/Qwen 按用户说明使用同一 Sub2API；网关用量及计费 GET 通过 | 具备一路独立 DeepSeek 候选；Qwen 与 GPT 共享入口和账面额度。试点独立硬预算、Qwen 上游额度及真实生成未验证 |
| Hermes 拒绝处理官方修复 | 最新稳定版仍 v0.23.1；当前 main 的拒绝 handler 仍尝试切换备用；对应可配置策略需求仍 open/needs-decision | 未查到满足既定拒绝终态要求的已发布官方修复，继续 HOLD |

本批只读调查与文档交付完成。B0 总体保持 HOLD，入口阻塞已关闭，剩余重点为拒绝终态、可执行费用停止机制和完整运行候选。真实模型能力、故障切换及资源测试留在未来获部署指令后的 B1。

## 2. 超时的原因及证据边界

之前实际测试链路为 Windows loopback → 已有 socat → 私有上游。Windows 对同一私有目标的 TCP 连接成功，路由使用 Ethernet 的直连 /24 网络；模型目录仍返回 41 个 ID。

SpringMonkey 的相同目标不在 wlp4s0 的直连网段，路由走 Wi-Fi 网关。Tailscale 的 RouteAll 为 false，table 52 无匹配目标路由；UFW active 且默认允许出站。相同上游 TCP 连接超时，发生在 TLS/HTTP/模型鉴权之前。主机同时能访问 DeepSeek 和 Qwen 公网 HTTPS 模型路径并收到匿名 401，公网 HTTPS 出站可用。

据此可定位为原私有入口缺少已验证的跨网访问路径。没有目标侧防火墙/路由器抓包或配置证据，不能进一步断言是哪台设备丢弃报文，也不能把单独开启 accept-routes 当成已验证修复。子网路由还依赖路由发布、批准和访问规则，见 [Tailscale 官方说明](https://tailscale.com/docs/features/subnet-routers)。实际 Tailscale SSH 读证成功；status 的单个 Self.Online 字段与本次访问不一致，不据此判定 SSH 离线。

用户随后明确 GPT 与 Qwen 的服务地址为 `https://ccnode.briconbric.com:49530`。这是本轮新证据，替代此前仅有 loopback/私有上游的入口信息。

| 检查 | Windows | SpringMonkey |
| --- | --- | --- |
| DNS | 公网地址，与旧私有目标不同 | 公网地址，与旧私有目标不同 |
| TLS | 默认 CA 与主机名校验通过 | 默认 CA 与主机名校验通过 |
| 匿名 GET `/v1/models` | 401 | 401 |
| 使用已有同服务凭据 GET `/v1/models` | 200，41 模型 | 200，41 模型，与 Windows 集合一致 |

新公网入口与旧私有转发目标的端口也不同。已确定部署候选 base URL 为 `https://ccnode.briconbric.com:49530/v1`，无需依赖 Windows loopback，不需要本次修改路由或新增 FRP/Tailscale 转发。模型目录成功只证明网络/TLS/认证及目录服务，生成、流式和工具调用尚未测试。

凭据通过加密 SSH stdin 进入远端 Python 进程内存，仅请求用户确认的同一 HTTPS 服务；未写远端文件、环境变量、命令行、Git 或普通日志。保持重定向拒绝与 TLS 校验，不读取 Discord 或 Codex OAuth 材料。

## 3. 实际三路入口和额度

| 路由 | 已核实入口与 model ID | 额度证据 | 限制 |
| --- | --- | --- | --- |
| GPT 主路 | `https://ccnode.briconbric.com:49530/v1`，`gpt-6-astra` | 同一 key 的 `/v1/usage` 返回 200、正的 USD 账面 balance/remaining；`/v1/sub2api/billing` 返回 200，billing_scope=token、effective_rate_multiplier=1 | 此为网关记账，不代表底层供应商现金余额、并发余量或每个模型可生成；试点专属上限未证明 |
| DeepSeek 独立备用 | `https://api.deepseek.com`，`deepseek-flash` | 既有直连配置对应 key 的 GET `/models` 与 `/user/balance` 均 200，is_available=true，余额超过计划 USD 10 样例预算 | 精确余额只保留本机证据；该余额供账户其他用途共享，未为 Hermes 预留或设独立费用上限；远端仅匿名网络验证，未传入此 key |
| Qwen 备用 | 与 GPT 同一公网入口，目录 ID 为 `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S` | 共享 key 账面额度可读，无 Qwen 上游独立余额/限额证据 | 不具有独立网关故障域。上游实际模型映射、工具/流式支持及容量待 B1；本轮不在 SpringMonkey 下载或运行 GGUF |

DeepSeek 的精确余额、币种和采样时间保存在本机 PROVIDER_ACCOUNT_CHECK.json，避免将账户财务数值同步进仓库。官方余额字段的含义见 [DeepSeek 余额 API](https://api-docs.deepseek.com/api/get-user-balance/)。GET `/models` 当前仅返回 `deepseek-flash`、`deepseek-v4-pro`；采用正式 Flash 名称。官方当前公布 Flash/Pro 账户并发上限为 2500/500，它是服务规则，不能视为本账户实时空闲容量，也不改变试点并发 1。[DeepSeek 模型说明](https://api-docs.deepseek.com/quick_start/pricing/)、[并发说明](https://api-docs.deepseek.com/quick_start/rate_limit/)

用户已说明 Qwen 的现有接入方式，本次不要求另开 Model Studio 账号。此前查阅的 Model Studio 地域 key、免费额度和预算规则仅适用于未来另选其官方服务，不能套用于本次 Sub2API 的 Qwen 路由。

共享服务根页面标题为 Sub2API。额度端点依据其 [官方路由](https://github.com/Wei-Shaw/sub2api/blob/main/backend/internal/server/routes/gateway.go) 和 [key 计费 handler](https://github.com/Wei-Shaw/sub2api/blob/main/backend/internal/handler/gateway_key_billing.go) 确认后查询，未尝试管理 API、登录、账户枚举或配置修改。账面值和汇总投影只保留本机；未保存返回中的身份字段。部署服务的完整版本与公开 main 是否一致未核实，当前只报告实际返回字段。

建议的有序链为 GPT 网关 → DeepSeek 官方 → Qwen 网关。网关故障时 DeepSeek 可提供独立候选；Qwen 仍会受同一网关故障影响，不能承诺三套独立基础设施。两处服务的生成预算分别计数，辅助调用和重试计入总量；实际配置、密钥分发和费用停止机制尚未实施。本机 Codex model_provider 保持 openai，现有 DeepSeek/Sub2API 配置均未更改。

## 4. 官方拒绝处理核查

截至本轮查询，[最新稳定发布](https://github.com/NousResearch/hermes-agent/releases/latest) 仍为 v0.23.1，commit `3b421578588243f920886e6fe79a6faa87ea026e`，2026-11-10T01:42:15Z 发布。沿用已固定候选，不拉取镜像或安装更新。

本轮 main 固定为 `43dc9a0a2848e8ddec2e57c578f49199cb0a8bba`，提交时间 2026-11-16T16:28:16Z：

1. [turn_truncation.py](https://github.com/NousResearch/hermes-agent/blob/43dc9a0a2848e8ddec2e57c578f49199cb0a8bba/agent/turn_truncation.py#L722) 的 `handle_content_policy_refusal` 仍在第 772 行调用 `_try_activate_fallback(reason=FailoverReason.content_policy_blocked)`。
2. [chat_completion_helpers.py](https://github.com/NousResearch/hermes-agent/blob/43dc9a0a2848e8ddec2e57c578f49199cb0a8bba/agent/chat_completion_helpers.py#L2034) 的 `try_activate_fallback` 继续沿候选链绑定可用路由；入口未见拒绝类别终态策略。
3. [fallback_cooldown.py](https://github.com/NousResearch/hermes-agent/blob/43dc9a0a2848e8ddec2e57c578f49199cb0a8bba/agent/fallback_cooldown.py) 的 switch_deferred_by_reset 仅对 rate-limit 类处理等待窗口，不能用于阻止内容拒绝切换。

这说明所查默认路径仍存在与本试点拒绝终态要求的差异；不推断所有协议、插件和配置下的完整运行行为。

[官方仓库 issue #97943](https://github.com/NousResearch/hermes-agent/issues/97943) 请求按分类错误配置 fallback/stop，含内容拒绝保持终态；当前 open、needs-decision、无评论，未有可用版本承诺。相关 [#82688](https://github.com/NousResearch/hermes-agent/issues/82688) 关于 should_fallback 与会话循环一致性的报告也仍 open/needs-decision。查询 #97943 的 PR 引用仅得到两个未合并的本地 llama.cpp watchdog PR，无法作为所需策略修复证据。

结论为未找到满足本试点要求的已发布官方修复。此行为具有现行产品设计依据，应作为策略适配项跟踪，不能仅等待普通错误修复说明。可接受路径为官方实现并验证分类停止策略，或另获授权后对固定候选做最小策略修改及覆盖性测试。本轮未改源码、未安装拒绝插件、未构造拒绝请求，不关闭全部故障兜底来替代策略验收。

## 5. 剩余条件及验证范围

| 条件 | 结果 |
| --- | --- |
| 远端安全入口、目录认证 | PASS，旧入口阻塞关闭 |
| 至少一路独立备用入口/凭据/余额 | DeepSeek 只读前置 PASS；远端认证生成未执行 |
| GPT/Qwen 网关账面额度 | PASS，可读正余额；上游模型余量和试点专属上限未证明 |
| 三路真实生成、协议、故障切换 | 未执行，保留未来 B1 |
| 可执行费用停止机制 | 未完成；正余额不能替代费用上限 |
| 拒绝保持终态 | 当前固定候选未通过，无已证实官方版本修复 |
| 整体 B0 | HOLD，暂不部署、不接 Discord |

正式证据见 [本轮目录](C:/workspace/codex-work/muse-selfhost-research-20261116/evidence/b0-blockers-20261117)：CONNECTIVITY_AND_CREDENTIAL_SCOPE、PUBLIC_ENTRY_CHECK、PROVIDER_ACCOUNT_CHECK、PUBLIC_QUOTA_SURFACE、GATEWAY_KEY_QUOTA、固定官方源码和 issue/release 查询。首次根路径 JSON 解析失败如实记录在指导文档，修正只读取 HTML 类型及标题，无额外管理端点探测。静态审查不能充当推理、资源或隔离验收。
