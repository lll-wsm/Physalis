#!/bin/bash
#
# Physalis macOS App 打包脚本
# 使用方法: ./build_macapp.sh
#

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Physalis macOS App 构建脚本 ==="
echo "工作目录: $SCRIPT_DIR"

# 检查环境
if [ ! -d ".venv" ]; then
    echo "错误: 未找到 .venv 虚拟环境"
    echo "请先运行: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 激活虚拟环境并安装 PyInstaller
echo "1. 安装 PyInstaller..."
.venv/bin/pip install pyinstaller

# 检查 yt-dlp
echo "2. 检查 yt-dlp..."
if ! command -v yt-dlp &> /dev/null && [ ! -f "bin/yt-dlp" ]; then
    echo "警告: 未找到 yt-dlp，将从网络下载..."
    mkdir -p bin
    curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o bin/yt-dlp
    chmod +x bin/yt-dlp
fi

# 清理旧构建
echo "3. 清理旧构建..."
rm -rf dist/Physalis dist/Physalis.app

# 打包
echo "4. 开始打包..."
.venv/bin/pyinstaller Physalis.spec --clean -y

# 修复 PyInstaller 损坏的 QtWebEngineCore.framework 符号链接
echo "5. 修复 QtWebEngineCore 符号链接..."
WEBENGINE_FRAMEWORK="dist/Physalis.app/Contents/Frameworks/PyQt6/Qt6/lib/QtWebEngineCore.framework"
if [ -d "$WEBENGINE_FRAMEWORK" ]; then
    cd "$WEBENGINE_FRAMEWORK"
    # PyInstaller 会创建指向 Versions/Current/... 的符号链接，
    # 但实际文件被放在了 Versions/Resources/ 下，导致链接指向错误位置。
    # 这里无条件修复两个符号链接。
    if [ -L "Helpers" ] || [ -e "Helpers" ]; then
        rm -f Helpers
        ln -s Versions/Resources/Helpers Helpers
        echo "  已修复 Helpers 链接"
    fi
    if [ -L "Resources" ] || [ -e "Resources" ]; then
        rm -f Resources
        ln -s Versions/Resources/Resources Resources
        echo "  已修复 Resources 链接"
    fi
    cd "$SCRIPT_DIR"
fi

# 清理
echo "6. 清理构建产物..."
rm -rf build/Physalis.spec.bak

echo ""
echo "=== 构建完成 ==="
echo "App 位置: dist/Physalis.app"
echo ""
echo "运行测试:"
echo "  open dist/Physalis.app"
echo ""
echo "签名（可选，需要开发者证书）:"
echo '  codesign --force --deep --sign "Developer ID Application: Your Name" dist/Physalis.app'
