# Figma同步快速开始指南

## 🎯 当前状态

- ✅ **Figma文件ID**: `UQSjvrR1smHEJzeDq2kYJT`
- ✅ **项目名称**: 趣我圈2026
- ✅ **Figma链接**: https://www.figma.com/make/UQSjvrR1smHEJzeDq2kYJT/趣我圈2026
- ✅ **Node.js依赖**: 已安装
- ✅ **同步脚本**: 已准备就绪

## 📝 第一步：配置环境变量

由于 `.env` 文件受保护，需要手动创建：

### 方法1：使用配置助手（推荐）

```bash
bash scripts/setup_figma_config.sh
```

脚本会引导你输入Figma访问令牌。

### 方法2：手动创建

在项目根目录创建 `.env` 文件：

```bash
# 在项目根目录执行
cat > .env << 'EOF'
# Figma API配置
FIGMA_ACCESS_TOKEN=你的访问令牌
FIGMA_FILE_KEY=UQSjvrR1smHEJzeDq2kYJT
FIGMA_DESIGN_TOKENS_NODE_ID=
EOF
```

## 🔑 获取Figma访问令牌

1. 登录 [Figma](https://www.figma.com/)
2. 点击右上角头像 → **Settings**
3. 左侧菜单：**Account** → **Personal access tokens**
4. 点击 **Create new token**
5. 输入名称（如：`quwoquan-app-sync`）
6. 复制生成的令牌
7. 将令牌粘贴到 `.env` 文件的 `FIGMA_ACCESS_TOKEN=` 后面

## 🚀 第二步：运行同步

### 使用增强版脚本（推荐）

增强版脚本支持从Figma变量、样式和节点中提取设计令牌：

```bash
npm run sync:figma:enhanced
```

### 或使用标准脚本

```bash
npm run sync:figma
```

## 📊 同步过程说明

同步脚本会：

1. **从Figma API获取文件信息**
   - 文件名称和结构
   - 设计令牌节点

2. **提取设计令牌**
   - ✅ 从Figma变量（Variables）中提取颜色
   - ✅ 从Figma样式（Styles）中提取颜色
   - ✅ 从设计令牌节点中提取颜色和间距
   - ✅ 自动查找名为 "Design Tokens" 的页面或Frame

3. **生成Flutter代码**
   - `lib/core/design_system/colors/app_colors.dart`
   - `lib/core/design_system/spacing/app_spacing.dart`

4. **自动备份**
   - 同步前会自动备份原文件（`.backup.时间戳`）

## ✅ 第三步：验证同步结果

### 1. 检查生成的文件

```bash
# 查看颜色文件
cat lib/core/design_system/colors/app_colors.dart

# 查看间距文件
cat lib/core/design_system/spacing/app_spacing.dart
```

### 2. 运行代码检查

```bash
flutter analyze lib/core/design_system/
```

### 3. 检查差异

```bash
git diff lib/core/design_system/
```

## ⚠️ 重要提示

### 关于代码覆盖

**当前设计系统代码已手动实现完整功能**，同步脚本会覆盖这些文件。

**建议操作流程**：

```bash
# 1. 先备份当前代码
git add lib/core/design_system/
git commit -m "backup: design system before figma sync"

# 2. 运行同步
npm run sync:figma:enhanced

# 3. 检查差异
git diff lib/core/design_system/

# 4. 如有问题，可以恢复
git checkout lib/core/design_system/
```

### 关于Figma文件访问

你提供的URL是 `/make/` 格式，这是Figma社区文件或模板。

如果遇到访问权限问题：

1. **确认文件访问权限**
   - 确保你有该文件的查看权限
   - 如果是团队文件，确保你是团队成员

2. **检查API访问**
   - 确保访问令牌有读取文件的权限
   - 某些社区文件可能需要特殊权限

## 🆘 遇到问题？

### 常见错误及解决方案

#### 1. 401 Unauthorized
```
❌ API请求失败: 401
```
**解决**：
- 检查访问令牌是否正确
- 确认令牌未过期
- 重新生成访问令牌

#### 2. 404 Not Found
```
❌ 获取Figma文件失败: 404
```
**解决**：
- 检查文件ID是否正确：`UQSjvrR1smHEJzeDq2kYJT`
- 确认有文件访问权限
- 尝试在浏览器中打开文件，确认可以访问

#### 3. 未找到设计令牌节点
```
⚠️  未找到设计令牌节点
```
**解决**：
- 在Figma中创建名为 "Design Tokens" 的页面或Frame
- 或手动设置 `FIGMA_DESIGN_TOKENS_NODE_ID` 环境变量

#### 4. 未找到颜色/间距令牌
```
⚠️  未找到颜色令牌，跳过颜色同步
```
**解决**：
- 在Figma中使用变量（Variables）定义颜色
- 或创建设计令牌节点，包含颜色矩形和间距Frame
- 确保节点命名清晰（如：Primary, Secondary, Spacing-XS等）

## 📚 相关文档

- [Figma迁移指南](./04.3_FIGMA_MIGRATION_GUIDE.md) - 详细的使用说明
- [Figma同步配置说明](./FIGMA_SYNC_SETUP.md) - 配置步骤
- [设计系统恢复文档](./DESIGN_SYSTEM_RESTORED.md) - 当前代码状态

## 🎉 完成！

同步完成后，你的设计系统代码将与Figma原型保持一致。

如有任何问题，请查看相关文档或检查错误信息。
