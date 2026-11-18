# SpringMonkey Hermes 使用入口

日常使用打开 [Hermes WebApp](https://smapp.briconbric.com)，用现有Nous账号登录。在Message框输入中文任务，按Enter发送。新会话使用你在模型设置中选择的聊天默认模型。原[管理控制台](https://sm.briconbric.com/chat?profile=default)保留。

WebApp的Bots栏中，右键Hermes，选择Open Screen可观看远端桌面。Take over接管鼠标和键盘，Hand back交回；人工持有控制权时Agent的浏览器及computer_use会被拒绝。桌面dock有Terminal和Browser入口，初次空桌面可先打开Browser。真实账号需在接管状态下自行登录，当前尚未接入邮箱或网盘账号。

可以直接输入：

> 帮我检索 Hermes Agent 的官方文档，整理适合初学者的功能说明，附来源链接，保存成 /workspace/Hermes入门.md。

需要 DeepSeek、Qwen 同时给参考时，使用 `/moa 你的任务`，最终判断和工具调用由 `gpt-6.1-sol` 负责。辅助任务保持自动选择，Discord 未接入。

WebApp的New session开始新任务，Sessions继续历史；右侧Files浏览成果，聊天中的文件卡片可预览和下载。`/workspace`对应SpringMonkey的`/srv/hermes-pilot/workspace`。已实测等待60秒期间关页后继续并产出文件；单次运行预算7200秒，进程崩溃后的外部操作恢复需按任务状态处理。

WebApp当前显示亮色界面，Open settings可调整界面。原Dashboard左下角调色盘可选主题，已保存 `Nous Blue`；Dashboard与WebApp的界面设置分别保存。

底部持续 `retrying` 表示聊天服务连接尚未成功；可把该状态反馈给管理员。管理页能够打开、模型名称显示正确，各自只能证明对应部分工作，完整聊天还需要成功收发一次消息。

此入口为可信单人管理员界面，管理操作与 CLI 的权限不同，勿向其他用户共享登录会话。当前仍有官方移动端布局限制，首次建议在电脑浏览器使用。

依据：[官方 Dashboard 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)，[MoA 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents)。

## 后台模型

在新会话中说「把 SteamWorks 报表交给后台查」，Hermes 可以通过原生委派选择日常路由。例行报表、查询和整理默认使用 `routine` 对应的 `gpt-6.1-terra`。需要后台做复杂分析时，可以说「把这个复杂分析交给 Sol」，让 Hermes 选 `complex`。聊天会话自己调用工具时仍使用该会话的模型。已经打开的旧会话可新建会话来加载新的委派工具定义。

未单独指定模型的 Hermes 原生定时任务跟随 `cron.model`，当前为 Terra。需要用 Sol 的定时任务可在该任务上单独指定模型。路由变更本身不创建计划任务。

官方 Advanced Delegation 使用 [审核过的固定提交](https://github.com/NousResearch/hermes-official-plugins/tree/13b2c1c9c8204bf333df240b2aacf98c3e6250b7/advanced-delegation)。部署路径为 `/srv/hermes-pilot/data/plugins/advanced-delegation`，配置见仓库的 `pilot-config.json`。两个路由复用现有兼容网关及其环境变量。模型、鉴权和 MoA 配置各自独立。

回滚时，从 `/srv/hermes-pilot/background-routing-rollback/config.yaml` 恢复本次涉及的委派、插件启用、命名供应商、工具集和 cron 模型字段，然后通过 Hermes 控制套接字重新加载插件。只恢复本次变更的字段可保留后来用户对聊天默认值的调整。

部署验收确认 Hermes 在热加载后发现官方插件。`delegate_task` 省略路由时返回 `model_map/routine`，SteamWorks 报表由 Terra 子会话真实读取，五个指定数值和页面一致。Sol 复杂路由与 Terra 定时任务路由已用原生解析器核对；本次只有报表委派实际调用模型。安装依据为用户要求独立配置后台路由，聊天和 MoA 模型字段保留原值。
