## OpenClaw 统一向量后端预配置

目标：为当前环境中的向量 / embedding 需求一次性确定统一后端，但在明确批准前不启用 `memory-lancedb` 接管默认记忆槽。

---

## 当前结论

当前已知需要向量模型的能力：

- `memory-lancedb`

当前不需要向量模型的能力：

- `memory-core`
- `discord`
- `lobster`
- `llm-task`
- `git-essentials`
- `notion`
- `openclaw-backup`
- `calendar`

---

## 统一向量后端

建议后端：

- 服务地址：`http://ccnode.briconbric.com:22545/v1`
- embedding 模型：`bge-m3:latest`
- 服务类型：Ollama OpenAI-compatible embeddings

原因：

- 已显性测试通过
- 支持 `/v1/embeddings`
- 可避免为 embeddings 单独使用 OpenAI API
- 与当前“主聊天走订阅，向量尽量自控”策略一致

---

## 预期落盘位置

若以后启用 `memory-lancedb`，本地向量数据库建议落盘到：

- `/var/lib/openclaw/.openclaw/memory/lancedb`

说明：

- 向量数据库在远程主机本地
- embedding 服务走远端 Ollama
- 记忆主数据不依赖 OpenAI 云端存储

---

## 预配置建议

建议预配置项：

- `embedding.baseUrl = http://ccnode.briconbric.com:22545/v1`
- `embedding.model = bge-m3:latest`
- `embedding.apiKey = <占位值，仅用于兼容 schema>`
- `dbPath = /var/lib/openclaw/.openclaw/memory/lancedb`
- `autoCapture = false`
- `autoRecall = false`

说明：

- 在真正启用前，先关闭 `autoCapture` / `autoRecall`
- 这样可以先把后端路线定住，但不让它开始自动写记忆

---

## 当前策略

- 已统一确定向量后端路线
- 预配置方案已形成文档
- 预配置已成功写入远端 `openclaw.json`
- 尚未让 `memory-lancedb` 接管默认记忆槽
- 尚未启动 OpenClaw
- 是否正式启用，仍以启动前复核和你的最终批准为准

---

## 风险点

- 当前外网 Ollama 暴露未见有效鉴权
- 若将其作为正式 embedding 后端，应优先考虑访问收口或鉴权
- 若链路波动，embedding 延迟会影响记忆写入 / 检索速度

---

## 后续启用步骤

1. 确认接受该向量后端方案
2. 确认是否需要先收口 Ollama 暴露面
3. 将 `memory-lancedb` 配置写入远端 OpenClaw
4. 决定是否让 `memory-lancedb` 接管默认记忆槽
5. 决定是否开启 `autoCapture`
6. 决定是否开启 `autoRecall`
7. 启动后做首轮记忆写入 / 召回测试
