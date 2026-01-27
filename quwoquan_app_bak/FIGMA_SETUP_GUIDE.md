# Figma 代码恢复快速指南

## 📋 从 Figma 恢复代码的方法

根据你的 Figma 链接: https://www.figma.com/make/UQSjvrR1smHEJzeDq2kYJT/%E8%B6%A3%E6%88%91%E5%9C%882026

文件ID: `UQSjvrR1smHEJzeDq2kYJT`

## ⚠️ 重要提示

**当前设计系统代码已手动实现完整功能**，包括完整的颜色系统和间距系统。

**同步脚本会覆盖现有代码文件**，因此建议：

1. ✅ **手动对照方式**（推荐）- 在 Figma 中查看设计规范，手动更新代码
2. ⚠️ **自动同步方式** - 仅在需要从 Figma 重新导入基础值且已备份代码时使用

## 方法 1: 手动对照方式（推荐）

### 步骤：

1. **在 Figma 中查看设计规范**
   - 打开设计文件
   - 查看颜色系统、间距系统、字体系统
   - 查看组件设计

2. **对照更新代码**
   - 查看 `lib/core/design_system/colors/app_colors.dart`
   - 查看 `lib/core/design_system/spacing/app_spacing.dart`
   - 手动更新设计值

3. **参考设计文档**
   - `03_DESIGN_RULES.md` - 设计规则文档
   - `04.3_FIGMA_MIGRATION_GUIDE.md` - 完整的迁移指南

## 方法 2: 使用 Figma API 自动同步

### 前提条件

1. **获取 Figma 访问令牌**
   - 登录 [Figma](https://www.figma.com/)
   - Settings → Account → Personal access tokens
   - 点击 "Create new token"
   - 复制生成的令牌

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入你的访问令牌
   ```

3. **备份当前代码**（重要！）
   ```bash
   git add lib/core/design_system/
   git commit -m "backup: design system before figma sync"
   ```

### 运行同步

```bash
# Node.js 版本
npm install  # 首次运行需要安装依赖
node scripts/sync_figma.js

# 或 Python 版本
pip install requests python-dotenv
python3 scripts/sync_figma.py
```

### 同步后会覆盖的文件

- `lib/core/design_system/colors/app_colors.dart`
- `lib/core/design_system/spacing/app_spacing.dart`
- `lib/core/design_system/typography/app_typography.dart`

## 方法 3: 使用 Figma 插件

1. 在 Figma 中安装 "Figma to Flutter" 插件
2. 选择设计元素
3. 复制生成的代码
4. 手动集成到项目中

## 方法 4: 导出设计 Token（推荐用于设计系统）

如果 Figma 文件中使用了 Design Tokens：

1. 使用 Figma 的 Design Tokens 插件
2. 导出为 JSON 格式
3. 手动转换为 Flutter 代码

## 📚 相关文档

- [完整的 Figma 迁移指南](./04.3_FIGMA_MIGRATION_GUIDE.md)
- [设计规则文档](./03_DESIGN_RULES.md)
- [Figma 同步说明](./FIGMA_SYNC_README.md)

## 🔍 从 Figma 获取的信息

从 Figma 可以获取：
- ✅ 颜色系统（设计令牌）
- ✅ 间距系统（设计令牌）
- ✅ 字体系统（设计令牌）
- ✅ 组件设计（需要手动实现）
- ✅ 布局信息（需要手动实现）
- ✅ 图标和图片（需要手动导出）

**注意**：Figma API 主要用于获取设计令牌（Design Tokens），组件和布局需要手动对照实现。
