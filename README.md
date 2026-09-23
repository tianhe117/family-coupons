# 家人券夹

给老人现场展示券码的轻量应用。Python 单文件后端、本地 JSON、一个 HTML 模板，无前端构建工具。

完整需求见 [docs/desing.md](docs/desing.md)。

## Docker Compose 部署

1. 复制配置文件：`cp .env.example .env`。
2. 在 `.env` 填写 `INITIAL_ACCESS_PASSWORD`（1–32位数字）和 `INITIAL_ADMIN_PASSWORD`（至少8位）。请不要提交 `.env`。
3. 执行 `docker compose up -d --build`。
4. 用服务器上的反向代理将 HTTPS 域名转发到 `http://127.0.0.1:8080`，应用部署在域名根路径。
5. 电脑访问域名，点击“管理”添加券；手机访问同一地址即可使用。手机管理入口为 `/?view=admin`。

`COOKIE_SECURE=true` 用于 HTTPS 部署。仅本机 HTTP 调试时改为 `false`。`PORT` 可以修改宿主机端口。若反向代理本身在另一个容器中，需要自行调整 Docker 网络连接，不能把其容器内的 `127.0.0.1` 当作宿主机。

初始化后，密码哈希和券码存于 `./data/data.json`。可移除 `.env` 中两个初始化密码，已有 JSON 不会被启动配置覆盖。数据丢失时若未提供初始化密码，应用会拒绝启动，不自动创建空券池。

数据目录必须可写。定期备份 `data`；重建容器不会清空挂载的数据。修复 JSON 前先停服务并备份，不在运行时手动编辑。

**固定使用一个容器、一个 Gunicorn worker。** 线程之间的读改写由锁串行化，不能增加副本或工作进程。JSON 先写同目录临时文件、刷盘再替换，写入失败不报告成功。

## 手机使用

- iPhone Safari 打开 HTTPS 地址，分享 → 添加到主屏幕。
- 输入老人密码，展示第一张未使用券。
- 按住按钮满3秒标记使用；短按、移出按钮和切后台都取消。
- 用完一张后重新输入密码，才能查看下一张；后台返回和刷新也要重新输入。
- 网络结果不明确时只核实原操作，不直接展示下一张。

券码由服务器保管，手机不保存离线券码或使用下标。主屏幕模式、软键盘和系统长按菜单仍应在真实 iPhone 上验收。

## 电脑管理

支持单张添加、批量预览及整体导入、未使用券修改、误标恢复、使用历史和两类密码修改。老人密码不能调用管理接口。管理操作请避开现场验券时间；两台设备仍可能同时出示同一张尚未记录使用的券。

## 本地开发和测试

需要 Python 3.12+：

```sh
python -m venv .venv
# 激活虚拟环境后
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

本地运行前设置 `INITIAL_ACCESS_PASSWORD`、`INITIAL_ADMIN_PASSWORD`、`COOKIE_SECURE=false` 环境变量，然后 `python app.py`，访问 `http://127.0.0.1:8080`。本地运行不会自动加载 `.env`；Compose 会读取它。

可选浏览器验收：安装或使用已有 Playwright，在一个终端运行 `python -m tests.serve_browser`，另一个依次运行 `node tests/browser.cjs`、`node tests/network.cjs`。第二个脚本继续使用第一个脚本留下的测试券池；重新执行全套测试时重启测试服务。可用 `PLAYWRIGHT_MODULE` 指向现有 Playwright 模块，`PLAYWRIGHT_EXECUTABLE_PATH` 指向现有 Chromium。测试服务使用临时 JSON，不接触生产数据；截图输出到忽略提交的 `test-results/`。这只是测试工具，不是应用运行依赖。

已在本地通过8项后端测试，以及 Chromium 的7种手机视口和网络异常验收。Docker 镜像构建及真实 iPhone 桌面模式尚需在对应环境验证。

## 文件

- `app.py`：接口、权限、JSON 读写、图标和 Manifest。
- `templates/index.html`：所有页面、样式和交互。
- `compose.yaml` / `Dockerfile`：服务器部署。
- `tests/`：权限、持久化、幂等、并发及浏览器验收。

框架部署参考：[Flask / Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/)。
