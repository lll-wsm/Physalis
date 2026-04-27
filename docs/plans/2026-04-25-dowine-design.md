# Physalis - 跨平台视频下载工具设计文档

## 概述

将 macOS 独占软件 Downie 的核心体验移植到 Linux 和 Windows 平台。采用 PyQt6 + QWebEngineView 构建桌面端，yt-dlp 作为下载引擎，内置浏览器实现站点登录和视频嗅探。

## 目标

- 跨平台：Windows / Linux（macOS 可选）
- 通用视频下载：支持 YouTube、Bilibili、抖音等 1000+ 站点
- 内置浏览器：独立窗口打开站点，登录后嗅探视频
- 简洁交互：粘贴链接 / 拖放 / 浏览器嗅探，三种方式触发下载

## 整体架构

```
┌──────────────────────────────────────────────────────┐
│                    主窗口                              │
│  ┌────────────────────────┐  ┌─────────────────────┐ │
│  │  链接输入栏 (拖放/粘贴) │  │  嗅探到的视频列表    │ │
│  └────────────────────────┘  └─────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │              下载任务列表 + 进度                   │ │
│  └──────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│              浏览器窗口 (独立 QWebEngineView)          │
│  ┌──────────────────────────────────────────────────┐ │
│  │  地址栏 + 导航按钮                                │ │
│  ├──────────────────────────────────────────────────┤ │
│  │            网页内容 (用户登录、浏览)               │ │
│  ├──────────────────────────────────────────────────┤ │
│  │  嗅探面板：检测到的视频 [画质] [下载]              │ │
│  └──────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  网络嗅探层 (QWebEngineUrlRequestInterceptor)        │
│  → 拦截 .m3u8 / .mp4 / .flv 等媒体请求              │
│  → 提取 Cookie 传递给 yt-dlp                         │
├──────────────────────────────────────────────────────┤
│  yt-dlp (下载引擎，携带站点 Cookie)                   │
│  ffmpeg (合并/转码)                                   │
└──────────────────────────────────────────────────────┘
```

## 项目结构

```
Physalis/
├── main.py                  # 入口
├── app.py                   # QApplication 初始化
├── ui/
│   ├── main_window.py       # 主窗口（链接输入 + 下载列表）
│   ├── browser_window.py    # 浏览器窗口（核心）
│   ├── sniff_panel.py       # 嗅探视频列表面板
│   ├── download_list.py     # 下载任务列表
│   ├── settings_dialog.py   # 设置（下载路径、并发数等）
│   └── resources/           # 图标/样式
├── core/
│   ├── sniffer.py           # 网络请求拦截 + 视频URL识别
│   ├── cookie_manager.py    # 浏览器Cookie提取 → 传给yt-dlp
│   ├── downloader.py        # yt-dlp 封装，任务调度
│   ├── task.py              # 下载任务数据模型
│   └── config.py            # 配置管理
├── utils/
│   ├── media_patterns.py    # 视频/音频URL正则匹配规则
│   ├── platform_utils.py    # 跨平台路径/命令检测
│   └── log.py               # 日志
└── requirements.txt
```

## 核心工作流

1. 用户打开浏览器窗口 → 导航到抖音/B站等站点 → 正常登录
2. `QWebEngineUrlRequestInterceptor` 实时拦截页面中的媒体请求
3. 嗅探到的视频 URL + 当前页面的 Cookie 显示在底部嗅探面板
4. 用户点击下载 → Cookie 和 URL 一起传给 yt-dlp → 完成下载

---

## 模块详细设计

### 1. 网络嗅探模块 (core/sniffer.py)

#### 处理流程

```
浏览器网络请求
      │
      ▼
QWebEngineUrlRequestInterceptor.interceptRequest()
      │
      ├─ 过滤：只关注媒体相关请求
      │   ├─ URL 后缀: .m3u8, .mp4, .flv, .ts, .m4s, .webm, .mpd
      │   ├─ Content-Type: video/*, application/dash+xml, application/x-mpegURL
      │   └─ 关键词: /video/, /play/, /stream/, /manifest/
      │
      ▼
MediaRequest 解析
      │
      ├─ 提取: url, method, headers, resource_type
      ├─ 智能去重: 同一视频的不同画质/分片归组
      │   ├─ m3u8 → 解析主播放列表 → 提取各画质子流
      │   ├─ mpd (DASH) → 解析自适应流 → 提取音视频轨道
      │   └─ 直接 .mp4 → 记录为独立视频
      │
      ▼
VideoItem 信号发射 → sniff_panel.py 更新UI
```

#### 核心类

