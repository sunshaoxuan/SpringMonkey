# SpringMonkey Hermes 使用入口

日常使用打开 [Hermes WebApp](https://smapp.briconbric.com)，用现有Nous账号登录。在Message框输入中文任务，按Enter发送。新会话模型应为 `gpt-6.1-sol`。原[管理控制台](https://sm.briconbric.com/chat?profile=default)保留。

WebApp的Bots栏中，右键Hermes，选择Open Screen可观看远端桌面。Take over接管鼠标和键盘，Hand back交回；人工持有控制权时Agent的浏览器及computer_use会被拒绝。桌面dock有Terminal和Browser入口，初次空桌面可先打开Browser。真实账号需在接管状态下自行登录，当前尚未接入邮箱或网盘账号。

可以直接输入：

> 帮我检索 Hermes Agent 的官方文档，整理适合初学者的功能说明，附来源链接，保存成 /workspace/Hermes入门.md。

默认模型为 gpt-6.1-sol。需要 DeepSeek、Qwen 同时给参考时，使用 `/moa 你的任务`。辅助任务保持自动选择，Discord 未接入。

WebApp的New session开始新任务，Sessions继续历史；右侧Files浏览成果，聊天中的文件卡片可预览和下载。`/workspace`对应SpringMonkey的`/srv/hermes-pilot/workspace`。已实测等待60秒期间关页后继续并产出文件；单次运行预算7200秒，进程崩溃后的外部操作恢复需按任务状态处理。

WebApp当前显示亮色界面，Open settings可调整界面。原Dashboard左下角调色盘可选主题，已保存 `Nous Blue`；Dashboard与WebApp的界面设置分别保存。

底部持续 `retrying` 表示聊天服务连接尚未成功；可把该状态反馈给管理员。管理页能够打开、模型名称显示正确，各自只能证明对应部分工作，完整聊天还需要成功收发一次消息。

此入口为可信单人管理员界面，管理操作与 CLI 的权限不同，勿向其他用户共享登录会话。当前仍有官方移动端布局限制，首次建议在电脑浏览器使用。

依据：[官方 Dashboard 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)，[MoA 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents)。
