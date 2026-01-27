#!/bin/bash

# Figma同步运行脚本
# 如果.env文件不存在，会提示用户创建

cd "$(dirname "$0")/.."

echo "🚀 Figma同步脚本"
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "❌ .env 文件不存在"
    echo ""
    echo "请先创建 .env 文件，内容如下："
    echo ""
    echo "FIGMA_ACCESS_TOKEN=你的访问令牌"
    echo "FIGMA_FILE_KEY=UQSjvrR1smHEJzeDq2kYJT"
    echo "FIGMA_DESIGN_TOKENS_NODE_ID="
    echo ""
    echo "或者运行配置助手："
    echo "  bash scripts/setup_figma_config.sh"
    echo ""
    exit 1
fi

# 检查访问令牌
if ! grep -q "FIGMA_ACCESS_TOKEN" .env || grep -q "your_figma_access_token_here" .env; then
    echo "❌ Figma访问令牌未配置"
    echo ""
    echo "请在 .env 文件中设置有效的 FIGMA_ACCESS_TOKEN"
    echo ""
    exit 1
fi

# 备份当前代码
echo "📦 备份当前设计系统代码..."
if [ -d lib/core/design_system ]; then
    BACKUP_DIR=".figma_sync_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    cp -r lib/core/design_system "$BACKUP_DIR/"
    echo "✅ 已备份到: $BACKUP_DIR"
    echo ""
fi

# 运行同步
echo "🔄 开始同步Figma设计令牌..."
echo ""

if command -v node &> /dev/null; then
    npm run sync:figma:enhanced
else
    echo "❌ Node.js 未安装"
    exit 1
fi
