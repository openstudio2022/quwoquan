#!/bin/bash
# iOS 模拟器运行脚本（无需代码签名）

echo "正在查找可用的 iOS 模拟器..."
DEVICES=$(xcrun simctl list devices available | grep -i "iphone" | head -1 | sed 's/.*(\(.*\)).*/\1/')

if [ -z "$DEVICES" ]; then
    echo "错误: 未找到可用的 iOS 模拟器"
    echo "请先启动一个模拟器，或运行: xcrun simctl boot 'iPhone 15 Pro Max'"
    exit 1
fi

echo "找到设备: $DEVICES"
echo "正在运行 Flutter 应用..."
flutter run -d "$DEVICES"
