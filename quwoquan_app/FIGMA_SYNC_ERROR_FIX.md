# Figma同步错误修复指南

## ❌ 错误信息

```
API请求失败: 400 - File type not supported by this endpoint
```

## 🔍 问题分析

这个错误表示你提供的Figma文件是**社区文件或模板**（URL格式为 `/make/`），而不是标准的设计文件（URL格式为 `/file/`）。

### 当前文件信息
- **URL格式**: `https://www.figma.com/make/UQSjvrR1smHEJzeDq2kYJT/趣我圈2026`
- **文件类型**: 社区文件/模板 (`/make/`)
- **问题**: 社区文件无法通过Figma API直接访问

## ✅ 解决方案

### 方案1：复制文件到工作区（推荐）

1. **在Figma中打开文件**
   - 访问: https://www.figma.com/make/UQSjvrR1smHEJzeDq2kYJT/趣我圈2026

2. **复制到你的工作区**
   - 点击右上角 **"..."** 菜单
   - 选择 **"Duplicate"** 或 **"复制"**
   - 选择复制到你的团队或个人工作区

3. **获取新文件的URL**
   - 复制后的文件URL格式应该是: `https://www.figma.com/file/NEW_FILE_KEY/File-Name`
   - 注意：URL从 `/make/` 变成了 `/file/`

4. **更新配置**
   ```bash
   # 编辑 .env 文件，更新文件ID
   FIGMA_FILE_KEY=新的文件ID
   ```

5. **重新运行同步**
   ```bash
   npm run sync:figma:enhanced
   ```

### 方案2：使用团队文件

如果你有团队文件访问权限：

1. **确认文件URL格式**
   - 标准文件: `https://www.figma.com/file/FILE_KEY/File-Name`
   - 不是: `https://www.figma.com/make/FILE_KEY/File-Name`

2. **检查访问权限**
   - 确保你是团队成员
   - 确保访问令牌有读取权限

3. **更新文件ID**
   - 从正确的URL中提取文件ID
   - 更新 `.env` 文件

### 方案3：手动导出设计令牌

如果无法通过API访问，可以手动操作：

1. **在Figma中查看设计令牌**
   - 打开文件
   - 查找 "Design Tokens" 页面或Frame

2. **手动提取值**
   - 颜色值：查看填充颜色
   - 间距值：查看Frame尺寸

3. **更新代码**
   - 手动更新 `lib/core/design_system/colors/app_colors.dart`
   - 手动更新 `lib/core/design_system/spacing/app_spacing.dart`

## 🔧 验证文件类型

### 检查URL格式

```bash
# 标准文件（可以API访问）
https://www.figma.com/file/FILE_KEY/File-Name

# 社区文件（无法API访问）
https://www.figma.com/make/FILE_KEY/File-Name
```

### 测试API访问

```bash
# 使用curl测试（需要先设置访问令牌）
curl -H "X-Figma-Token: YOUR_TOKEN" \
  https://api.figma.com/v1/files/YOUR_FILE_KEY
```

如果返回 `400 - File type not supported`，说明文件无法通过API访问。

## 📝 更新后的操作步骤

1. **复制文件到工作区**
   ```
   Figma → 打开文件 → "..." → Duplicate → 选择工作区
   ```

2. **获取新文件URL**
   ```
   新URL格式: https://www.figma.com/file/NEW_KEY/File-Name
   ```

3. **更新.env文件**
   ```bash
   FIGMA_FILE_KEY=新的文件ID
   ```

4. **重新运行同步**
   ```bash
   npm run sync:figma:enhanced
   ```

## 🆘 仍然遇到问题？

如果复制文件后仍然无法访问，请检查：

1. **访问令牌权限**
   - Settings → Account → Personal access tokens
   - 确认令牌有文件读取权限

2. **文件访问权限**
   - 确认你是文件的所有者或团队成员
   - 确认文件不是私有的

3. **文件ID格式**
   - 文件ID应该是32位字符串
   - 从URL的 `/file/FILE_KEY/` 部分提取

## 📚 相关文档

- [Figma API文档](https://www.figma.com/developers/api)
- [Figma迁移指南](./04.3_FIGMA_MIGRATION_GUIDE.md)

---

**关键提示**: 社区文件(`/make/`)无法通过API访问，必须先复制到工作区！
