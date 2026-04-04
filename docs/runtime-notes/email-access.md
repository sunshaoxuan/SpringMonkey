# SpringMonkey 专用邮箱接入说明

## 邮箱标识
- 地址：springmonkey@briconbric.com

> 凭据不写入仓库或公开工作文件；密码应单独保管与轮换。

## 已验证能力
- SMTP 提交通道：已验证可登录并成功发信
- IMAP 收信通道：已验证可登录并成功读到自发测试邮件
- 自发自收测试：通过

## 服务配置
- IMAP SSL
  - 主机：mail.briconbric.com
  - 端口：993
  - 安全：SSL/TLS
- IMAP STARTTLS（备选）
  - 主机：mail.briconbric.com
  - 端口：143
  - 安全：STARTTLS
- SMTP Submission
  - 主机：mail.briconbric.com
  - 端口：587
  - 安全：STARTTLS
- SMTPS（备选）
  - 主机：mail.briconbric.com
  - 端口：465
  - 安全：SSL/TLS
- MX
  - mail.briconbric.com

## 推荐访问方式
1. 收信：IMAP SSL 993
2. 发信：SMTP Submission 587 + STARTTLS
3. 用户名：完整邮箱地址

## 日常检查方法
- 先用 IMAP 查看收件箱是否有新邮件
- 注册平台账号后，优先检查验证邮件、重置邮件和风控邮件
- 若登录异常，先检查 IMAP/SMTP 是否仍可连，再检查密码是否已轮换

## 维护规则
- 不在公开频道、仓库或普通笔记里重复写明密码
- 若凭据曾在公开场合暴露，应尽快改密，并更新安全存储处
- 如新增平台账号，优先把“平台名 + 用途 + 是否已验证邮箱”记到安全运行笔记中
