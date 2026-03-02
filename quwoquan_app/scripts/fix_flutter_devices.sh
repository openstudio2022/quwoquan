#!/usr/bin/env bash
# 修复 Flutter/IDE「No Connected Devices Found」：ADB 报错会导致整次设备发现失败。
# 用法：在终端执行 ./scripts/fix_flutter_devices.sh，然后再打开 Android Studio 或运行 flutter run。

set -e
ADB="${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$ANDROID_HOME/platform-tools:$PATH"

echo "→ 结束现有 adb 进程..."
"$ADB" kill-server 2>/dev/null || true
sleep 1
echo "→ 启动 adb server..."
"$ADB" start-server
echo "→ 列出设备..."
"$ADB" devices
echo ""
echo "→ 检查 Flutter 设备列表..."
cd "$(dirname "$0")/.." && flutter devices
echo ""
echo "若上面能看到 iOS 模拟器或真机，再在 IDE 里选运行配置「quwoquan_app」并点 Run 即可。"
