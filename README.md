# 超时空会夜机

> 基于 WebSocket 的异地同步观影桌面应用

当前分支为 **beta0.1.2**，包含暖白界面、个人中心、标题与小窗进度、外挂字幕管理、一体化房间，以及版本检查和远程更新。beta0.1.2 仅用于验证更新流程，没有功能改动。原标为 1.4.0 的稳定版已重新归为 **1.3.2**，保留在 [master](https://github.com/hxxztch/WatchingTogether/tree/master)。历史归档不覆盖。

左侧「房间」可以创建内置房间、通过邀请链接加入，或切回原服务器连接方式。房主退出解散房间；异地模式使用 Cloudflare 临时公共通道，无需自行部署服务器，但公共服务不保证可用性。创建期间显示可取消的加载动画，其他操作暂时锁定。

单客户端下载、构建、附件方案对比及已知验收边界见 [一体化方案与验收](一体化方案与验收.txt)。构建用 `python packaging/build_integrated.py build`；以下旧版独立服务端说明继续适用于原连接模式。

![Python](https://img.shields.io/badge/Python-3.8-blue)
![PySide6](https://img.shields.io/badge/PySide6-Qt6-green)
![WebSocket](https://img.shields.io/badge/WebSocket-Async-orange)
![mpv](https://img.shields.io/badge/mpv-libmpv-red)

---

## 简介

超时空会夜机是一款支持**异地同步观影**的桌面应用。创建或加入房间后，播放进度实时同步。支持本地视频文件播放，也支持使用url播放，支持直接粘贴bilibili视频地址。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 房间同步 | 创建/加入房间，播放进度实时同步 |
| 断线恢复 | 自动重连，60秒内恢复原房间身份和最新播放状态 |
| 连接状态 | 显示往返延迟，异常断线自动清理在线成员 |
| 播放控制 | 播放、暂停、进度条跳转、音量调节、全屏 |
| B站视频 | 直接粘贴视频网页链接播放，支持分P切换、画质切换 |
| B站登录 | 在应用内显示二维码，使用 bilibili APP 扫码确认登录，获取账号可用的清晰度 |
| 音轨切换 | 多音轨视频可自由切换音频轨道 |
| 弹幕聊天 | 边看边聊|
| 快捷键 | 空格暂停/播放（同步）、左右方向键快进快退（同步） |
| 多客户端 | 不限人数 |
| 配置保存 | 自动记住上次的服务器地址、昵称和 bilibili 登录状态 |

---

## 快速开始

注：已上传服务端和客户端的打包文件，可直接下载使用。仅需**一人**配置服务端，其他人下载客户端即可。

### 环境要求

- Python 3.8+
- [ngrok](https://ngrok.com/) 或其他内网穿透工具（服务端需要）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 客户端更新与自动发布

已知 beta0.1.2 的自动更新可能在等待旧客户端退出时失败。可以关闭旧客户端后，使用[独立更新修复助手](https://github.com/hxxztch/WatchingTogether/releases/tag/repair-beta0.1.4)安装已下载的匹配差异包，操作步骤见助手发行页。当前 beta0.1.4 完整客户端尚未重新打包纳入退出等待修复；助手独立提供，配置和个人表情保留。

便携版启动后检查同一 beta 通道的新版本。「设置 → 更新源」默认选择 **Gitee**，也可切换到 **GitHub**；选择自动保存到个人配置。两种来源分别读取各自的静态清单，失败时使用同一平台的 Releases API，不会自动切到另一平台。设置页可手动检查、查看差异文件和下载更新。发布页提供完整便携包 `betaX.Y.Z.zip`；压缩包仍只有一个顶层目录，里面是 EXE、`_internal` 和说明文件。新版同时提供从各旧 beta 版本升级的 `旧版-to-新版.delta.zip` 和对应 `.delta.json` 文件清单。便携版优先自动下载适用的差异包，用户点击「安装更新并重启」后才会替换文件；个人 `config.json`、`stickers` 和诊断日志均保留。若找不到适用的差异包，可下载完整 ZIP。源码运行时仅检查更新并提供完整便携包下载，不改动 Git 工作区。

Gitee 单个附件上限为 100MB，超限包会分成多个附件。客户端会自动逐段下载、合并并校验每段及整个 ZIP 的 SHA256；手动下载完整包时，把所有分段和发行页提供的 `merge-betaX.Y.Z.cmd` 放到同一目录运行，再解压得到的完整 ZIP。无需安装额外工具。

2026-10-23 修订的 beta0.1.1 修复了 GitHub Release 文件跳转导致的下载校验失败。此前下载的 beta0.1.1 包需要手动替换一次：解压发布页的新版完整 ZIP，关闭旧客户端后将旧 EXE 同目录的 `config.json` 复制到新 EXE 目录。修订版随后可用差异包升级到 beta0.1.2。

发布新 beta 时，先修改 `app/version.py` 中的 `CLIENT_VERSION`，提交并推送代码，再推送同名标签。[GitHub Actions](.github/workflows/release-beta.yml) 会在 Windows 上安装 `packaging/requirements-lock.txt`、构建并校验便携包、生成完整 ZIP 与差异包，创建 Release 后更新静态发布清单。无需手工打包或上传文件。只有标签名与代码版本一致时才会发布。

同步 Gitee：先把同一源码分支和标签推送到 `gitee` 远端，等待 GitHub Actions 成功，再运行 `python packaging/publish_gitee.py --tag betaX.Y.Z --assets-dir dist/gitee-betaX.Y.Z --from-github`。脚本从 GitHub 下载已校验的同一批完整包和差异包，按需要拆分，上传到 Gitee，并以匿名下载校验确认可用后更新 Gitee 的 `update-feed` 清单。令牌只从隐藏提示或发布机的 `GITEE_TOKEN` 环境变量读取；不写入源码、客户端或更新清单。

当前 Gitee 普通仓库不支持 LFS 上传，源码镜像保留 `libmpv` 的 LFS 指针；推送镜像时使用 `GIT_LFS_SKIP_PUSH=1`。从 Gitee 获取源码时可设置 `GIT_LFS_SKIP_SMUDGE=1` 后克隆，再将已下载便携包中的 `_internal/libmpv/libmpv-2.dll` 复制到源码的 `libmpv/libmpv-2.dll`。便携客户端和差异更新均包含实际 DLL，不受源码镜像的 LFS 限制影响。

同版本修订会更新同名 Release 文件，但现有客户端只识别版本号更高的更新。已经安装该版本的用户需手动下载新的完整 ZIP；换目录安装时，请自行保留原目录的 `config.json` 与 `stickers`。

客户端把启动环境、关键操作、异常与更新脚本步骤写入 EXE 同目录的 `crash.log`（每文件 2 MB，保留 3 份历史）；Python 原生故障堆栈写入 `fatal.log`。目录不可写时，日志写入 `%LOCALAPPDATA%\WatchingTogether\logs`。日志不会自动上传，不记录昵称、房间邀请、聊天、媒体路径或账号 Cookie。反馈问题时可提供对应时间段的日志；分享前仍应检查日志中的异常堆栈是否含个人路径。

### 启动服务端

```bash
python server.py
```

同时启动 ngrok 穿透本地端口：

```bash
ngrok http 9877
```

ngrok 会提供一个公网地址（例如 `https://xxx.ngrok-free.dev`），将https改为wss即为服务器地址，将地址发给朋友。

### 配置客户端

启动客户端后，在界面左上角输入服务器地址（如 `wss://xxx.ngrok-free.dev`）和昵称，点击"连接"即可。

点击 B站登录后，使用 bilibili APP 扫描应用内二维码并确认登录。登录状态与连接设置保存在本地 `config.json` 中；该文件由程序自动保存，不纳入 Git 版本管理。

### 启动客户端

```bash
python client.py
```

### 稳定版客户端1.3.2 / 服务端1.2.0（原连接模式参考）

2026-10-15更新源码及构建文档，完整变更见[更新日志.txt](更新日志.txt)。本地便携包于2026-10-14构建；发行ZIP不纳入Git源码仓库，GitHub自动生成的源码ZIP不能直接作为便携程序运行。

稳定版用户完整解压对应ZIP，双击“超时空会夜机1.3.2.exe”或“server-1.2.0.exe”。beta0.1.2只需客户端包，内置房间服务。均需保留EXE旁的`_internal`文件夹；个人配置首次运行后自动生成，不随发行包提供。

由一人运行服务端，其他客户端填写`ws://服务端局域网或虚拟局域网IP:9877`。同机使用`ws://127.0.0.1:9877`。互联网访问仍需要网络可达性，便携包不自带VPN或公网穿透服务。

构建说明：使用Python 3.8 x64建立独立虚拟环境，安装`packaging/requirements-lock.txt`，然后执行：

```bash
python -m pip install pip==25.0.1
python -m pip install -r packaging/requirements-lock.txt
python packaging/build_release.py build
python packaging/verify_release.py
python packaging/build_release.py archive --output dist/archives
```

验证脚本将完整包复制到仓库外的临时目录，清除Python、Conda、Qt路径环境变量，直接运行EXE检查原生Qt、mpv、音量、时间跳转、两客户端联机和断线恢复。

### 联机稳定性与播放更新

稳定版1.3.2包含以下修复，beta0.1.2继续保留；已有的1.3.1 EXE和安装包不包含这些修改。

两人处于同一局域网或可互访的虚拟局域网时，由一人运行 `python server.py`。其他人在客户端填写 `ws://服务端的虚拟局域网IP:9877`，刷新连接后创建或加入房间；服务端电脑需允许 TCP 9877 入站。

- 短暂断网后自动重连并回房，离线会话保留60秒；主动离房不自动返回。服务端重启或会话过期后会提示重新创建或加入。
- 重连以服务端最新状态为准，不补发过期的播放、暂停和跳转指令。每2秒校准一次进度，小误差采用轻微调速，大误差或明确控制操作采用跳转。
- 聊天增加发送确认、补发和去重，最多保留32条待确认消息，60秒后停止补发并提示。回房时最多恢复最近100条聊天；这不是永久聊天记录。
- 各成员仍需自行打开相同视频。打开本地文件不会重置其他人的播放进度；更换影片后可用进度条统一跳转到开头。
- 本次增加的是连接恢复能力，不保证底层网络零丢包；自动发现房间和客户端内置服务端尚未加入。
- 点击“当前时间 / 视频时长”可输入秒数、`分:秒`、`时:分:秒`，回车跳转，Esc或失去焦点取消。非法时间、超出时长和未知时长会提示；房间内沿用同步跳转，暂停状态保持不变。
- 修正Windows文件选择框与mpv的斜杠差异，避免本地视频已播放却一直提示“等待加载”。左右方向键每次点按跳转5秒，长按产生的系统重复事件忽略；房间内由服务端统一计算并同步给在线成员，片头/片尾限制在视频范围内。聊天和时间编辑框中的方向键保持文本编辑用途。
- 点击喇叭切换静音，再次点击恢复最后一次非零音量；悬停调音浮窗不再拦截喇叭点击。加载视频前设置的音量也会保留。
- 扫码登录的生成、轮询、账号验证全部在后台执行，优先复用确认响应中的凭据，减少跨站请求。失败重试、二维码过期重新生成和取消都不会阻塞窗口。
- B站按清晰度ID选择真实视频流，修复WBI签名及切流音轨加载。下拉菜单只显示当前账号实际获得的视频流；切换保持进度和播放状态，解析在后台进行。登录后请重新打开视频刷新可用画质，清晰度仍受账号和视频权限限制。
- 2026-10-13 使用 `BV1mfay6pEti` 完成 4K→1080P→720P→360P 实际解码验证；未登录接口返回480P和360P。此结果仅代表该视频、当前账号及当次接口响应。

完整审查范围、测试结果和后续优化优先级见 [审查与测试报告.txt](审查与测试报告.txt)。

建议手动验证：两人连接并播放同一视频，短暂断网后恢复，检查身份是否重复、播放进度是否恢复、聊天是否重复；再测试主动离房、服务端重启和不同清晰度播放。

开发检查（在项目根目录执行）：

```bash
python -m unittest discover -s tests -v
python tests/gui_smoke.py
python tests/media_smoke.py
python tests/login_smoke.py
# 可选：联网验证指定B站视频，仅从个人配置读取登录状态
python tests/media_smoke.py --live-bilibili
```

界面检查使用临时配置、隐藏的 Qt 窗口和 mpv 空输出，验证真实客户端联机与媒体切换流程，不修改个人登录配置。联网媒体测试需要当前账号具备该视频4K权限；没有权限时会明确失败，不绕过平台限制。

## 项目结构

```
film-app/
├── server.py               # WebSocket 服务端：房间管理、播放同步广播
├── client.py               # 客户端入口
├── requirements.txt        # Python 依赖
├── build_client_1.3.1.spec  # 1.3.1 客户端 PyInstaller 打包配置
├── 更新日志.txt             # 版本更新记录
│
├── app/                    # 客户端核心模块
│   ├── player.py           # mpv 视频播放器封装及音视频切流
│   ├── bilibili.py         # B站 WBI 签名、请求与实际清晰度选择
│   ├── bili_login.py       # 可取消的扫码登录后台会话
│   ├── timecode.py         # 时间输入解析与格式化
│   ├── network.py          # WebSocket 网络通信层（异步收发、自动重连）
│   ├── sync.py             # 播放进度校准策略
│   ├── runtime.py          # Qt 插件及 DLL 路径初始化
│   ├── config.py           # JSON 配置持久化管理
│   │
│   └── ui/                 # PySide6 界面组件
│       ├── main_window.py  # 主窗口、布局、同步逻辑调度、B站登录
│       ├── controls.py     # 播放控制栏（进度条、音量、画质、音轨、分P）
│       ├── bili_login_dialog.py # 非阻塞扫码登录界面
│       ├── room_panel.py   # 房间面板（创建/加入、成员列表、昵称图片）
│       └── danmaku.py      # 弹幕浮层组件
│
├── libmpv/                 # libmpv-2.dll 运行时库
├── mpv_config/             # mpv 播放器配置（字体、input.conf）
├── assets/                 # 图标、图片等资源文件
└── screenshots/            # 界面截图
```

---

## 界面预览

### 首页
![首页](screenshots/film_homepage.png)

### 加入房间
![加入房间](screenshots/room2.png)

---

## 技术栈

| 技术 | 用途 |
|------|------|
| Python + asyncio | 异步服务端与客户端通信 |
| websockets | WebSocket 实时双向通信 |
| mpv + python-mpv | 高性能视频播放（GPU 硬解） |
| PySide6 (Qt6) | 跨平台桌面 UI 框架 |
| yt-dlp | B站视频链接解析与流媒体提取 |
| segno | 生成 B站登录二维码 |
| ngrok | 内网穿透，公网访问 |
| B站 API (WBI) | 在线视频清晰度列表与播放地址获取 |

---

## 第三方依赖

| 包 | 版本 | 说明 |
|------|------|------|
| PySide6 | >=6.0 | Qt6 界面框架 |
| python-mpv | >=1.0 | mpv Python 绑定 |
| websockets | >=13.1 | 异步 WebSocket |
| yt-dlp | 最新 | 视频链接解析 |
| segno | — | 登录二维码生成 |

---

## 作者

[@hxxztch](https://github.com/hxxztch)
