# Physalis

Cross-platform video downloader with embedded browser for URL sniffing.

## 简体中文

跨平台视频下载器，内置浏览器支持 URL 嗅探功能。

## Features / 功能特性

| English | 中文 |
|---------|------|
| Embedded browser with video URL sniffing | 内置浏览器，支持视频 URL 嗅探 |
| yt-dlp powered download engine | 基于 yt-dlp 的下载引擎 |
| Cookie management for authenticated content | Cookie 管理，支持需要登录的内容 |
| Cross-platform (macOS/Linux/Windows) | 跨平台支持 (macOS/Linux/Windows) |
| Per-domain title extraction rules | 域名级标题提取规则 |
| Download history persistence | 下载历史持久化 |

## Requirements / 环境要求

- Python 3.10+
- PyQt6 >= 6.6.0
- PyQt6-WebEngine >= 6.6.0
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (must be on `$PATH` or at `bin/yt-dlp`)

## Installation / 安装

```bash
# Clone the repository
git clone <repo-url>
cd Physalis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Quick Start / 快速开始

```bash
.venv/bin/python main.py
```

## Usage / 使用

1. **Browser Sniffing / 浏览器嗅探**
   - Click the browser button to open the embedded browser
   - Navigate to any video website
   - The sniff panel will automatically detect video URLs
   - Click the download button to add to queue

2. **URL Paste / URL 粘贴**
   - Paste a video URL directly into the app
   - Single video: starts downloading immediately
   - Playlist: select videos via the selection dialog

3. **Cookie Management / Cookie 管理**
   - Export cookies from browser to access premium content
   - Supports Netscape cookie format for yt-dlp

## Architecture / 架构

```
main.py
 └── app.py (create_app, styles)
      └── ui/main_window.py
           ├── core/downloader.py     # yt-dlp wrapper
           ├── core/sniffer.py        # URL interceptor
           ├── core/config.py         # Settings singleton
           ├── core/cookie_manager.py # Cookie persistence
           └── ui/browser_window.py   # Embedded browser + sniff panel
```

**Key Components / 主要组件：**

- `MainWindow` - Main download list and status bar
- `BrowserWindow` - Embedded QWebEngineView + SniffPanel
- `Downloader` - QProcess-based yt-dlp wrapper
- `NetworkSniffer` - HTTP request interceptor for media detection
- `Config` - Singleton settings manager
- `CookieManager` - Cookie persistence and export

## Configuration / 配置

Settings are stored in `config.json`:
- `download_dir` - Download directory path
- `max_concurrent` - Max concurrent downloads
- `preferred_quality` - Preferred video quality
- `language` - UI language (zh_CN / en_US)

## Building macOS App / 构建 macOS 应用

```bash
# 使用打包脚本（推荐）
./build_macapp.sh

# 或手动执行
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller Physalis.spec --clean
```

输出位置: `dist/Physalis.app`

**签名（可选）:**
```bash
codesign --force --deep --sign "Developer ID Application: Your Name" dist/Physalis.app
```

**公证（需要 Apple 开发者账号）:**
```bash
# 先压缩
zip -r Physalis.zip Physalis.app

# 提交公证
notarytool submit Physalis.zip --apple-id "your@email.com" --password "app-password" --team-id "TEAMID"
```

## License

MIT License
