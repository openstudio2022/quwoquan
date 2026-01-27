#!/bin/bash

# 快速Figma同步脚本
# 如果.env不存在，会提示用户输入令牌

cd "$(dirname "$0")/.."

echo "🚀 Figma快速同步"
echo ""

# 检查或创建.env文件
if [ ! -f .env ]; then
    echo "📝 创建 .env 文件..."
    echo ""
    read -p "请输入你的Figma访问令牌: " TOKEN
    
    if [ -z "$TOKEN" ]; then
        echo "❌ 错误: 访问令牌不能为空"
        exit 1
    fi
    
    cat > .env << EOF
# Figma API配置
# 自动生成于 $(date)
FIGMA_ACCESS_TOKEN=$TOKEN
FIGMA_FILE_KEY=UQSjvrR1smHEJzeDq2kYJT
FIGMA_DESIGN_TOKENS_NODE_ID=
EOF
    
    echo "✅ .env 文件已创建"
    echo ""
else
    # 检查令牌是否有效
    if grep -q "your_figma_access_token_here" .env || ! grep -q "FIGMA_ACCESS_TOKEN=" .env; then
        echo "⚠️  .env 文件存在但令牌未配置"
        read -p "请输入你的Figma访问令牌: " TOKEN
        if [ ! -z "$TOKEN" ]; then
            sed -i.bak "s/FIGMA_ACCESS_TOKEN=.*/FIGMA_ACCESS_TOKEN=$TOKEN/" .env
            echo "✅ 令牌已更新"
        fi
    fi
fi

# 备份当前代码
echo ""
echo "📦 备份当前设计系统代码..."
BACKUP_DIR=".figma_sync_backup_$(date +%Y%m%d_%H%M%S)"
if [ -d lib/core/design_system ]; then
    mkdir -p "$BACKUP_DIR"
    cp -r lib/core/design_system "$BACKUP_DIR/" 2>/dev/null
    echo "✅ 已备份到: $BACKUP_DIR"
fi

# 运行同步
echo ""
echo "🔄 开始同步Figma设计令牌..."
echo ""

npm run sync:figma:enhanced

SYNC_EXIT_CODE=$?

if [ $SYNC_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✨ 同步完成！"
    echo ""
    echo "📝 下一步:"
    echo "1. 检查生成的文件: lib/core/design_system/"
    echo "2. 运行: flutter analyze lib/core/design_system/"
    echo "3. 查看差异: git diff lib/core/design_system/"
else
    echo ""
    echo "❌ 同步失败，请检查错误信息"
    echo "💡 提示: 如果备份文件存在，可以使用备份恢复"
    exit $SYNC_EXIT_CODE
fi
