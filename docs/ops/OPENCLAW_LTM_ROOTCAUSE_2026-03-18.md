# OpenClaw 长记忆未入库排障记录

日期：2026-03-18

## 问题现象

- `memory-lancedb` 已启用
- `autoCapture=true`
- `autoRecall=true`
- 向量后端 `Ollama + bge-m3:latest` 已能正常返回 `1024` 维向量
- 但 `openclaw ltm stats` 长时间保持：
  - `Total memories: 0`

## 排查结论

根因不在向量链路，也不在 LanceDB 初始化，而在 `auto-capture` 的前置过滤规则。

### 1. Discord 用户消息被元数据包装

真实入站文本不是单纯的人类一句话，而是类似：

- `Conversation info (untrusted metadata): ...`
- `Sender (untrusted metadata): ...`
- 然后才是用户真正说的话

这会直接影响：

- 文本长度判断
- 触发词命中
- 分类判断

### 2. 原始触发词几乎不覆盖中文

当前版本 `memory-lancedb` 原始 `MEMORY_TRIGGERS` 主要是：

- 英文
- 捷克语

对中文这类重要设定消息几乎没有命中能力，例如：

- `你的名字叫：汤猴`
- `请把你的时间对齐为东京时间`

### 3. 最小长度门槛过高

原始 `shouldCapture()` 的最小长度门槛是：

- `10`

这会把短但关键的中文设定直接排除。

## 已应用修复

远端文件：

- `/usr/lib/node_modules/openclaw/extensions/memory-lancedb/index.ts`

已做修改：

1. 新增 `stripConversationMetadata()`
- 清掉 Discord 的 `Conversation info / Sender` 包装
- 清掉 `[[reply_to_current]]`
- 清掉开头的 mention

2. `before_agent_start` 先清洗 prompt
- 避免召回时把 Discord 包装文本直接拿去做 embedding

3. `agent_end` 的 auto-capture 先清洗用户文本
- 再进入 `shouldCapture()`

4. 扩展中文触发词
- `记住`
- `偏好`
- `以后`
- `默认`
- `统一`
- `改成`
- `对齐`
- `名字是`
- `名字叫`
- `东京时间`
- `JST`

5. 扩展中文分类规则
- `entity`
- `decision`
- `preference`
- `fact`

6. 调整长度限制
- 最小长度从 `10` 改为 `6`
- `captureMaxChars` 调整为 `2000`

## 显性验证

### 修复前

- `openclaw ltm stats`
  - `Total memories: 0`

### 修复后

- 已做一次受控回填
- 范围仅限当前 Discord 会话内满足规则的用户消息

回填命中的候选：

- `你的名字叫：汤猴`
- `对了，咱们对一下表，请你把你的时间对齐为东京时间。`

### 当前结果

- `openclaw ltm stats`
  - `Total memories: 2`

- `openclaw ltm search '东京时间' --limit 5`
  - 已命中：
    - `对了，咱们对一下表，请你把你的时间对齐为东京时间。`
    - `你的名字叫：汤猴`

## 当前结论

- 长记忆现在已经不是“启用但空转”
- `memory-lancedb` 已经可以真实入库
- 小模型向量化链路已参与实际记忆写入与检索
- 后续新的中文设定类消息，已具备进入 LanceDB 的条件
