# Phase 2 - 浏览器嗅探 设计文档

## 概述

为 Physalis 添加内置浏览器和视频嗅探功能。用户在浏览器中访问视频站点，NetworkSniffer 自动拦截媒体请求，SniffPanel 展示嗅探到的视频，用户可一键下载（Cookie 自动注入）。

## 决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 浏览器窗口模型 | 独立 QMainWindow | 与主窗口解耦，嗅探视频发送到主窗口下载列表 |
| 媒体识别方式 | URL 模式匹配 | QWebEngineUrlRequestInterceptor 只能看到请求，看不到响应/Content-Type |
| Cookie 管理 | 内存提取，不持久化 | Phase 3 再做 SQLite 持久化，当前从 QWebEngineCookieStore 实时提取 |

## 新增/修改文件

```
新增:
  core/sniffer.py        # NetworkSniffer + SniffedVideo
  ui/browser_window.py   # BrowserWindow — 独立 QMainWindow
  ui/sniff_panel.py      # 底部嗅探视频面板

修改:
  ui/main_window.py      # 添加"打开浏览器"入口
  app.py                 # 浏览器相关控件样式
```

core/downloader.py、core/task.py、core/config.py 无需修改 — 已支持 cookies_file、referer 字段。

## 模块设计

### 1. NetworkSniffer (core/sniffer.py)

继承 QWebEngineUrlRequestInterceptor，拦截浏览器网络请求，匹配媒体 URL。

**URL 匹配规则：**
- 后缀: `.m3u8`, `.mp4`, `.flv`, `.ts`, `.m4s`, `.webm`, `.mpd`
- 路径关键词: `/video/`, `/play/`, `/stream/`, `/manifest/`, `/aweme/v1/`

**去重策略：**
- 维护 `_seen_urls: set[str]`，跳过已见 URL
- 同一视频的不同 .ts 分片（相同路径前缀，不同段号）只保留第一个

**数据模型：**
```python
@dataclass
class SniffedVideo:
    url: str
    page_url: str        # firstPartyUrl
    referer: str         # Referer 请求头
    format_hint: str     # "m3u8" / "mp4" / "dash" / "flv"
    quality: str = ""    # 可从 URL 推断，否则为空
    timestamp: float = field(default_factory=time.time)
```

**信号：** `video_found = pyqtSignal(object)` — 使用 object 避免 Qt 元类型注册。

### 2. BrowserWindow (ui/browser_window.py)

独立 QMainWindow，包含导航栏 + QWebEngineView + SniffPanel。

**布局：**
```
┌──────────────────────────────────────────┐
│  ◀ ▶ 🔄   [  https://www.douyin.com  ] │  ← 导航栏
├──────────────────────────────────────────┤
│           QWebEngineView                 │
├──────────────────────────────────────────┤
│  嗅探到 N 个视频          [清除] [全部下载] │
│  ┌────────────────────────────────────┐  │
│  │ 标题/URL    m3u8  1080p    [下载]  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

**关键实现：**
- 每个窗口创建独立 off-the-record QWebEngineProfile，设置 NetworkSniffer
- 导航栏: QLineEdit 地址栏 + 后退/前进/刷新按钮
- SniffPanel 底部可折叠
- 下载流程: 点击下载 → 从 QWebEngineCookieStore 提取域名 Cookie → 写临时 Netscape 文件 → 构造 DownloadTask → 发射信号
- 信号: `download_requested = pyqtSignal(DownloadTask)`，MainWindow 连接到 Downloader.add_task()

**Cookie 提取流程：**
1. 用户点击"下载"
2. 从 SniffedVideo.url 提取域名
3. `cookieStore.getAllCookies()` 异步回调
4. 过滤该域名的 cookie，写入 `/tmp/physalis_cookies_<domain>.txt`（Netscape 格式）
5. 构造 `DownloadTask(url=video.url, cookies_file=path, referer=video.referer)`
6. 发射 `download_requested` 信号

### 3. SniffPanel (ui/sniff_panel.py)

底部面板，展示嗅探到的视频列表。

**功能：**
- 接收 NetworkSniffer.video_found 信号，调用 add_video()
- 每条视频一行 QWidget: 标题/URL + 格式标签 + 下载按钮
- 顶部: "嗅探到 N 个视频" + [清除] + [全部下载]
- add_video() 检查 URL 去重
- 清除按钮清空列表
- 信号: `download_requested(SniffedVideo)`, `download_all_requested()`

### 4. MainWindow 修改

- 添加"打开浏览器"按钮或菜单项
- 打开 BrowserWindow 时连接其 `download_requested` 信号到 `Downloader.add_task()`
- BrowserWindow 保持引用防止 GC

### 5. app.py 修改

- 为导航栏按钮、地址栏、SniffPanel 添加样式

## 数据流

```
用户在浏览器浏览视频站点
       │
       ▼
NetworkSniffer.interceptRequest() 拦截请求
       │
       ├─ URL 匹配媒体模式 → 发射 video_found
       │
       ▼
SniffPanel 显示嗅探到的视频
       │
       ▼
用户点击 [下载]
       │
       ▼
BrowserWindow 提取 Cookie → 写 Netscape 文件
       │
       ▼
构造 DownloadTask(url, cookies_file, referer)
       │
       ▼
发射 download_requested → MainWindow → Downloader.add_task()
       │
       ▼
yt-dlp --cookies <file> --referer <url> <video_url>
```
