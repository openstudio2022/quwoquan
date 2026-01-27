# 项目更新指南

## 🎯 更新目标

从Figma原型同步最新的设计令牌，更新项目设计系统代码。

## 📋 更新步骤

### 第一步：配置Figma访问

由于 `.env` 文件受保护，需要手动创建：

#### 方法1：使用配置助手（最简单）

```bash
bash scripts/setup_figma_config.sh
```

#### 方法2：手动创建.env文件

在项目根目录创建 `.env` 文件：

```bash
FIGMA_ACCESS_TOKEN=你的访问令牌
FIGMA_FILE_KEY=UQSjvrR1smHEJzeDq2kYJT
FIGMA_DESIGN_TOKENS_NODE_ID=
```

**获取访问令牌**：
1. 登录 https://www.figma.com/
2. Settings → Account → Personal access tokens
3. Create new token
4. 复制令牌

### 第二步：备份当前代码

```bash
# 备份设计系统代码
git add lib/core/design_system/
git commit -m "backup: before figma sync"
```

### 第三步：运行同步

```bash
# 使用增强版同步脚本（推荐）
npm run sync:figma:enhanced

# 或使用运行脚本（包含自动备份）
bash scripts/run_figma_sync.sh
```

### 第四步：验证更新

```bash
# 检查生成的代码
flutter analyze lib/core/design_system/

# 查看差异
git diff lib/core/design_system/

# 运行测试
flutter test
```

## ⚠️ 注意事项

1. **代码会被覆盖**：同步脚本会覆盖 `app_colors.dart` 和 `app_spacing.dart`
2. **自动备份**：增强版脚本会自动备份原文件（`.backup.时间戳`）
3. **需要访问权限**：确保Figma文件有访问权限

## 🆘 遇到问题？

- 查看 [快速开始指南](QUICK_START_FIGMA_SYNC.md)
- 查看 [Figma迁移指南](04.3_FIGMA_MIGRATION_GUIDE.md)
