# Ollama Endpoint Model Queue

时间：2026-04-09

## 目的

在同一个 Ollama 端点上，避免不同模型请求并发打进 `/api/chat` 导致频繁换模、首 token 过慢、任务超时。

当前汤猴的关键风险场景：

- LINE 定时任务
- Discord 会话聊天
- 新闻 worker / 其他依赖同一 Ollama 端点的请求

这些请求如果同时命中同一个 Ollama 端点，而模型名不同，就可能在服务端产生反复切模。

## 当前落地

宿主机已对 OpenClaw 运行时代码打补丁：

- 目标文件：`/usr/lib/node_modules/openclaw/dist/stream-DqNCFbiN.js`
- 备份：`/usr/lib/node_modules/openclaw/dist/stream-DqNCFbiN.js.bak-ollama-model-queue`
- 安装脚本：`SpringMonkey/scripts/remote_install_ollama_endpoint_queue.py`

## 行为

补丁在 Ollama `createOllamaStreamFn` 入口处增加了一层“按端点串行、同模型优先”的队列：

- 队列键：`chatUrl`
- 模型键：`model.id`
- 同一端点上任意时刻只放行一条实际 Ollama 请求
- 如果当前端点队列里仍有与当前模型相同的待执行请求，则优先继续清空同模型请求
- 如果当前模型没有待执行请求，再切到队列里更早进入的其他模型请求

这不是严格的 DAG 依赖调度器，但已经满足当前最核心的约束：

- 不让同一 Ollama 端点并发打多个模型
- 尽量减少不同模型之间的反复切换
- 维持“单链执行”语义

## 边界

- 该补丁不改变全局主模型策略
- 当前主模型是 `openai-codex/gpt-5.4`
- `ollama/qwen3:14b` 只作为候补
- 该补丁只影响 Ollama HTTP 调用排队，不改变 OpenClaw 的高层 channel / cron 路由

## 恢复

若 OpenClaw 升级覆盖了该文件，需要重新执行：

```powershell
python SpringMonkey/scripts/remote_install_ollama_endpoint_queue.py
```

然后在宿主机：

```bash
systemctl restart openclaw.service
```
