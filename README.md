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

字体为 Noto Serif CJK SC 界面文字子集，许可见 `web/public/font-license.txt`；其余文字回退到系统衬线字体。
