# Hermes MoA 配置与真实验收

2026-11-17，Asia/Tokyo。用户授权gpt-6.1-sol最终决策，DeepSeek/Qwen提供参考，沿用原接口。辅助任务继续auto，Discord不接入。本批已部署并真实验收通过。

## 运行配置

| 角色 | provider / model | 接口与凭据 |
| --- | --- | --- |
| 汇总、回答和工具调用 | custom / gpt-6.1-sol | 既有HTTPS网关及HERMES_GATEWAY_API_KEY |
| 参考1 | custom:springmonkey-deepseek / deepseek-flash | 既有DeepSeek官方入口及HERMES_DEEPSEEK_API_KEY |
| 参考2 | custom / hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S | 既有HTTPS网关及HERMES_GATEWAY_API_KEY |

替换官方default预设示例。原生槽位只保存provider/model等字段，DeepSeek通过新增providers.springmonkey-deepseek命名项引用原key_env。三槽位实际解析的端点、协议与凭据均在内存中与原值比对。没有新建凭据或更改网关服务、账户、路由及认证。

预设enabled=true、fanout=user_turn，每轮两路参考各运行一次，后续GPT执行工具循环。reference_timeout=180秒，degraded_reference_policy=loud，参考失败会明确披露。privacy_filter=full，最终save_traces=false。辅助槽位保持auto；原先关闭的标题生成和后台审查保持关闭。

普通聊天默认仍为custom:gpt-6.1-sol，DeepSeek/Qwen可用性兜底保持。MoA是可选的已启用预设。单轮会商用：

~~~
/moa 需要多模型会商的任务内容
~~~

在模型选择器选择Mixture of Agents的default预设可用于整个当前会话。本批实际验收入口为：

~~~sh
sudo hermes-pilot chat --provider moa --model default --query "任务内容"
~~~

用法依据[官方MoA文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents)。GUI已实际查看：2 references · custom/gpt-6.1-sol，编辑器中两路参考正确，辅助栏11 tasks · all auto。官方UI源码未改，原手机窄屏问题继续保留。

## 真实验收

合成题目：3GiB内存上限，12项任务各400MiB、20秒，对比全部串行A和同时运行B。没有在主机真实启动这些负载。完整Hermes MoA运行69.360秒、退出0：

- DeepSeek真实返回：669输入tokens、1245输出tokens，参考正文1730字符。
- Qwen真实返回：691输入tokens、1346输出tokens，参考正文1460字符。
- 两路实际参考正文均在gpt-6.1-sol的聚合请求中，原生trace逐项匹配。
- 本轮只有一次参考fan-out。GPT执行两次write_file、两次read_file，无工具错误。
- 实际JSON为上限3072MiB，A峰值400MiB/240秒、可执行；B峰值4800MiB/20秒、超限，最终选择A。输出内容及下载SHA256核验通过。

第一次入口在推理前因gateway-backed路径拒绝--run-budget而exit2。删除该单次参数，保持原900秒任务配置和宿主wrapper，再执行此前未开始的请求。没有为该参数错误重复推理或放宽策略。

仅合成验收期间临时开启详细trace，结束已原子恢复false。原始记录留在CLI私有home的moa-traces，文件0600、home0700；Git只保存脱敏统计/哈希和合成输出。未来任务的详细trace保持关闭。

- [三槽位端点及原凭据匹配](evidence/hermes-moa-20261117/SLOT_RESOLUTION.json)
- [实际三路、参考注入及工具验收](evidence/hermes-moa-20261117/ACCEPTANCE.json)
- [JSON输出](evidence/hermes-moa-20261117/moa-acceptance-result.json)
- [中文说明](evidence/hermes-moa-20261117/moa-acceptance-summary.md)
- [实际管理页](evidence/hermes-moa-20261117/moa-configured.jpg)
- [最终配置及基础服务](evidence/hermes-moa-20261117/FINAL_STATE.json)

## 边界、安装记录与回滚

固定v0.23.1/3b421578及原r2镜像未变。配置仍为/srv/hermes-pilot/policy/config.yaml，UID10001/GID10000/0640，原生symlink保存保持。与原备份逐项比较，最终仅新增moa和providers.springmonkey-deepseek；其他用户设置均不变。

CLI仍1.5CPU/3GiB，Dashboard仍1CPU/1GiB，端口及镜像不变、无OOM。Wi-Fi connected，SSH/Tailscale/FRP active；Tailscale SSH实际连接正常。公网匿名config401、Nous gate有效。未新增Agent框架、账号、GPU或本地模型，Discord保持不接入。

本次证明一轮合成端到端通过，没有把它当成所有任务质量提升、长期稳定性或最大上下文基准。参考模型接收用户/助手文本；仅使用本次授权的三个接口，未接账号或公司数据。详细数据边界继续受工作区策略约束。

回滚仅删除当前moa及新增的providers.springmonkey-deepseek项，保留其他现行用户设置。配置前副本位于管理home的moa-before-b6.yaml，不得用它覆盖以后用户新增的其他设置。先结束进行中的MoA任务，再刷新自有运行时。70 Skills、远程入口、证书及工作区数据不在回滚删除范围。
