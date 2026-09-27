# 课间 · 个人课表

部署地址：https://timetable.krahsu.top

GitHub：https://github.com/KraHsu/personal-timetable

## 推送自动部署

向 `main` 推送后，GitHub Actions 自动执行：

1. Node 24 / Python 3.12 语法检查、课表逻辑测试、页面交互测试、服务测试和部署回滚测试。
2. 将 `server.py`、`public/` 和当前提交号打包，经 SSH 22222 端口传到 rain。
3. 验证发布包，在 `releases/<commit>/` 安装程序，并用 SQLite backup API 备份数据库。
4. 原子切换 `current` 链接、重启服务，检查 `/healthz` 返回的提交号以及课表读取接口；失败时切回上一版程序。
5. 从 GitHub runner 验证公网 HTTPS 正在提供本次提交。

PR 只运行测试，不部署。也可以在 Actions 页面手动运行 `Test and deploy timetable`。部署串行执行，不会被后续推送中途取消。

```bash
git add <修改的文件>
git commit -m "Describe the change"
git push origin main
```

仓库 Secrets：`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_KEY`、`DEPLOY_KNOWN_HOSTS`。课表使用独立的部署密钥；服务器将该密钥限制为固定接收器，只接受 `deploy <commit>` 和约定的应用文件，不能打开 SSH shell 或转发端口。主机指纹通过已信任的 rain SSH 连接读取后固定，CI 不临时信任 `ssh-keyscan` 结果。

真实课表、数据库、编辑密码、SSH 私钥均不进入仓库或发布包。服务器 `data/` 独立于版本目录；部署备份在 `backups/`，旧程序在 `releases/`。当前规模很小，旧版本和备份保留，按需通过 SSH 清理。

`deploy/receive.py` 是一次性安装到 `/usr/local/libexec/timetable-receive.py` 的服务器接收器。修改接收器、systemd 或 Nginx 配置后需通过 SSH 更新；普通页面和服务代码改动只需 push。初始化脚本为 `deploy/bootstrap.sh`，仅用于从原来的平铺部署迁移，不要重复运行。

参考个人博客的 Catppuccin 配色、中文衬线字体与留白。手机默认日程，桌面默认周课表，可随时切换。支持学期起始周一、1–60 周、时区、周次范围、单双周、多个上课时段、课程地点/老师/备注、冲突提醒、JSON 导入导出和深浅主题。示例预览不会写入真实数据。

查看公开，编辑需要密码。Python 3.12 标准库服务 + SQLite，无运行时第三方依赖，无外部字体/CDN。配置与课程存储在服务器，页面每分钟及回到前台时同步；编辑期间不会自动覆盖表单。并发保存通过版本号阻止互相覆盖。历史记录保留最近 50 次修改。

## 使用

打开页面，点击「学期设置」，输入编辑密码，配置开学第一周的周一和学期周数，然后添加课程。周次可写 `1-16`、`1-16单`、`2-16双`、`1-8,10,12-16`。同一门课程不同日期、时间或周次，通过「添加时段」分别配置。备注中的 http/https 链接可以点击。

每个时段可单独指定地点，留空时沿用课程地点，支持部分周次改为线上或换教室。尚未排定时间的课程可移除所有时段后保存，保留在「我的课程」并标注时间待定；不会生成虚构的日程。

默认时间为 Asia/Shanghai，不受查看设备所在地影响。选课表显示范围以外的课程会自动扩展时间轴。日期转换使用 UTC 日期计算，避免夏令时影响周次。

## 本地启动

```bash
python3 server.py
# http://127.0.0.1:8765
# 首次启动生成 data/admin-password.txt，权限 0600
```

生产环境通过 `TIMETABLE_ORIGIN` 设置外部 HTTPS 域名，Cookie 使用 Secure/HttpOnly/SameSite=Strict；密码以 PBKDF2-SHA256（600000 次）保存，连续登录尝试有频率限制。

## rain 部署

- 当前程序：`/home/charles/apps/timetable/current/`，指向 `releases/<commit>/`
- 数据：`/home/charles/apps/timetable/data/schedule.sqlite3`
- 编辑密码：`/home/charles/apps/timetable/data/admin-password.txt`（0600，仅 SSH 可读）
- 服务：`timetable.service`，仅监听 `127.0.0.1:8765`
- 独立域名配置：`/opt/1panel/www/conf.d/timetable.krahsu.top.conf`
- HTTPS 使用现有 `*.krahsu.top` 通配符证书，直接引用博客证书的更新路径。

```bash
ssh rain 'sudo systemctl status timetable --no-pager'
ssh rain 'sudo journalctl -u timetable -n 50 --no-pager'
ssh rain 'cat ~/apps/timetable/data/admin-password.txt'
```

备份优先用页面「学期设置 → 导出 JSON」。完整备份须使用 SQLite backup API（包含 WAL 中已提交内容），同时安全保存 `auth.json`。不要只复制正在运行中的 `.sqlite3` 文件。`history` 表可用于恢复最近的误操作；恢复前先备份当前数据。

需要停用：停止 `timetable.service`，移走独立域名配置后检查并 reload OpenResty；数据目录可保留。该服务不修改博客程序和课表数据以外的业务文件。

## 验证

```bash
node tests/core.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
# jsdom 仅为开发测试依赖，不部署到服务器。
npm ci --ignore-scripts
npm test
npm run check
```

字体为 Noto Serif CJK SC 的界面文字子集（181 KB），完整许可见 `public/font-license.txt`；其余文字回退到系统衬线字体。