```python
class SniffedVideo:
    url: str                    # 视频真实地址
    page_url: str               # 来源页面
    title: str = ""             # 视频标题（从页面提取）
    format: str = ""            # m3u8 / mp4 / dash
    quality: str = ""           # 1080p / 720p / ...
    size_hint: int = 0          # 大小估算（从Content-Length）
    headers: dict               # 请求头（Referer等，部分站点需要）
    cookies: dict               # 关联Cookie
    timestamp: float            # 发现时间

class NetworkSniffer(QWebEngineUrlRequestInterceptor):
    video_found = pyqtSignal(SniffedVideo)

    def interceptRequest(self, info):
        # 1. URL模式匹配
        # 2. 去重检查（避免重复信号）
        # 3. m3u8内容预解析（可选，获取画质列表）
        # 4. 发射 video_found 信号
```

#### 抖音特殊处理

```
抖音页面请求流程：
  页面HTML → API请求(/aweme/v1/) → 返回JSON含video.play_addr
                                          │
   同时：浏览器播放器请求 .m3u8 / .m4s     │
                                          │
  策略：两层捕获 ──────────────────────────┘
    1. API层：拦截 /aweme/v1/ 响应，JSON解析出视频URL
    2. 流媒体层：拦截 .m3u8/.m4s 请求，直接获取播放地址
    → 两者去重合并，优先使用API层（含更多元数据）
```

### 2. Cookie 管理模块 (core/cookie_manager.py)

#### 架构

```
┌─────────────────────────────────────────────────┐
│              CookieManager                       │
│                                                 │
│  ┌───────────────┐    ┌──────────────────────┐  │
│  │ QWebEngine    │    │ Cookie存储            │  │
│  │ CookieStore   │───▶│ SQLite (持久化)       │  │
│  └───────────────┘    └──────────────────────┘  │
│         │                       │               │
│         ▼                       ▼               │
│  实时Cookie提取           Cookie持久化           │
│  (登录态保持)            (跨会话免重复登录)       │
│         │                       │               │
│         └───────────┬───────────┘               │
│                     ▼                           │
│          导出为 yt-dlp 可用格式                   │
│          ├─ Netscape格式文件 (--cookies)          │
│          └─ 命令行字典                            │
└─────────────────────────────────────────────────┘
```

#### 核心类

```python
class CookieManager:
    def __init__(self, profile: QWebEngineProfile):
        self._store = profile.cookieStore()
        self._store.cookieAdded.connect(self._on_cookie_added)
        self._store.cookieRemoved.connect(self._on_cookie_removed)
        self._cookies: dict[str, list[QNetworkCookie]] = {}  # domain → cookies
        self._db = CookieDatabase()  # SQLite持久化

    def get_cookies(self, domain: str) -> list[QNetworkCookie]:
        """获取指定域名的所有Cookie"""

    def export_netscape_file(self, domain: str) -> str:
        """导出为Netscape格式文件，供yt-dlp --cookies使用"""

    def export_to_ytdlp_args(self, domain: str) -> list[str]:
        """直接生成yt-dlp命令行参数"""

    def restore_cookies(self, domain: str):
        """启动时从SQLite恢复Cookie到浏览器"""
```

#### Cookie 传递给 yt-dlp 的流程

```
用户在浏览器登录抖音
       │
       ▼
CookieManager 捕获并存储 Cookie
       │
       ▼
用户点击"下载"
       │
       ▼
CookieManager.export_netscape_file("douyin.com")
       │
       ▼
生成临时 /tmp/physalis_cookies_douyin.txt
       │
       ▼
yt-dlp --cookies /tmp/physalis_cookies_douyin.txt <url>
       │
       ▼
下载完成后删除临时Cookie文件
```

### 3. 浏览器窗口 (ui/browser_window.py)

#### 界面布局

```
┌──────────────────────────────────────────────────┐
│  ◀  ▶  🔄    [  https://www.douyin.com  ]  📋   │  ← 导航栏
├──────────────────────────────────────────────────┤
│                                                  │
│              网页内容区域                          │
│          (QWebEngineView)                        │
│                                                  │
├──────────────────────────────────────────────────┤
│  嗅探到 3 个视频                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ 📹 抖音视频-标题1    1080p  m3u8   [⬇下载] │  │
│  │ 📹 抖音视频-标题2    720p   mp4    [⬇下载] │  │
│  │ 📹 抖音视频-标题3    480p   m3u8   [⬇下载] │  │
│  └────────────────────────────────────────────┘  │
│  [全部下载]                    [清除] [设置]      │
└──────────────────────────────────────────────────┘
```

