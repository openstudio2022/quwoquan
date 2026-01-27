#!/bin/bash

# Figma配置助手脚本

echo "🚀 Figma同步配置助手"
echo ""

# 检查.env文件是否存在
if [ -f .env ]; then
    echo "✅ .env 文件已存在"
    echo ""
    echo "当前配置："
    grep -E "FIGMA_ACCESS_TOKEN|FIGMA_FILE_KEY" .env | sed 's/=.*/=***/' || echo "  未找到配置项"
    echo ""
    read -p "是否要更新配置？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi
else
    echo "📝 创建新的 .env 文件"
fi

# 文件ID（从用户提供的URL提取）
FILE_KEY="UQSjvrR1smHEJzeDq2kYJT"
echo "✅ Figma文件ID已设置: $FILE_KEY"
echo ""

# 获取访问令牌
echo "请提供你的Figma访问令牌："
echo "（如果还没有，请访问: https://www.figma.com/developers/api#access-tokens）"
read -p "FIGMA_ACCESS_TOKEN: " ACCESS_TOKEN

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ 错误: 访问令牌不能为空"
    exit 1
fi

# 写入.env文件
cat > .env << EOF
# Figma API配置
# 自动生成于 $(date)
FIGMA_ACCESS_TOKEN=$ACCESS_TOKEN
FIGMA_FILE_KEY=$FILE_KEY
FIGMA_DESIGN_TOKENS_NODE_ID=
EOF

echo ""
echo "✅ 配置完成！"
echo ""
echo "📋 配置信息："
echo "  文件ID: $FILE_KEY"
echo "  访问令牌: ${ACCESS_TOKEN:0:10}***"
echo ""
echo "🚀 现在可以运行同步："
echo "   npm run sync:figma"
echo ""
