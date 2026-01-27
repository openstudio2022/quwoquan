# Figma同步配置说明

## 📋 当前配置信息

根据你提供的Figma链接，已识别以下信息：
- **项目名称**: 趣我圈2026
- **Figma文件ID**: `UQSjvrR1smHEJzeDq2kYJT`
- **Figma链接**: https://www.figma.com/make/UQSjvrR1smHEJzeDq2kYJT/趣我圈2026

## ⚙️ 配置步骤

### 1. 创建 `.env` 文件

在项目根目录创建 `.env` 文件，内容如下：

```bash
# Figma API配置
FIGMA_ACCESS_TOKEN=你的访问令牌
FIGMA_FILE_KEY=UQSjvrR1smHEJzeDq2kYJT
FIGMA_DESIGN_TOKENS_NODE_ID=
```

### 2. 获取Figma访问令牌

1. 登录 [Figma](https://www.figma.com/)
2. 点击右上角头像 → **Settings**
3. 在左侧菜单找到 **Account** → **Personal access tokens**
4. 点击 **Create new token**
5. 输入令牌名称（如：`quwoquan-app-sync`）
6. 复制生成的令牌
7. 将令牌粘贴到 `.env` 文件的 `FIGMA_ACCESS_TOKEN=` 后面

### 3. 安装依赖

```bash
npm install
```

### 4. 运行同步

```bash
npm run sync:figma
```

或者直接运行：

```bash
node scripts/sync_figma.js
```

## 🔍 注意事项

### 关于文件URL格式

你提供的URL是 `/make/` 格式，这是Figma社区文件或模板。如果无法访问，可能需要：

1. **确认文件访问权限**
   - 确保你有该文件的查看权限
   - 如果是团队文件，确保你是团队成员

2. **使用标准文件URL**
   - 如果是你自己的文件，URL格式应该是：`https://www.figma.com/file/FILE_KEY/File-Name`
   - 文件ID `UQSjvrR1smHEJzeDq2kYJT` 应该仍然有效

3. **检查API访问**
   - 确保访问令牌有读取文件的权限
   - 某些社区文件可能需要特殊权限

## 🚀 快速开始

完成配置后，运行：

```bash
# 1. 安装依赖（如果还没安装）
npm install

# 2. 运行同步
npm run sync:figma

# 3. 检查生成的文件
flutter analyze lib/core/design_system/
```

## 📝 同步后的检查

同步完成后，请检查：

1. **生成的文件**
   - `lib/core/design_system/colors/app_colors.dart`
   - `lib/core/design_system/spacing/app_spacing.dart`

2. **代码验证**
   ```bash
   flutter analyze
   flutter test
   ```

3. **代码差异**
   ```bash
   git diff lib/core/design_system/
   ```

## ⚠️ 重要提示

**当前设计系统代码已手动实现完整功能**，同步脚本会覆盖这些文件。

建议：
1. 先提交当前代码到Git
2. 运行同步后检查差异
3. 如有问题可以快速回退

```bash
# 备份当前代码
git add lib/core/design_system/
git commit -m "backup: design system before figma sync"
```

## 🆘 遇到问题？

### 常见错误

1. **401 Unauthorized**
   - 检查访问令牌是否正确
   - 确认令牌未过期

2. **404 Not Found**
   - 检查文件ID是否正确
   - 确认有文件访问权限

3. **未找到设计令牌节点**
   - 在Figma中创建名为 "Design Tokens" 的页面或Frame
   - 或手动设置 `FIGMA_DESIGN_TOKENS_NODE_ID`

更多帮助请参考：[Figma迁移指南](./04.3_FIGMA_MIGRATION_GUIDE.md)
