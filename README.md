# 家人券夹

给老人现场展示券码的轻量应用。Python 单文件后端、本地 JSON、一个 HTML 模板，无前端构建工具。

完整需求见 [docs/desing.md](docs/desing.md)。

## Docker Compose 部署

服务器需安装 Git、Docker 和 Docker Compose 2.24.4 或更新版本（本地覆盖配置使用 `!override`）。以下命令从项目目录执行，无需 `.env` 文件。

### 首次部署

```sh
git clone https://github.com/tianhe117/family-coupons.git
cd family-coupons
docker compose up -d --build coupons
docker compose ps
docker compose logs --tail=100 coupons
curl --fail http://127.0.0.1:8000/health
```

健康检查正常返回 `{"ok":true}`。默认端口映射为 `8000:8000`，不指定宿主机 IP，对所有网卡开放。网络及防火墙允许时，可通过服务器 IP 的8000端口访问。通过现有 HTTPS 反向代理转发到 `http://127.0.0.1:8000`，应用部署在域名根路径；代理在另一个容器中时需调整 Docker 网络连接。

镜像为 `family-coupons:1.0`，容器名为 `family-coupons`。镜像基于 `python:3.12-slim`，只复制并安装 `requirements.txt`，依赖安装在挂载目录之外。`.dockerignore` 仅允许构建必需文件进入上下文。Compose 将宿主项目目录挂载到 `/app`，Gunicorn 监听 `0.0.0.0:8000`。

首次初始化：老人密码为 **123456**，管理员密码为 **admin**。电脑访问域名后点击“管理”，用 `admin` 登录，在“密码设置”修改密码并添加券。手机管理入口为 `/?view=admin`。老人密码必须为6位数字，支持前导零；修改后的管理员密码至少8位。

默认密码仅在 `data/data.json` 不存在时使用，重启不会覆盖已有密码和券码。已有非六位老人密码需要先在管理界面修改为六位。数据保存在宿主项目的 `data/data.json`，目录必须可写，重建容器不会清空数据。定期备份 `data`；修复 JSON 前先停服务并备份，不在运行时手动编辑。

**固定使用一个容器、一个 Gunicorn worker。** 线程之间的读改写由锁串行化，不能增加副本或工作进程。JSON 先写同目录临时文件、刷盘再替换，写入失败不报告成功。

### 服务器本地配置

```sh
cp compose.override.example.yaml compose.override.yaml
```

按需修改 `compose.override.yaml`；示例将宿主机端口改为9090，同样对所有网卡开放。该文件已加入 `.gitignore`，不会随 `git pull` 被覆盖。不额外指定 `-f` 时 Compose 自动加载它。

```yaml
services:
  coupons:
    ports: !override
      - "9090:8000"
    environment:
      COOKIE_SECURE: "true"
```

`!override` 替换整个端口列表，避免默认8000与9090合并保留。默认 `COOKIE_SECURE: "true"` 用于 HTTPS。需要通过服务器 IP 直接以 HTTP 访问时，将 `COOKIE_SECURE` 改为 `"false"`，否则管理员登录 Cookie 无法正常使用；确保网络及防火墙允许访问。

```sh
# 校验共享配置和示例配置
docker compose -f compose.yaml config --quiet
docker compose -f compose.yaml -f compose.override.example.yaml config --quiet

# 检查实际本地配置并应用
docker compose config
docker compose up -d coupons
```

使用示例配置后，端口应只有9090到8000的映射，健康检查改为 `curl --fail http://127.0.0.1:9090/health`。只改端口或其他 Compose 配置时使用 `up -d coupons`，无需重建镜像；`restart` 不会应用新配置。

### 更新代码

仅修改 Python、模板或文档时：

```sh
git pull --ff-only
docker compose restart coupons
```

拉取后文件立即映射进容器，重启让 Python 进程加载最新代码，无需重建镜像。不要删除 `data` 目录。

修改依赖、基础镜像或 Dockerfile 后：

```sh
git pull --ff-only
docker compose up -d --build coupons
```

只修改 Compose 配置后：

```sh
git pull --ff-only
docker compose up -d coupons
```

从旧部署升级时，在原项目目录运行 `docker compose up -d --build coupons`，服务键仍为 `coupons`。新容器名固定为 `family-coupons`，升级前用 `docker ps -a` 确认没有其他项目占用该名称，并检查宿主机8000端口是否被其他容器占用。已有本地覆盖文件会继续生效，请检查最终端口绑定。重建保留宿主机 `data` 目录。

### 常用管理命令

```sh
docker compose stop coupons
docker compose start coupons
docker compose restart coupons
docker compose ps
docker compose logs -f --tail=100 coupons
```

日志查看时按 Ctrl+C 退出，不会停止服务。

## 手机使用

- iPhone Safari 打开 HTTPS 地址，分享 → 添加到主屏幕。
- 使用锁屏式大号数字键盘输入6位老人密码，满6位自动验证；删除键可退回一位，输错后清空重输。
- 按住按钮满3秒后弹出确认，点击“确定”才标记使用，点击“取消”继续展示原券；短按、移出按钮和切后台都取消。
- 用完一张后重新输入密码，才能查看下一张；后台返回和刷新也要重新输入。
- 网络结果不明确时只核实原操作，不直接展示下一张。

券码由服务器保管，手机不保存离线券码或使用下标。主屏幕模式、软键盘和系统长按菜单仍应在真实 iPhone 上验收。

## 电脑管理

支持单张添加、批量预览及整体导入、未使用券修改、误标恢复、使用历史和两类密码修改。老人密码不能调用管理接口。管理操作请避开现场验券时间；两台设备仍可能同时出示同一张尚未记录使用的券。

## 可选券码金额

单张添加和修改未使用券时可填写金额（元），留空不显示，清空已有金额可移除。仅支持非负整数，最多9位，不接受小数。老人展示页和管理列表仅在填写时显示金额。

批量添加兼容两列旧格式，也支持第三列金额；两种格式可以混合：

```text
001234567890 001234
009876543210 000456 100
001111222233 000789 88
```

任一行金额格式错误时整批拒绝导入。旧 JSON 无需迁移，没有 `amount` 的券照常使用。金额保存为整数字符串（例如 `"88"`），旧客户端修改请求未传金额时保留原值。已使用券继续保持不可编辑，误标恢复后可修改。

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

金额兼容说明：旧的 `100.00` 等整数值自动规范为 `100`；有非零小数的旧数据报错并保留原文件，不会自动取整。
