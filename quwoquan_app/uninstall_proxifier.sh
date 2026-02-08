#!/bin/bash
# Proxifier 彻底卸载脚本（需在终端执行，会提示输入密码）

set -e
echo "=== Proxifier 彻底卸载 ==="

# 1. 卸载系统扩展（必须，否则重装会冲突）
echo ""
echo "1. 卸载 Proxifier 系统扩展..."
sudo systemextensionsctl uninstall NXELXU5YLW com.initex.proxifier.v3.macos.ProxifierExtension
echo "   系统扩展已卸载。"

# 2. 删除受保护的容器目录
echo ""
echo "2. 删除用户容器数据..."
sudo rm -rf "$HOME/Library/Containers/com.initex.proxifier.v3.macos"
echo "   容器数据已删除。"

# 3. 删除系统扩展文件（若上述 uninstall 后仍有残留）
echo ""
echo "3. 删除系统扩展文件..."
sudo rm -rf /Library/SystemExtensions/F85495BC-2FB8-407B-85A9-92AEE7E68D4E/com.initex.proxifier.v3.macos.ProxifierExtension.systemextension
sudo rmdir /Library/SystemExtensions/F85495BC-2FB8-407B-85A9-92AEE7E68D4E 2>/dev/null || true
echo "   完成。"

echo ""
echo "=== 卸载完成。建议重启 Mac 后再安装新版本。 ==="
