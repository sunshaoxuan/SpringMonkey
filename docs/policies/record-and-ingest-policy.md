# 记录与入库长期规则

## 适用范围
凡是已确认成立的非机密、非临时、可复用工作信息，都必须主动记录并推送到 SpringMonkey，包括：
- 新的运行配置说明
- 新的接入方式说明
- 新的任务域规则
- 新的 apply / verify / recover 流程
- 已验证可用的服务接入信息（不含机密）
- 重要故障根因与修复方法
- 以后复用价值高的运行经验

## 不得入库的内容
- 密码
- token
- OAuth access / refresh token
- API key 明文
- 私钥
- cookie
- 会话文件
- 临时日志
- 缓存
- 锁文件
- 一次性测试垃圾

## 默认落点
- 运行说明：docs/runtime-notes/
- 报告与复盘：docs/reports/
- 规则与流程：docs/policies/
- 机器可读配置：config/
- 工具脚本：scripts/

## 默认动作
当新增或更新了上述非机密工作成果时，必须自动完成：
1. 写入合适目录
2. git add
3. git commit
4. git push 到 bot/openclaw

## 完成标准
- 只写进文件，不算完成
- 只进入正确目录，不算完成
- 只有推到 bot/openclaw 并给出 commit hash，才算完成
