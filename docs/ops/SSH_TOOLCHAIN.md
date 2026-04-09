# 远程操作 OpenClaw 主机：本机工具链（一次配置、反复使用）

目的：避免每次执行任务都重新「找 Python、再 `pip install paramiko`」。在**你用来跑脚本的 Windows 机器**上做一次环境固定，之后只调用同一解释器与同一依赖。

---

## 1. 固定一个 Python 解释器

在 PowerShell 中确认本机已安装 Python 3，并记下**完整路径**（示例，以你机器为准）：

```powershell
Get-Command python* | Format-List
# 常见路径示例：
# C:\Users\<你>\AppData\Local\Programs\Python\Python312\python.exe
```

**建议**：在「用户环境变量」里增加：

| 变量名 | 值 |
|--------|-----|
| `OPENCLAW_PYTHON` | 上述 `python.exe` 的完整路径 |

以后文档与脚本中的 `python` 均指 **`%OPENCLAW_PYTHON%`**，不再每次探测。

---

## 2. 一次安装依赖（不要每次装）

在仓库根目录执行**一次**：

```powershell
$py = $env:OPENCLAW_PYTHON   # 若未设，改成你的 python.exe 完整路径
& $py -m pip install -r SpringMonkey/scripts/requirements-ssh.txt
```

安装完成后，**无需**在脚本里再执行 `pip install`。

---

## 3. SSH 认证（不要写进仓库）

| 变量 | 含义 |
|------|------|
| `OPENCLAW_SSH_PASSWORD` 或 `SSH_ROOT_PASSWORD` | root SSH 密码（仅本机会话） |
| `OPENCLAW_SSH_PASSWORD_FILE` | 本机**绝对或相对路径**，文件内**单行**密码（不落盘到 Git 时可用） |

**本机文件（被 `.gitignore` 忽略，脚本仍会读取）**：若存在以下任一路径，远程脚本会在未设置上述环境变量时自动读取第一行：

- `SpringMonkey/secrets/openclaw_ssh_password.txt`
- `SpringMonkey/private/openclaw_ssh_password.txt`

说明：被 ignore 的目录在 Cursor 里**可能无法被 AI 索引或搜索**，属正常现象；运行时 Python 仍可从磁盘读取。统一逻辑见 `scripts/openclaw_ssh_password.py`。

可选：配置 **SSH 公钥** 登录 `root@ccnode.briconbric.com -p 8822`，脚本可改为密钥认证。

---

## 4. 统一调用示例

```powershell
$env:OPENCLAW_SSH_PASSWORD = '你的密码'
& $env:OPENCLAW_PYTHON "SpringMonkey\scripts\remote_diag_openclaw_webhook.py"
```

将 `remote_diag_openclaw_webhook.py` 换成其它 `SpringMonkey/scripts/remote_*.py` 即可。

---

## 5. 仓库内脚本约定

- `SpringMonkey/scripts/*.py`：远程 SSH 运维脚本，**仅 import** `paramiko`；若未安装，则报错并提示执行第 2 节，**不在**运行时自动 `pip install`。
- `SpringMonkey/scripts/requirements-ssh.txt`：SSH 脚本依赖清单。

---

## 6. PuTTY / plink

若已安装 **PuTTY**，可使用 `plink.exe` 做批处理 SSH；与 Python 二选一即可。将 `plink.exe` 路径加入 `PATH`，或在本文档记下固定路径。

---

## 7. 为何以前会「每次都下 Python」

- 部分脚本在 `import paramiko` 失败时**自动** `pip install`，看起来像「每次重装」。
- Cursor 终端有时 **PATH 里没有 `python`/`py`**，会误用 Microsoft Store 占位符。

按本文 **固定 `OPENCLAW_PYTHON` + 一次 `pip install -r requirements-ssh.txt`** 后，上述问题会消失。

---

## 参见

- `docs/CAPABILITY_INDEX.md` — 仓库内远程脚本、新闻流水线、OpenClaw 路径等**总索引**（做事前先查）。
- `docs/ops/TOOLS_REGISTRY.md` — **场景→工具**映射、参数约定、分裂与组合流水线。
- `scripts/openclaw_remote_cli.py` — 远程运维子命令统一入口（`list` / `diag` / `doctor` / `recover` 等）。
