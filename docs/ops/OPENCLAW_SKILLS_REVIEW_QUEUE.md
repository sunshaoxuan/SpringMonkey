## OpenClaw Skills / Plugins 审查清单

目标：社区 skill 不直接安装到生产环境。先登记、再审查、再批准、再安装。

---

## 已落地的第 1 层

内置 / 受管能力：

- 已建立共享 skills 目录：`/var/lib/openclaw/.openclaw/skills`
- 已将共享目录加入 `skills.load.extraDirs`
- 当前优先使用 OpenClaw 自带 bundled skills 与内置工具
- 当前不自动引入任何第三方社区 skill

---

## 已落地的第 2 层

官方插件：

- 已启用：`discord`
- 已启用：`memory-lancedb`
- 已启用：`lobster`
- 已启用：`llm-task`
- 已启用但当前加载失败：`diffs`
- 已启用但当前加载失败：`diagnostics-otel`

当前远端配置实况：

- `diffs`
  - 用途：只读 diff / 文件渲染
  - 适合：代码审阅、补丁核对
  - 当前状态：配置中 `enabled=true`
  - 当前问题：缺少依赖 `@pierre/diffs`，运行时加载失败

- `diagnostics-otel`
  - 用途：把运行指标导出到 OpenTelemetry
  - 适合：你后面如果要接更正规的监控平台
  - 当前状态：配置中 `enabled=true`
  - 当前问题：缺少依赖 `@opentelemetry/exporter-logs-otlp-proto`，运行时加载失败

- `memory-lancedb`
  - 用途：增强长期记忆
  - 当前状态：已启用并接管 `memory` 槽位
  - 当前配置：
    - `autoCapture=true`
    - `autoRecall=true`
    - `dbPath=/var/lib/openclaw/.openclaw/memory/lancedb`
    - `embedding.baseUrl=http://ccnode.briconbric.com:22545/v1`
    - `embedding.model=bge-m3:latest`
    - `embedding.dimensions=1024`

- `lobster`
  - 用途：可恢复工作流与审批
  - 适合：以后想做更严格的人工批准链路
  - 当前状态：已启用

- `llm-task`
  - 用途：结构化 JSON 子任务
  - 风险：会增加自动化层级
  - 当前状态：已启用

---

## 第 3 层：社区 skill 待审队列

说明：下面不是“已批准列表”，而是“建议先考虑的方向”。  
真正安装前，你逐项确认，我再审源码、审权限、审依赖。

### 候选方向 A：Git / 代码仓库辅助

用途：
- 读仓库
- 生成变更摘要
- 帮助做 review

建议理由：
- 对 OpenClaw 作为运维/协作助手价值高
- 风险通常可控，前提是只给读权限或受限写权限

审查重点：
- 是否会执行任意 shell
- 是否会自动 push / release
- 是否依赖外部 token

状态：
- [ ] 待你指定具体 skill slug / repo

### 候选方向 B：知识库 / 文档同步

用途：
- 对接 Notion / 文档站 / 内部知识库
- 让 OpenClaw 在回答前拉取背景资料

建议理由：
- 对长期运维和多人协作很有用

审查重点：
- 是否读取超范围文档
- 是否带写权限
- 是否把敏感内容上传到第三方

状态：
- [ ] 待你指定具体 skill slug / repo

### 候选方向 C：运维观察与只读报表

用途：
- 汇总系统状态
- 读取日志
- 输出简报

建议理由：
- 跟你当前“先观察再放权”的策略一致

审查重点：
- 是否只读
- 是否会改系统配置
- 是否会清理日志或改变状态

状态：
- [ ] 待你指定具体 skill slug / repo

### 候选方向 D：对象存储 / 备份

用途：
- 把日志、快照、归档发到 S3 / NAS / WebDAV

建议理由：
- 能增强审计不可抵赖性

审查重点：
- 凭据保存方式
- 是否会覆盖已有备份
- 是否支持只追加或版本化

状态：
- [ ] 待你指定具体 skill slug / repo

### 候选方向 E：日程 / 通知

用途：
- 定时汇报
- 通知你某些事件

建议理由：
- 对日常管理方便，但不是第一优先级

审查重点：
- 是否会主动大量发消息
- 是否会误触发外部通知

状态：
- [ ] 待你指定具体 skill slug / repo

---

## 每个社区 skill 的审批模板

在批准前，至少补全以下项目：

- 名称：
- 来源：
  - GitHub 仓库 / ClawHub slug / 发布者
- 功能：
- 是否官方：
- 是否需要额外二进制：
- 是否需要额外 API key：
- 是否需要联网：
- 是否读本地文件：
- 是否写本地文件：
- 是否执行 shell：
- 是否可能修改系统状态：
- 是否涉及外部数据上传：
- 建议运行权限：
- 是否允许进入生产：
- 你的最终决定：

---

## 审批规则

- 不直接安装“热门榜” skill
- 不直接安装来源不明的 skill
- 不直接安装需要高权限的 skill
- 先审源码，再决定是否进入共享 skills 目录
- 安装后要补记到启动前清单

---

## 当前共享 Skills 目录实况

远端共享目录：

- `/var/lib/openclaw/.openclaw/skills`

当前已安装第三方 skills：

- `calendar`
- `git-essentials`
- `notion`
- `openclaw-backup`

对应 `SKILL.md` 已存在于：

- `/var/lib/openclaw/.openclaw/skills/calendar/SKILL.md`
- `/var/lib/openclaw/.openclaw/skills/git-essentials/SKILL.md`
- `/var/lib/openclaw/.openclaw/skills/notion/SKILL.md`
- `/var/lib/openclaw/.openclaw/skills/openclaw-backup/SKILL.md`
