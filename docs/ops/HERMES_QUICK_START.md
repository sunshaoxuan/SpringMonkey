# SpringMonkey Hermes 使用入口

打开 [聊天页](https://sm.briconbric.com/chat?profile=default)，用现有 Nous 账号登录。在中间聊天区输入中文任务，按 Enter 发送。首次启动时等待底部显示 `ready`，右侧模型应为 `gpt-6.1-sol`。

可以直接输入：

> 帮我检索 Hermes Agent 的官方文档，整理适合初学者的功能说明，附来源链接，保存成 /workspace/Hermes入门.md。

默认模型为 gpt-6.1-sol。需要 DeepSeek、Qwen 同时给参考时，使用 `/moa 你的任务`。辅助任务保持自动选择，Discord 未接入。

右侧“新对话”开始新任务，右侧历史列表继续已有任务。左侧 Files 浏览生成的文件；聊天内的 `/workspace` 对应 SpringMonkey 的 `/srv/hermes-pilot/workspace`。

左下角调色盘打开主题选择。当前已保存官方 `Nous Blue` 亮色主题，也可选择其他内置主题。Dashboard 主题和终端内的配色属于不同显示层，当前终端使用浅色背景及金色强调文字。

底部持续 `retrying` 表示聊天服务连接尚未成功；可把该状态反馈给管理员。管理页能够打开、模型名称显示正确，各自只能证明对应部分工作，完整聊天还需要成功收发一次消息。

此入口为可信单人管理员界面，管理操作与 CLI 的权限不同，勿向其他用户共享登录会话。当前仍有官方移动端布局限制，首次建议在电脑浏览器使用。

依据：[官方 Dashboard 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)，[MoA 说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents)。