#### 窗口特性

| 特性 | 实现 |
|------|------|
| 独立 Profile | 每个浏览器窗口用独立 `QWebEngineProfile`，Cookie 互不干扰 |
| User-Agent | 可自定义 UA，模拟移动端/桌面端 |
| 嗅探面板 | 底部可折叠 `QDockWidget`，不影响浏览 |
| 一键下载 | 点击直接调用 `downloader.py`，Cookie 自动注入 |
| 全部下载 | 批量添加到下载队列 |
| Cookie 持久 | 关闭窗口后 Cookie 保存到 SQLite，下次打开免登录 |

### 4. 下载器模块 (core/downloader.py)

#### 下载流程

```
用户点击下载
      │
      ▼
Downloader.add_task(SniffedVideo)
      │
      ├─ 1. CookieManager 导出该域名Cookie
      ├─ 2. 构建 yt-dlp 命令:
      │      yt-dlp
      │        --cookies <cookie_file>
      │        --referer <page_url>
      │        --add-header "User-Agent: <ua>"
      │        -f "bestvideo[height<=1080]+bestaudio/best"
      │        -o "<download_dir>/%(title)s.%(ext)s"
      │        <video_url>
      │
      ├─ 3. QProcess 启动 yt-dlp（可监听输出）
      │
      ├─ 4. 实时解析 yt-dlp stdout:
      │      [download]  45.3% of 123.45MiB at 2.5MiB/s ETA 00:27
      │      → 提取百分比、速度、剩余时间 → 更新UI
      │
      ├─ 5. 下载完成 → ffmpeg 合并（yt-dlp自动处理）
      │
      └─ 6. 发射信号 task_completed / task_failed
```

#### 并发调度

```python
class DownloadScheduler:
    max_concurrent: int = 3              # 最大同时下载数
    queue: list[DownloadTask]            # 等待队列
    active: dict[int, QProcess]          # task_id → 运行中进程

    def add_task(self, video: SniffedVideo):
        """添加任务，有空位立即启动，否则入队"""

    def _start_next(self):
        """从队列取任务启动"""

    def _on_process_output(self, task_id, line):
        """解析yt-dlp输出，更新进度"""
```

### 5. 数据流总览

```
┌──────────── 浏览器窗口 ────────────┐
│  QWebEngineView                    │
│      │ 网络请求                     │
│      ▼                             │
│  NetworkSniffer ──→ SniffedVideo   │
│      │                 │           │
│  CookieManager         │           │
│      │                 │           │
└──────┼─────────────────┼───────────┘
       │                 │
       ▼                 ▼
  cookies.txt      用户点击下载
       │                 │
       └───────┬─────────┘
               ▼
        DownloadScheduler
               │
               ▼
         yt-dlp (QProcess)
          --cookies + --referer + URL
               │
               ▼
         下载文件 → 本地磁盘
               │
               ▼
         主窗口下载列表更新进度
```

---

## 技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| PyQt6 | >= 6.6 | GUI框架 |
| PyQt6-WebEngine | >= 6.6 | 内置浏览器 |
| yt-dlp | >= 2024.0 | 下载引擎（外部二进制，打包内嵌） |
| ffmpeg | - | 音视频处理（外部二进制，打包内嵌） |

## 打包分发

| 平台 | 方案 | 说明 |
|------|------|------|
| Windows | PyInstaller → 单目录/单exe | 内嵌 yt-dlp + ffmpeg |
| Linux | AppImage 或 Flatpak | 内嵌 yt-dlp + ffmpeg |
| macOS | PyInstaller → .app bundle | 可选支持 |

## 开发里程碑

### Phase 1 - 最小可用版本
- 主窗口：链接输入 + 下载列表
- yt-dlp 封装：基本下载功能
- 直接粘贴链接 → yt-dlp 下载

### Phase 2 - 浏览器嗅探
- 浏览器窗口：QWebEngineView + 导航栏
- 网络嗅探：QWebEngineUrlRequestInterceptor
- 嗅探面板：检测到的视频列表
- 一键下载嗅探到的视频

### Phase 3 - Cookie 管理与登录
- CookieManager：实时捕获 + SQLite 持久化
- Cookie 导出给 yt-dlp
- 登录态保持：关闭窗口后重新打开免登录
- 抖音/B站等需登录站点的完整流程

### Phase 4 - 体验打磨
- 画质/格式选择器
- 下载历史记录
- 多语言支持（中/英）

### Phase 5 - 打包发布
- Windows PyInstaller 打包
- Linux AppImage 打包
- 自动更新机制
