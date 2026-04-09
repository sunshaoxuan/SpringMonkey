# TimesCar 入口探查基线（2026-04）

用途：避免 TimesCar 自动化把单一登录地址写死成唯一入口，导致网站升级后整条任务失效。

## 1. 设计目标

TimesCar 自动化需要同时满足两件事：

- 不要随意切到明显错误或无关域名
- 也不能把一个历史登录页当成永远不变的唯一真理

所以当前策略应为：

- 优先使用“已验证可用入口缓存”
- 缓存失效时，允许自主探查最新登录入口
- 探查成功后，把新入口写回缓存

## 2. 入口策略

### 2.1 首选缓存

宿主机应维护一个 TimesCar 入口候选缓存，按优先顺序尝试。

推荐至少包含：

1. `https://share.timescar.jp/view/member/mypage.jsp`
2. `https://share.timescar.jp/`
3. `https://timescar.jp/`

说明：

- `www.timescar.jp` 在当前宿主机环境里解析不稳定或不可解析，不应作为首选入口
- 但也不应简单地把“历史上不可用”变成永久禁止；应由缓存可用性与实时探查结果共同决定

### 2.2 探查触发条件

只有在以下情况之一时，才进入探查模式：

- 首选缓存入口连续失败
- 页面已不存在 / 明显改版
- 登录入口被重定向但未进入有效 member flow
- DNS / HTTP / browser 层提示缓存入口失效

### 2.3 探查方式

允许使用：

- browser
- web_fetch
- web_search

目标是找到“当前官方可登录入口”，而不是随意找一个看起来像 TimesCar 的页面。

探查时应优先验证：

- 官方域名是否仍属于 TimesCar
- 页面是否存在会员登录入口
- 进入后是否能到预约 / member / mypage 相关路径

## 3. 错误分类

这几类错误不能等同于“无预约”：

- DNS 解析失败
- 浏览器无法打开站点
- 登录入口失效
- 站点维护
- 站点改版导致入口选择失败

也就是说：

- `NO_REPLY` 只代表“成功进入预约列表后，确认未来 24 小时没有目标预约”
- 站点层失败应返回阻塞错误，而不是 `NO_REPLY`

## 4. 缓存更新原则

探查成功后，应把结果写入宿主机缓存，并保留：

- URL
- 来源方式（cached / discovered）
- 最后成功时间
- 备注（如 redirected-to-login / member-flow-ok）

建议缓存位置：

- `/var/lib/openclaw/.openclaw/workspace/state/timescar_entry_candidates.json`

## 5. 与 cron prompt 的关系

TimesCar 相关 cron prompt 不应再写成：

- “只能用某一个固定 URL”

而应写成：

- “先试缓存入口”
- “缓存失败则自主探查”
- “探查成功后更新缓存”
- “站点失败不等于 `NO_REPLY`”

## 6. 当前宿主机已知事实

2026-04-09 排查时确认：

- `www.timescar.jp` 在宿主机上解析失败
- `timescar.jp` 本体可解析
- 先前失败任务是因为 agent 自己幻觉成了 `https://www.timescar.jp/login`
- 宿主机上的 `TIMESCAR_AUTOMATION.md` 原先过于强调固定单入口，缺乏缓存与探查回退策略

## 7. 恢复建议

恢复 TimesCar 自动化时，至少要同时恢复这三层：

1. workspace 中的 `TIMESCAR_AUTOMATION.md`
2. 入口缓存文件
3. `timescar-*` cron prompt
## 2026-04-09 Stability Notes

- `timescar_secret.sh` must not rely on the caller's `HOME` when locating `timescar.key`.
- The host baseline key path is `/var/lib/openclaw/.openclaw/secrets/timescar.key`.
- `timescar_fetch_reservations.py` should use server-safe Chrome args. Avoid combining `--disable-gpu` with `--disable-software-rasterizer`, because that can crash headless Chrome before `new_context()` and surface as `TargetClosedError`.
