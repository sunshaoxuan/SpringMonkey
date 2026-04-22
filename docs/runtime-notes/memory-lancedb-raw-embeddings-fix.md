# `memory-lancedb`：raw embeddings 修复

## 症状

宿主机日志持续出现：

- `memory-lancedb: recall failed`
- `No vector column found to match with the query vector dimension: 256`

而现有 LanceDB 表 `memories.vector` 的真实 schema 是：

- `FixedSizeList[1024]<Float32>`

这说明问题不在库表损坏，而在**查询侧 embeddings 维度漂移**。

## 根因

当前版本 `memory-lancedb` 插件默认通过内置 `OpenAI` SDK 调 `client.embeddings.create(...)`。

在本环境里：

- 真实 embedding 后端：`http://ccnode.briconbric.com:22545/v1`
- 模型：`bge-m3:latest`
- 真实返回维度：`1024`

但插件走 SDK 路径时，查询侧最终落成了 `256` 维向量，导致 LanceDB recall 报维度不匹配。

## 修复策略

对 `baseUrl` 场景强制改走**原始 HTTP**：

- `POST ${baseUrl}/embeddings`
- 直接读取 `data[0].embedding`
- 显式校验 `dimensions == 1024`

同时把运行时配置固化为：

- `plugins.entries.memory-lancedb.config.embedding.model = "bge-m3:latest"`
- `plugins.entries.memory-lancedb.config.embedding.baseUrl = "http://ccnode.briconbric.com:22545/v1"`
- `plugins.entries.memory-lancedb.config.embedding.dimensions = 1024`
- `plugins.entries.memory-lancedb.config.dbPath = "/var/lib/openclaw/.openclaw/memory/lancedb"`
- `plugins.entries.memory-lancedb.config.autoCapture = true`
- `plugins.entries.memory-lancedb.config.autoRecall = true`
- `plugins.entries.memory-lancedb.config.captureMaxChars = 2000`
- `plugins.slots.memory = "memory-lancedb"`

## 仓库入口

- 补丁脚本：
  - `scripts/openclaw/patch_memory_lancedb_raw_embeddings_current.py`
- 远程一键修复：
  - `scripts/remote_repair_memory_lancedb.py`
- 启动级自愈安装：
  - `scripts/remote_install_memory_lancedb_guard.py`
- 统一 CLI：
  - `python SpringMonkey/scripts/openclaw_remote_cli.py memory-repair`
  - `python SpringMonkey/scripts/openclaw_remote_cli.py memory-guard`

## 启动级自愈基线

为避免 OpenClaw 升级、重装或覆盖后把补丁静默抹掉，宿主机必须安装以下守护：

- systemd drop-in：
  - `/etc/systemd/system/openclaw.service.d/20-memory-lancedb-guard.conf`
- 启动前守护：
  - `/usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh`
- 启动后健康检查：
  - `/usr/local/lib/openclaw/check_memory_lancedb_dims.sh`

行为约束：

1. `ExecStartPre` 必须先重打补丁，并验证插件文件仍包含 raw HTTP `/v1/embeddings` 路径与维度校验逻辑。
2. `ExecStartPost` 必须实际请求 embeddings 接口，并确认返回维度为 `1024`。
   - 当前基线端点是 `http://ccnode.briconbric.com:22545/v1/embeddings`
   - 必须带短重试，避免瞬时断链把 service 误杀
3. 若补丁缺失或维度校验失败，`openclaw.service` 不应默默带病启动。

## 验证口径

修复后至少满足以下条件：

1. `POST /v1/embeddings` 实测返回 `1024` 维
2. `memory-lancedb` 日志不再出现 `query vector dimension: 256`
3. 日志出现：
   - `memory-lancedb: injecting ... memories into context`
4. 现有 LanceDB 表 schema 仍为：
   - `vector: FixedSizeList[1024]<Float32>`
5. `systemctl cat openclaw.service` 可见：
   - `ExecStartPre=/usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh`
   - `ExecStartPost=/usr/local/lib/openclaw/check_memory_lancedb_dims.sh`

## 保留说明

若未来 OpenClaw 升级覆盖 `/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js`：

- 正常情况下，启动级自愈会在下次 `openclaw.service` 启动前自动重打补丁。
- 若守护文件本身丢失，再执行：
  - `python SpringMonkey/scripts/openclaw_remote_cli.py memory-guard`

不要依赖默认 SDK 路径自动恢复，也不要只做一次性手工 patch。
