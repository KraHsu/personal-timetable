# 课间 · 个人课表

[在线课表](https://timetable.krahsu.top) · [GitHub](https://github.com/KraHsu/personal-timetable)

个人使用的课表页面，参考个人博客的 Catppuccin 配色、中文衬线字体与留白。打开即可查看，编辑需要密码。手机默认日程，桌面默认周课表，可随时切换。

## 技术栈

- **前端：Vue 3 + Vite**，Composition API / 单文件组件，原生 CSS，无外部字体或 CDN。
- **后端：Rust + Axum + Tokio**，提供课表、登录、静态文件和健康检查接口。
- **存储：SQLite / rusqlite**，沿用原有数据库结构，历史记录保留最近 50 次修改。
- **部署：GitHub Actions → SSH → systemd + OpenResty HTTPS**。服务器运行 Rust 二进制和构建后的静态文件，无需安装 Node 或 Rust 工具链。

课程支持多个时段、周次范围、单双周、各时段独立地点、老师和备注。未排定时间的课程可以保留空时段列表；时间冲突会提示。支持学期设置、时区、JSON 导入导出、深浅主题，示例预览不会写入真实数据。

页面每分钟及回到前台时同步，编辑期间不覆盖表单；版本号防止不同设备互相覆盖修改。当前周和下一节课按照课表时区计算，不受查看设备所在地影响。默认 Asia/Shanghai；超出显示范围的课程会自动扩展时间轴。

## 本地开发

需要 Rust 1.97.1（CI 使用版本）、Node 24 和 C 编译器（编译内置 SQLite）。

```bash
npm ci
npm run build
TIMETABLE_PUBLIC="$PWD/dist" cargo run -- --port 8765
# http://127.0.0.1:8765
# 首次启动生成 data/admin-password.txt，权限 0600
```

开发 Vue 时，另开终端运行 `npm run dev`。Vite 将 `/api` 请求代理到本地 Rust 服务；后端需设置 `TIMETABLE_ORIGIN=http://localhost:5173`，并通过该地址打开前端。

环境变量：

| 变量 | 用途 |
| --- | --- |
| `TIMETABLE_DATA` | 数据目录，默认当前工作目录的 `data/` |
| `TIMETABLE_PUBLIC` | 静态文件目录，默认二进制旁的 `public/` |
| `TIMETABLE_ORIGIN` | 页面访问来源，生产设为 `https://timetable.krahsu.top` |
| `TIMETABLE_REVISION` | 可选版本号，默认读取二进制旁的 `REVISION` |

生产 Cookie 使用 Secure / HttpOnly / SameSite=Strict；密码采用 PBKDF2-SHA256（600000 次），登录有频率限制。Rust 兼容原 Python 版本的 `auth.json` 和登录 Cookie，升级不重置密码。

## 使用

点击「学期设置」，输入编辑密码，配置第一周的周一和学期周数，然后添加课程。周次可写 `1-16`、`1-16单`、`2-16双`、`1-8,10,12-16`。每个时段独立配置时间、星期、周次和地点，地点留空则沿用课程地点。

页头和课程详情提供「校园地图」入口，可放大、拖动查看北京理工大学中关村校区地图，也可打开原始 PDF。地图无需编辑登录，打开时才加载图片；地图资源与应用一起同源托管。

时间待定的课程可移除所有时段，仍在「我的课程」显示。备注中的 http/https 链接可以点击。JSON 导入会替换整份课表，导入前可以先导出备份。

## 推送自动部署

向 `main` 推送后，GitHub Actions 自动：

1. 检查 Rust 格式和 Clippy，运行课表逻辑、Vue 交互、Rust 单元、HTTP 兼容性和部署回滚测试。
2. 在 Ubuntu 24.04 构建 Rust 发布二进制和 Vue 静态文件，打包 `timetable-server`、`public/` 和 `REVISION`。
3. 使用独立部署密钥，经 SSH 22222 端口传到 rain；接收器校验路径、文件类型、二进制格式、大小和提交号。
4. 使用 SQLite backup API 备份数据，原子切换 `current`，重启服务。健康检查失败则切回上一版。
5. 验证公网 HTTPS 返回本次提交号及 `backend: rust`。

PR 只测试，不部署；Actions 也支持手动运行。部署串行执行，不被后续推送中断。Secrets 为 `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_KEY`、`DEPLOY_KNOWN_HOSTS`。部署密钥只能执行固定接收器，不能打开 shell 或转发端口。

**真实课表、数据库、编辑密码及 SSH 私钥不进入仓库或发布包。** `data/` 独立于发布目录。应用升级只需 push；`deploy/receive.py`、`timetable-launch` 和 systemd 配置是服务器基础设施，修改后需通过 SSH 上传 `deploy/` 并运行 `bash deploy/install-runtime.sh`。安装脚本适用于已有 `current` 的 rain 部署，先备份基础设施配置。

SSH 接收器仍使用系统 Python，负责解包、备份和回退；课表 HTTP 服务由 Rust 提供。启动器保留对旧 Python 发布目录的回退支持。

## rain 运维

- 程序：`/home/charles/apps/timetable/current/` → `releases/<commit>/`
- 数据：`/home/charles/apps/timetable/data/schedule.sqlite3`
- 编辑密码：`/home/charles/apps/timetable/data/admin-password.txt`（0600）
- 服务：`timetable.service`，监听 `127.0.0.1:8765`
- 域名配置：`/opt/1panel/www/conf.d/timetable.krahsu.top.conf`
- HTTPS 使用现有 `*.krahsu.top` 证书；程序版本保存在 `releases/`，数据备份在 `backups/`。

```bash
ssh rain 'sudo systemctl status timetable --no-pager'
ssh rain 'sudo journalctl -u timetable -n 50 --no-pager'
```

完整备份须使用 SQLite backup API（包含 WAL 已提交数据），并安全保存 `auth.json`；不要只复制正在运行的 `.sqlite3`。页面的 JSON 导出仅备份课表，不含密码。旧版本和备份按需通过 SSH 清理。

## 验证

```bash
npm ci
npm test
npm run build
npm run check
cargo test --locked
cargo build --release --locked
python3 -m unittest discover -s tests -p 'test_*.py'
```

HTTP 测试启动编译后的 Rust 程序，使用 Python 旧格式生成的临时数据库、密码和 Cookie，验证升级兼容、保存、重启、并发版本保护、访问限制及速率限制。测试不使用真实课表。

字体为同源托管的 Noto Serif SC 可变字体，使用 Unicode 范围按需加载分片，并包含上游完整的 30,928 个字符；不再按界面文案裁剪字形。许可见 `web/public/font-license.txt`。

## Server酱³ 提醒与事项

主页「事项与提醒」沿用现有编辑登录，事项内容只向已登录用户提供。可以开关课程提醒、添加作业/考试/其他事项，填写名称、可选的事项时间、最多 20 个独立提醒时间和备注，并编辑、完成、恢复或删除事项。所有时间均使用课表时区；提醒与事项截止时间可以任意分开设置。完成或停用事项后，所有后续提醒和失败重试都会停止。主页提供完整事项列表，默认显示全部事项，支持待办/已完成筛选、搜索、编辑和完成操作；退出登录后隐藏事项内容。旧版单次提醒自动兼容，已发送的提醒不会因升级再次发送。

每门课程首次开课的前一周周五默认 18:00 推送新课提醒，支持独立开关和在线修改周五提醒时间。首次日期取全部时段与有效周次中的最早日期，未排课的课程不推送。新课提醒允许 24 小时内补发。

课程默认在实际开课前 30 分钟推送，尊重学期、周次、单双周和独立教室。服务器每 30 秒检查一次，无需保持网页打开。正常情况下推送误差约 30 秒；网络失败使用退避重试。课程只在开课前补发，事项在提醒时间后的 24 小时内补发，超过窗口不再发送。SQLite 的 `notification_deliveries` 记录发送结果，重启不会重复发送成功的提醒；网络响应丢失等不确定故障仍可能重复送达。修改事项提醒时间会生成一次新提醒。

Server3 密钥存放在 root 专用的 `/etc/timetable-notify.env`：

```text
SERVERCHAN3_SENDKEY=你的Server3密钥
```

密钥不进入页面、API 或仓库。`timetable-notify.service` 以 charles 身份运行，systemd 读取此环境文件。提醒配置、事项和发送记录均在原 SQLite 数据库中，随现有部署的 SQLite backup 一起备份；课表 JSON 导出不包含事项。

首次上线时，先部署新应用以创建数据表，再上传 `deploy/` 并执行 `bash deploy/install-notifications.sh`。没有独立配置时，该脚本仅从 `/etc/cert-monitor.env` 复制 `SERVERCHAN3_SENDKEY`，权限为 0600。后续修改 worker 或 timer 时重新运行此安装脚本；普通应用自动部署保留提醒服务。

```bash
ssh rain 'systemctl status timetable-notify.timer --no-pager'
ssh rain 'sudo journalctl -u timetable-notify.service -n 30 --no-pager'
```

服务时区建议在配置事项前设定；修改课表时区后，已有事项的填写时间会按新时区解释。夏令时跳过的无效本地时间会跳过并记日志，重复的本地时间取第一次。

## 个人日程与任务依赖

登录后，主页的「个人日程」可以管理私有待办，并在清单视图与依赖图之间切换。在「管理清单与事项」中创建、重命名或删除清单；未分类的任务放在收集箱。新任务默认关闭提醒，只填写名称也可以保存，课程和已有事项的提醒规则不变。

编辑任务时可以选择所属清单和多个前置任务，允许跨清单依赖。图中箭头表示「前置任务 → 后续任务」，支持分支与汇合；点击节点可编辑，键盘可聚焦节点，宽图可横向滚动。按清单、状态或关键词筛选图时，仍会显示相关前置任务，并用虚线边框标记。

图视图支持直接操作：

- 点选节点，在画布旁编辑名称、清单、类型、时间、备注、前置任务及提醒，无需离开图视图；节点右上角可直接完成或恢复任务。
- 使用「添加任务」创建独立任务，或在节点上添加后续任务；侧栏支持添加前置任务，新任务和连线会一次保存。
- 点击「连接任务」，依次点选前置、后续节点，或从节点右侧的 `＋` 开始连线。重复连线、自连接和循环会被拒绝。
- 点选连线后移除依赖；删除任务时清理相关连线。节点和连线均可通过键盘选择。
- 支持缩放、适合画布、展开画布，以及在空白处拖动平移；手机使用触摸滚动，编辑区显示在画布下方。
- 编辑草稿保留打开时的版本号。后台同步不会覆盖草稿，发生并发冲突或保存失败时仍保留输入；切换回清单视图前会提示未保存修改。

- 未完成且所有直接前置任务已完成的任务显示「可开始」，否则显示「等待前置」。完成状态由用户手动调整，不强制锁定后续任务；依赖关系不改变定时提醒的发送规则。
- 前端禁用会造成循环的依赖选项，后端对整张图校验，拒绝自引用、缺失引用、重复依赖和任何循环（包括独立子图中的循环）。
- 删除任务同时移除所有引用它的连线；删除清单只把任务移回收集箱，保留任务及依赖。
- 最多 50 个清单、300 个任务。新字段为 `lists: [{id, name}]`、任务的 `listId` 和 `dependsOn`（前置任务 ID 数组）。旧数据缺失字段时自动按空清单、收集箱、无依赖处理。
- 清单、任务和依赖沿用 `/api/reminders` 的登录保护与版本冲突检查，存储在原 SQLite `reminders` JSON 中，随 SQLite 备份保存。课表 JSON 导出仍不包含这些私有数据。

本功能只涉及应用发布，无需更新提醒 worker 或 systemd 配置。回退旧应用前应先备份数据库：旧应用保存事项时可能丢弃它不认识的清单和依赖字段。
