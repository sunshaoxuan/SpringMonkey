## Ollama Embedding 测试报告

测试目标：`http://ccnode.briconbric.com:22545`

测试目的：确认该外网 Ollama 服务是否可作为 `memory-lancedb` 的 embedding 后端。

---

## 1. 基础连通性

测试接口：

- `GET /api/version`

结果：

- 可访问
- 返回版本：`0.11.7`
- 首次简单请求耗时：约 `432 ms`

结论：

- 服务在线
- 外网可达

---

## 2. 模型清单

测试接口：

- `GET /api/tags`
- `GET /v1/models`

结果：

当前可见模型：

- `bge-m3:latest`
- `qwen3:1.7b`
- `qwen3:8b-q4_K_M`

结论：

- `bge-m3:latest` 可作为 embedding 模型
- `qwen3:*` 更适合聊天，不适合作为长期记忆的主 embedding 模型
- `/v1/models` 正常工作，说明该服务具备 OpenAI 兼容访问能力

---

## 3. Embedding 接口测试

### 3.1 原生 Ollama 接口

测试接口：

- `POST /api/embed`

测试参数：

- `model = bge-m3:latest`
- `input = "hello world"`

结果：

- 成功返回 embedding
- 说明原生 embedding 接口正常

### 3.2 OpenAI 兼容接口

测试接口：

- `POST /v1/embeddings`

测试参数：

- `model = bge-m3:latest`
- `input = "hello world"`

结果：

- 成功返回 OpenAI 兼容格式
- 返回字段包含：
  - `object`
  - `data[0].embedding`
  - `model`
  - `usage.prompt_tokens`
- 向量维度：`1024`
- 本次响应耗时：约 `648 ms`

结论：

- 该服务不仅支持 Ollama 原生 embedding
- 也支持 OpenAI 兼容 `/v1/embeddings`
- 技术上适合作为 `memory-lancedb` 的 embedding 后端

---

## 4. 鉴权测试

测试方法：

- 对 `/v1/embeddings` 请求附加明显错误的 Bearer token

结果：

- 仍然返回 `200`
- 仍然成功返回 embedding

结论：

- 当前该外网 Ollama 入口未见有效鉴权
- 或至少该 embedding 接口不校验 Bearer token

风险说明：

- 任何可访问该地址的人都可能直接调用该服务
- 这属于明显的暴露面风险

---

## 5. 对 OpenClaw 的意义

这意味着可以采用如下架构：

- 主聊天模型：`gpt-5.5 Low`
- embedding 后端：`bge-m3:latest`
- embedding 服务：`http://ccnode.briconbric.com:22545/v1`
- 长期记忆存储：远程主机本地 `LanceDB`

预期数据落盘位置：

- 若以 `openclaw` 用户运行，典型路径预计为：
  - `/var/lib/openclaw/.openclaw/memory/lancedb`

---

## 6. 测试结论

可用性结论：

- 可以作为 `memory-lancedb` 的 embedding 后端

成本结论：

- 可以避免为 embedding 单独使用 OpenAI API

风险结论：

- 当前最大问题不是可用性，而是外网暴露且未见有效鉴权

---

## 7. 建议

1. 在正式接入 `memory-lancedb` 前，先明确是否接受该 Ollama 继续外网裸露
2. 如果不接受，应先做访问收口或鉴权
3. 收口完成后，再将 `memory-lancedb` 指向：
   - `baseUrl = http://ccnode.briconbric.com:22545/v1`
   - `model = bge-m3:latest`
4. 启用后再把：
   - 记忆数据库落盘位置
   - embedding 依赖
   - 风险边界
   补记到启动前检查清单
