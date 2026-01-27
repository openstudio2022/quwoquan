# Figma同步工具使用说明

## 📦 安装

### Node.js版本（推荐）

```bash
# 安装依赖
npm install

# 或使用yarn
yarn install
```

### Python版本

```bash
# 安装依赖
pip install requests python-dotenv

# 或使用pip3
pip3 install requests python-dotenv
```

## ⚙️ 配置

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的Figma配置：
```bash
FIGMA_ACCESS_TOKEN=your_token_here
FIGMA_FILE_KEY=your_file_key_here
```

## 🚀 使用

### 运行同步

#### Node.js版本
```bash
npm run sync:figma
```

#### Python版本
```bash
python3 scripts/sync_figma.py
```

### 输出文件

同步后会在以下位置生成文件：
- `lib/core/design_system/colors/app_colors.dart` - 颜色常量
- `lib/core/design_system/spacing/app_spacing.dart` - 间距常量

## 📋 使用前检查清单

- [ ] 已安装Node.js (>=14.0.0) 或 Python (>=3.7)
- [ ] 已配置 `.env` 文件
- [ ] 已获取Figma访问令牌
- [ ] 已获取Figma文件ID
- [ ] Figma文件中有设计令牌节点

## 🔍 验证

同步完成后，运行以下命令验证：

```bash
# 检查代码格式
flutter analyze

# 运行测试
flutter test

# 格式化代码
dart format lib/core/design_system/
```

## 📝 注意事项

1. **不要手动修改自动生成的文件**
   - 这些文件会在下次同步时被覆盖
   - 如需自定义，请修改同步脚本

2. **定期同步**
   - 设计更新后及时同步
   - 发布前确保已同步最新设计

3. **版本控制**
   - 将 `.env` 添加到 `.gitignore`
   - 不要提交包含敏感信息的配置文件

## 🆘 问题排查

### 权限问题
- 确保Figma访问令牌有文件读取权限
- 确认文件是公开的或你有访问权限

### 节点找不到
- 检查Figma文件中是否有 "Design Tokens" 节点
- 或设置 `FIGMA_DESIGN_TOKENS_NODE_ID` 环境变量

### 网络问题
- 检查网络连接
- 确认可以访问Figma API

更多问题请参考 [Figma迁移指南](./04.3_FIGMA_MIGRATION_GUIDE.md)

