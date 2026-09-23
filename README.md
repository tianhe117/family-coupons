# 家人券夹

给老人现场展示券码的轻量应用。Python 单文件后端、本地 JSON、一个 HTML 模板，无前端构建工具。

完整需求见 [docs/desing.md](docs/desing.md)。

## Docker Compose 部署

1. 执行 `docker compose up -d --build`，不需要 `.env` 文件。
2. 用服务器上的反向代理将 HTTPS 域名转发到 `http://127.0.0.1:8080`，应用部署在域名根路径。
3. 首次初始化：老人密码（ACCESS_PASSWORD）为 **123456**，管理员密码（ADMIN_PASSWORD）为 **admin**。
4. 电脑点击“管理”，用 `admin` 登录后在“密码设置”修改密码并添加券。手机管理入口为 `/?view=admin`。

老人密码必须为6位数字，支持前导零；修改后的管理员密码至少8位。默认密码仅在 `data/data.json` 不存在时使用，重启不会覆盖已有密码和券码。已有非六位老人密码需要先在管理界面修改为六位。

端口和 `COOKIE_SECURE` 直接在 `compose.yaml` 修改。默认 `COOKIE_SECURE: "true"` 用于 HTTPS；仅本机 HTTP 调试时改为 `"false"`。若反向代理在另一个容器中，需要调整 Docker 网络连接。

数据目录必须可写。定期备份 `data`；重建容器不会清空挂载的数据。修复 JSON 前先停服务并备份，不在运行时手动编辑。

**固定使用一个容器、一个 Gunicorn worker。** 线程之间的读改写由锁串行化，不能增加副本或工作进程。JSON 先写同目录临时文件、刷盘再替换，写入失败不报告成功。

## 更新代码

镜像只安装 Python 依赖，不复制项目文件。Compose 将当前项目目录整体挂载到容器 `/app`，券码数据仍在宿主机项目的 `data/data.json`。

首次切换到这个挂载配置时，执行一次 `docker compose up -d --build --force-recreate`，让现有容器采用新挂载。以后只修改 Python、模板或文档时：

```sh
docker compose stop
git pull --ff-only
docker compose start
```

`start` 会重新启动 Python 进程，读取挂载目录中的最新代码。不要在更新代码时删除 `data` 目录。

如果更新涉及 `requirements.txt` 或 `Dockerfile`，执行 `docker compose up -d --build` 重新构建并创建容器；如果只修改 `compose.yaml`，执行 `docker compose up -d` 应用配置。`stop/start` 不会重新安装依赖或应用容器配置变化。

构建使用 Docker BuildKit 临时挂载 `requirements.txt` 安装依赖，Dockerfile 中没有 `COPY` 指令。需要支持 BuildKit 的 Docker 与 Compose v2。

## 手机使用

- iPhone Safari 打开 HTTPS 地址，分享 → 添加到主屏幕。
- 使用锁屏式大号数字键盘输入6位老人密码，满6位自动验证；删除键可退回一位，输错后清空重输。
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

本地运行前设置 `COOKIE_SECURE=false`，然后 `python app.py`，访问 `http://127.0.0.1:8080`。首次启动自动使用默认密码，无需密码环境变量。

可选浏览器验收：安装或使用已有 Playwright，在一个终端运行 `python -m tests.serve_browser`，另一个依次运行 `node tests/browser.cjs`、`node tests/network.cjs`。第二个脚本继续使用第一个脚本留下的测试券池；重新执行全套测试时重启测试服务。可用 `PLAYWRIGHT_MODULE` 指向现有 Playwright 模块，`PLAYWRIGHT_EXECUTABLE_PATH` 指向现有 Chromium。测试服务使用临时 JSON，不接触生产数据；截图输出到忽略提交的 `test-results/`。这只是测试工具，不是应用运行依赖。

已在本地通过9项后端测试，以及 Chromium 的7种手机视口和网络异常验收。Docker 镜像构建及真实 iPhone 桌面模式尚需在对应环境验证。

## 文件

- `app.py`：接口、权限、JSON 读写、图标和 Manifest。
- `templates/index.html`：所有页面、样式和交互。
- `compose.yaml` / `Dockerfile`：服务器部署。
- `tests/`：权限、持久化、幂等、并发及浏览器验收。

框架部署参考：[Flask / Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/)。
