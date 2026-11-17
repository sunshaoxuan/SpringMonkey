# SpringMonkey installed capabilities

Use ordinary language to request a task. Hermes should select relevant installed
skills automatically. For multi-model advice use /moa followed by the task:
DeepSeek and Qwen provide references, then gpt-6.1-sol answers and calls tools.
Normal chats and auxiliary auto routing continue to use the configured main model.
MoA is separate from the optional native workflow bundles below.

| Command | Workflow |
| --- | --- |
| `/research` | Public technical research, arXiv, RSS, citations and local knowledge notes |
| `/office` | PDF, DOCX, XLSX, PPTX, OCR and file conversion |
| `/analyst` | CSV/Excel exploration, statistics, charts and analysis validation |
| `/planner` | Requirements, decisions, roadmaps and sprint drafts |
| `/developer` | Plans, debugging, tests and completion evidence |
| `/reviewer` | Code changes, security-sensitive API review and review response |
| `/web-qa` | Browser testing, screenshots, console/network checks and web guidelines |
| `/writer` | Documents, status updates, editing and technical English |

The catalog contains 70 skills, including the original six. Bundles use Hermes'
native skill mechanism and run within the existing agent. Independent agent
frameworks, parallel delegation and private-service connectors are not configured.

Extended Python: `/opt/skills-python/bin/python`, also the default `python` on PATH.
It includes pandas, NumPy, SciPy, matplotlib, seaborn, Plotly, Playwright,
pytesseract, pygount, debugpy, pytest, Hypothesis and nbformat, plus the original
PDF and Office libraries. The sealed Hermes interpreter remains separate.

System tools: LibreOffice Writer/Calc/Impress, Poppler, Tesseract with English,
Japanese and Simplified Chinese, Pandoc, Graphviz, git, gh, jq and existing ffmpeg.
Playwright must launch the existing Chromium path from
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`; do not install another browser.

Write output and per-task temporary files under `/workspace`. Use an explicit
LibreOffice `-env:UserInstallation=file:///workspace/<task>/lo-profile` and
`--headless --convert-to ... --outdir ...`; clean up task server/browser processes.
Use real file rendering to check layout. Successful extraction or file creation
alone does not establish visual quality.

Public source reads and local user-approved files are available. Private GitHub,
email, calendars, trackers, publishing, infrastructure changes, and other account
operations require the corresponding user task and account setup. Discord stays
disconnected. No GPU model, paid image/audio service or recurring job is enabled.

Container ceilings remain CLI 1.5 CPU/3 GiB/512 pids and dashboard 1 CPU/1 GiB/256
pids. Run heavy conversions and browser sessions serially. These are trusted
single-user containers; skill text is not a security sandbox. The CLI and GUI chat
have different UIDs and resource ceilings. GUI chat workloads need their own
resource acceptance; this batch tests CLI workloads.
