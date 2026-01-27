# Figma同步 - 一键完成

## 🚀 快速开始

### 方法1：使用快速同步脚本（最简单）

```bash
bash scripts/quick_sync.sh
```

脚本会自动：
1. ✅ 检查或创建 `.env` 文件
2. ✅ 提示输入Figma访问令牌（如果需要）
3. ✅ 自动备份当前代码
4. ✅ 运行同步
5. ✅ 显示结果和下一步操作

### 方法2：手动配置后运行

```bash
# 1. 创建.env文件（或使用配置助手）
bash scripts/setup_figma_config.sh

# 2. 运行同步
npm run sync:figma:enhanced
```

## 📋 当前配置

- **Figma文件ID**: `UQSjvrR1smHEJzeDq2kYJT`
- **项目名称**: 趣我圈2026
- **同步脚本**: 已准备就绪

## 🔑 获取Figma访问令牌

1. 登录 https://www.figma.com/
2. Settings → Account → Personal access tokens
3. Create new token
4. 复制令牌

## ✅ 同步后的验证

```bash
# 检查代码
flutter analyze lib/core/design_system/

# 查看差异
git diff lib/core/design_system/

# 运行测试
flutter test
```

## 📚 更多信息

- [项目更新状态](PROJECT_UPDATE_STATUS.md)
- [快速开始指南](QUICK_START_FIGMA_SYNC.md)
- [Figma迁移指南](04.3_FIGMA_MIGRATION_GUIDE.md)

---

**推荐**: 直接运行 `bash scripts/quick_sync.sh` 即可完成所有操作！
