# 趣我圈App 项目规则总结

## 📋 规则体系概览

本项目建立了完整的规则体系，涵盖从项目规划到持续改进的全生命周期管理。

## 🎯 核心规则要点

### 1. 语义标签使用规范 ⭐
**最重要的编码规范**

```yaml
必须使用:
  - 颜色: AppColors.primaryColor, AppColors.success, AppColors.error
  - 间距: AppSpacing.semantic[DesignSemanticConstants.container][DesignSemanticConstants.md]
  - 文本: UITextConstants.loading, UITextConstants.home
  - 类型: ContentTypeConstants.image, ContentTypeConstants.video
  - 语义: DesignSemanticConstants.container, DesignSemanticConstants.md

禁止使用:
  - 硬编码颜色: Color(0xFF1877F2)
  - 硬编码间距: EdgeInsets.all(16.w)
  - 硬编码文本: '加载中...'
  - 魔鬼数字: 48.h, 24.sp
```

### 2. 空值安全处理
```dart
// ✅ 正确
AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ?? AppSpacing.containerSm

// ❌ 错误
AppSpacing.semantic[DesignSemanticConstants.container][DesignSemanticConstants.sm]
```

### 3. 设计系统一致性
- 使用设计令牌系统
- 支持浅色/深色主题
- 响应式设计适配
- 无障碍访问支持

### 4. 代码质量要求
- 静态分析通过率100%
- 测试覆盖率>80%
- 语义标签使用率100%
- 硬编码值消除率100%

## 📚 规则文档体系

### 🎯 项目规划与需求
| 文档 | 用途 | 关键内容 |
|------|------|----------|
| [01_项目计划书](01_PROJECT_PLANNING.md) | 项目概述和目标 | Figma原型迁移指导 |
| [02_需求规格说明书](02_REQUIREMENTS_SPECIFICATION.md) | 功能需求详细规格 | 功能性和非功能性需求 |

### 🎨 设计与编码规则
| 文档 | 用途 | 关键内容 |
|------|------|----------|
| [03_设计规则](03_DESIGN_RULES.md) | 设计系统规范 | 颜色、字体、间距、组件系统 |
| [04_编码规则](04_CODING_RULES.md) | 代码规范 | 语义标签、状态管理、错误处理 |
| [04.1_设计颜色检查清单](04.1_DESIGN_COLOR_CHECKLIST.md) | 颜色系统检查 | 颜色准确性、对比度、无障碍 |
| [04.2_API设计规则](04.2_API_DESIGN_RULES.md) | API设计规范 | 端云一致性、接口规范 |
| [04.3_Figma迁移指导](04.3_FIGMA_MIGRATION_GUIDE.md) | 原型迁移指导 | Figma到Flutter的迁移流程 |
| [编码规范检查清单](CODING_STANDARDS_CHECKLIST.md) | 编码质量检查 | 语义标签使用检查清单 |
| [编码规范快速参考](CODING_QUICK_REFERENCE.md) | 快速参考指南 | 常用语义标签和代码模式 |

### 🧪 测试与质量保证
| 文档 | 用途 | 关键内容 |
|------|------|----------|
| [05_测试规则](05_TESTING_RULES.md) | 测试规范 | 单元测试、集成测试、性能测试 |
| [06_发布质量保证规则](06_RELEASE_QA_RULES.md) | 质量保证流程 | 自动化审查、质量检查 |

### 🚀 发布与监控规则
| 文档 | 用途 | 关键内容 |
|------|------|----------|
| [07_灰度发布规则](07_GRAY_SCALE_RULES.md) | 灰度发布策略 | 多维度灰度、监控告警、回滚机制 |
| [08_用户行为与体验规则](08_USER_BEHAVIOR_EXPERIENCE_RULES.md) | 用户体验管理 | 行为分析、体验优化、反馈处理 |
| [09_系统监控规则](09_SYSTEM_MONITORING_RULES.md) | 系统监控 | 基础设施监控、应用性能监控 |
| [10_持续改进规则](10_CONTINUOUS_IMPROVEMENT_RULES.md) | 持续改进 | 数据驱动改进、质量提升 |

### 📊 项目状态与参考
| 文档 | 用途 | 关键内容 |
|------|------|----------|
| [项目规则框架](PROJECT_RULES_FRAMEWORK.md) | 规则体系架构 | 完整的项目规则体系 |
| [项目状态](PROJECT_STATUS.md) | 开发进度跟踪 | 任务状态和进度 |
| [首页功能规格](HOME_FEATURE_SPEC.md) | 功能详细说明 | 主页功能规格 |

## 🚀 快速开始指南

### 新开发者入门
1. **阅读核心文档**:
   - [编码规范快速参考](CODING_QUICK_REFERENCE.md) - 语义标签使用
   - [编码规范检查清单](CODING_STANDARDS_CHECKLIST.md) - 质量检查
   - [项目规则框架](PROJECT_RULES_FRAMEWORK.md) - 规则体系

2. **开发前准备**:
   - 配置开发环境
   - 了解设计系统
   - 熟悉语义标签使用

3. **开发流程**:
   - 遵循编码规范
   - 使用语义标签
   - 编写测试用例
   - 进行代码审查

### 日常开发检查
```bash
# 1. 运行静态分析
flutter analyze

# 2. 检查硬编码值
grep -r "Color(0x" lib/
grep -r "EdgeInsets\.all(" lib/
grep -r "\.h\|\.sp" lib/

# 3. 运行测试
flutter test

# 4. 格式化代码
dart format .
```

## 🎯 关键检查点

### 代码提交前检查
- [ ] 语义标签使用正确
- [ ] 硬编码值已替换
- [ ] 空值安全处理
- [ ] 静态分析通过
- [ ] 测试用例通过
- [ ] 代码格式化完成

### 功能开发检查
- [ ] 设计系统一致性
- [ ] 响应式设计支持
- [ ] 无障碍访问支持
- [ ] 主题切换支持
- [ ] 性能优化到位
- [ ] 错误处理完善

### 发布前检查
- [ ] 所有规则文档已遵循
- [ ] 质量检查通过
- [ ] 测试覆盖率达标
- [ ] 性能指标达标
- [ ] 安全审查通过
- [ ] 用户体验验证

## 🔧 工具和资源

### 开发工具
- **IDE**: VS Code / Android Studio
- **分析工具**: Flutter Analyzer
- **测试工具**: Flutter Test
- **格式化工具**: Dart Format

### 检查工具
- **静态分析**: `flutter analyze`
- **代码搜索**: `grep` 命令
- **测试运行**: `flutter test`
- **格式化**: `dart format`

### 参考资源
- **快速参考**: [编码规范快速参考](CODING_QUICK_REFERENCE.md)
- **检查清单**: [编码规范检查清单](CODING_STANDARDS_CHECKLIST.md)
- **规则框架**: [项目规则框架](PROJECT_RULES_FRAMEWORK.md)

## 📞 支持与反馈

### 规则问题
- 查看相关规则文档
- 参考快速参考指南
- 使用检查清单验证

### 技术问题
- 查看编码规范文档
- 参考设计系统规范
- 使用测试规则指导

### 流程问题
- 查看项目规则框架
- 参考发布规则文档
- 使用质量保证流程

---

**重要提醒**:
- 语义标签使用是编码规范的核心要求
- 所有硬编码值都必须替换为语义标签
- 空值安全处理是必须的
- 遵循完整的开发流程和检查清单

**最后更新**: 2024年12月19日  
**版本**: v1.0  
**维护者**: 项目团队
