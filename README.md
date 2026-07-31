# 超时空会夜机

> 基于 WebSocket 的异地同步观影桌面应用

![Python](https://img.shields.io/badge/Python-3.8-blue)
![PySide6](https://img.shields.io/badge/PySide6-Qt5-green)
![WebSocket](https://img.shields.io/badge/WebSocket-Async-orange)
![mpv](https://img.shields.io/badge/mpv-libmpv-red)

---

## 简介

超时空会夜机是一款支持**异地同步观影**的桌面应用。同一个房间后播放进度实时同步。支持本地视频文件播放，也支持直接粘贴 B站 视频链接在线观看。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 房间同步 | 创建/加入房间，播放进度实时同步，断线自动重连 |
| 播放控制 | 播放、暂停、拖拽进度条、音量调节、全屏 |
| B站视频 | 直接粘贴 BV 链接播放，支持分P切换、画质切换 |
| 音轨切换 | 多音轨视频可自由切换音频轨道 |
| 弹幕聊天 | 边看边聊，弹幕飘过屏幕 |
| 外挂字幕 | 拖入字幕文件到播放区域即可加载 |
| 快捷键 | 空格暂停/播放（同步）、左右方向键快进快退（同步） |
| 多客户端 | 不限人数|
| 配置保存 | 自动记住上次的服务器地址和昵称 |

---

## 快速开始

注：已上传服务端和客户端的打包文件，可直接下载使用。仅需**一人**配置服务端，其他人下载客户端即可。

### 环境要求

- Python 3.8+
- [ngrok](https://ngrok.com/) 或其他内网穿透工具（服务端需要）
### 安装依赖

```bash
pip install PySide6 python-mpv websockets
```

### 启动服务端

```bash
python server.py
```

同时启动 ngrok 穿透本地端口：

```bash
ngrok http 9877
```

ngrok 会提供一个公网地址（例如 `https://xxx.ngrok-free.dev`），将此地址发给朋友。

### 配置客户端

启动客户端后，在界面左上角输入服务器地址（如 `wss://xxx.ngrok-free.dev`）和昵称，点击"连接"即可。

或手动编辑 `config.json`：

```json
{
  "server": "wss://xxx.ngrok-free.dev",
  "nickname": "你的昵称"
}
```

### 启动客户端

```bash
python client.py
```

---

## 项目结构

```
WatchingTogether/
├── server.py               # WebSocket 服务端：房间管理、播放同步广播
├── client.py               # 客户端入口
├── config.json             # 客户端默认配置文件
├── requirements.txt        # Python 依赖
├── 更新日志.txt             # 版本更新记录
│
├── app/                    # 客户端核心模块
│   ├── player.py           # mpv 视频播放器封装（B站 URL 解析 + WBI 签名）
│   ├── network.py          # WebSocket 网络通信层（异步收发、自动重连）
│   ├── config.py           # JSON 配置持久化管理
│   │
│   └── ui/                 # PySide6 界面组件
│       ├── main_window.py  # 主窗口、布局、同步逻辑调度
│       ├── controls.py     # 播放控制栏（进度条、音量、画质、音轨、分P）
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
| Python + asyncio | 异步服务端与客户端 |
| websockets | WebSocket 实时双向通信 |
| mpv + python-mpv | 高性能视频播放（GPU 硬解） |
| PySide6 (Qt5) | 跨平台桌面 UI 框架 |
| ngrok | 内网穿透，公网访问 |
| B站 API (WBI) | 在线视频链接解析与播放 |

---

## 第三方依赖

| 包 | 版本 | 说明 |
|------|------|------|
| PySide6 | >=6.0 | Qt 界面框架 |
| python-mpv | >=1.0 | mpv Python 绑定 |
| websockets | >=10.0 | 异步 WebSocket |

---

## 作者

[@hxxztch](https://github.com/hxxztch)
