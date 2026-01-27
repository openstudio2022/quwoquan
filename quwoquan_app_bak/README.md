# 趣我圈新功能开发规则

## 概述

本规则基于业界最佳实践，确保每个新功能的开发都遵循统一的标准，包括测试覆盖、埋点集成、响应式设计、主题支持、无障碍访问等全方位要求。

## 新功能开发流程

### 1. 需求分析与设计阶段

#### 1.1 功能需求文档
**必须包含**:
- 功能目标和业务价值
- 用户故事和使用场景
- 功能规格说明
- 交互流程设计
- 视觉设计要求
- 技术实现方案

#### 1.2 设计评审
**评审要点**:
- 用户体验一致性
- 响应式适配方案
- 无障碍访问支持
- 性能影响评估
- 安全风险评估

#### 1.3 技术方案设计
**设计要素**:
- 架构设计图
- 数据流设计
- 状态管理方案
- 组件结构设计
- 接口设计规范
- API端云一致性设计
- 灰度发布方案设计

### 2. 文档更新阶段

#### 2.1 README.md 更新
**更新要求**:
- 新增功能描述
- 功能特性列表
- 使用说明
- 配置要求
- 依赖关系

#### 2.2 PROJECT_STATUS.md 更新
**更新内容**:
- 功能开发目标
- 开发状态跟踪
- 问题记录和修复
- 测试覆盖情况
- 准出标准检查

#### 2.3 技术文档更新
**文档类型**:
- API文档
- 组件文档
- 配置文档
- 部署文档
- 维护文档

### 3. 开发实现阶段

#### 3.1 代码实现要求
**代码规范**:
- 遵循项目代码规范
- 使用统一的设计系统
- 实现响应式布局
- 支持主题切换
- 集成无障碍功能

#### 3.2 测试驱动开发
**测试要求**:
- 单元测试覆盖率 ≥ 80%
- Widget测试覆盖所有组件
- 集成测试验证功能流程
- E2E测试验证用户体验
- 性能测试确保性能指标

#### 3.3 埋点集成
**埋点要求**:
- 页面访问埋点
- 用户行为埋点
- 性能监控埋点
- 错误追踪埋点
- 业务转化埋点

### 4. 测试验证阶段

#### 4.1 响应式测试
**测试场景**:
- 手机竖屏 (375x812)
- 手机横屏 (812x375)
- 平板竖屏 (768x1024)
- 平板横屏 (1024x768)
- 桌面端 (1920x1080)

#### 4.2 主题测试
**测试要求**:
- 浅色主题正常显示
- 深色主题正常显示
- 主题切换无异常
- 颜色对比度符合标准
- 主题一致性验证

#### 4.3 无障碍测试
**测试项目**:
- 字体大小缩放 (0.8x - 2.0x)
- 高对比度模式
- 屏幕阅读器支持
- 键盘导航支持
- 语音控制支持

#### 4.4 异常处理测试
**测试场景**:
- 网络异常处理
- 数据异常处理
- 权限异常处理
- 存储异常处理
- 系统异常处理

### 5. 质量保证阶段

#### 5.1 代码审查
**审查要点**:
- 代码质量和规范
- 测试覆盖率
- 性能优化
- 安全漏洞
- 可维护性

#### 5.2 集成测试
**测试范围**:
- 功能模块集成
- 系统集成测试
- 第三方服务集成
- 数据流完整性
- 错误传播测试

#### 5.3 用户验收测试
**验收标准**:
- 功能完整性
- 用户体验质量
- 性能指标达标
- 兼容性验证
- 安全性验证

#### 5.4 灰度测试验证
**验证要求**:
- 灰度配置正确性
- 多维度灰度支持
- 监控告警机制
- 自动回滚功能
- 用户体验一致性

### 6. 发布准备阶段

#### 6.1 文档完善
**文档检查**:
- README.md 更新完整
- API文档同步
- 用户手册更新
- 开发者文档完善
- 故障排除指南

#### 6.2 部署准备
**部署检查**:
- 环境配置正确
- 依赖关系完整
- 数据迁移脚本
- 回滚方案准备
- 监控告警配置

#### 6.3 发布验证
**验证项目**:
- 功能正常可用
- 性能指标达标
- 监控数据正常
- 用户反馈收集
- 问题快速响应

## 具体实现要求

### 1. 响应式设计要求

#### 1.1 断点适配
```dart
// 必须支持的断点
class ResponsiveBreakpoints {
  static const double mobile = 480;
  static const double tablet = 768;
  static const double desktop = 1024;
  static const double wideDesktop = 1440;
}
```

#### 1.2 布局适配
```dart
// 响应式布局示例
Widget buildResponsiveLayout() {
  return LayoutBuilder(
    builder: (context, constraints) {
      if (constraints.maxWidth < ResponsiveBreakpoints.mobile) {
        return MobileLayout();
      } else if (constraints.maxWidth < ResponsiveBreakpoints.tablet) {
        return TabletLayout();
      } else {
        return DesktopLayout();
      }
    },
  );
}
```

#### 1.3 字体大小适配
```dart
// 响应式字体大小
double getResponsiveFontSize(double baseSize) {
  final screenWidth = MediaQuery.of(context).size.width;
  final scaleFactor = screenWidth / 375; // 基准宽度
  return baseSize * scaleFactor.clamp(0.8, 1.5);
}
```

### 2. 主题支持要求

#### 2.1 主题切换
```dart
// 主题切换实现
class ThemeAwareWidget extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final theme = isDark ? AppTheme.darkTheme : AppTheme.lightTheme;
    
    return Theme(
      data: theme,
      child: child,
    );
  }
}
```

#### 2.2 颜色适配
```dart
// 主题颜色使用
Color getThemeColor(BuildContext context, Color lightColor, Color darkColor) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return isDark ? darkColor : lightColor;
}
```

### 3. 无障碍支持要求

#### 3.1 语义化标签
```dart
// 无障碍标签
Semantics(
  label: '点赞按钮',
  hint: '点击点赞这篇文章',
  button: true,
  child: IconButton(
    onPressed: () => handleLike(),
    icon: Icon(Icons.favorite),
  ),
)
```

#### 3.2 字体缩放支持
```dart
// 字体缩放适配
Text(
  '标题文本',
  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
    fontSize: Theme.of(context).textTheme.headlineSmall!.fontSize! * 
              MediaQuery.of(context).textScaleFactor,
  ),
)
```

#### 3.3 高对比度支持
```dart
// 高对比度检测
bool get isHighContrastMode {
  return MediaQuery.of(context).highContrast;
}
```

### 4. 测试覆盖要求

#### 4.1 单元测试模板
```dart
// 单元测试示例
group('FeatureService Tests', () {
  late FeatureService service;
  
  setUp(() {
    service = FeatureService();
  });
  
  test('should return expected result when valid input provided', () {
    // Arrange
    final input = 'valid_input';
    final expected = 'expected_result';
    
    // Act
    final result = service.processInput(input);
    
    // Assert
    expect(result, equals(expected));
  });
  
  test('should throw exception when invalid input provided', () {
    // Arrange
    final input = 'invalid_input';
    
    // Act & Assert
    expect(() => service.processInput(input), throwsA(isA<ValidationException>()));
  });
});
```

#### 4.2 Widget测试模板
```dart
// Widget测试示例
testWidgets('FeatureWidget should display correctly', (tester) async {
  // Arrange
  await tester.pumpWidget(
    MaterialApp(
      home: FeatureWidget(),
    ),
  );
  
  // Act
  await tester.pumpAndSettle();
  
  // Assert
  expect(find.byType(FeatureWidget), findsOneWidget);
  expect(find.text('Expected Text'), findsOneWidget);
});
```

#### 4.3 集成测试模板
```dart
// 集成测试示例
testWidgets('Complete feature flow test', (tester) async {
  // 测试完整功能流程
  await tester.pumpWidget(MyApp());
  
  // 模拟用户操作
  await tester.tap(find.byKey(Key('feature_button')));
  await tester.pumpAndSettle();
  
  // 验证结果
  expect(find.text('Success Message'), findsOneWidget);
});
```

### 5. 埋点集成要求

#### 5.1 页面访问埋点
```dart
// 页面访问埋点
class FeaturePage extends StatefulWidget {
  @override
  _FeaturePageState createState() => _FeaturePageState();
}

class _FeaturePageState extends State<FeaturePage> {
  @override
  void initState() {
    super.initState();
    context.trackPageView(
      pageName: 'feature_page',
      pageTitle: '功能页面',
      pageCategory: 'feature',
    );
  }
  
  @override
  void dispose() {
    context.trackPageLeave(
      pageName: 'feature_page',
      duration: _calculateDuration(),
      exitMethod: 'back_button',
    );
    super.dispose();
  }
}
```

#### 5.2 用户行为埋点
```dart
// 用户行为埋点
void handleUserAction() {
  context.trackAction(
    action: 'click',
    target: 'feature_button',
    targetId: 'feature_123',
    actionProperties: {
      'button_type': 'primary',
      'feature_type': 'advanced',
    },
  );
}
```

#### 5.3 性能监控埋点
```dart
// 性能监控埋点
void trackPerformance() {
  context.trackPerformance(
    metric: 'page_load_time',
    value: loadTime.inMilliseconds.toDouble(),
    page: 'feature_page',
    performanceProperties: {
      'data_size': dataSize,
      'network_type': networkType,
    },
  );
}
```

### 6. 错误处理要求

#### 6.1 异常捕获
```dart
// 异常处理示例
Future<void> performAction() async {
  try {
    await riskyOperation();
  } catch (e, stackTrace) {
    // 记录错误
    context.trackError(
      errorType: 'feature_error',
      errorMessage: e.toString(),
      page: 'feature_page',
      errorProperties: {
        'operation': 'risky_operation',
        'stack_trace': stackTrace.toString(),
      },
    );
    
    // 用户友好提示
    showErrorDialog(e.toString());
  }
}
```

#### 6.2 网络错误处理
```dart
// 网络错误处理
Future<T> handleNetworkRequest<T>(Future<T> Function() request) async {
  try {
    return await request();
  } on SocketException {
    context.trackError(
      errorType: 'network_error',
      errorMessage: '网络连接失败',
      page: 'feature_page',
    );
    throw NetworkException('网络连接失败，请检查网络设置');
  } on TimeoutException {
    context.trackError(
      errorType: 'timeout_error',
      errorMessage: '请求超时',
      page: 'feature_page',
    );
    throw NetworkException('请求超时，请重试');
  }
}
```

## 质量检查清单

### 开发阶段检查
- [ ] 功能需求文档完整
- [ ] 技术方案设计合理
- [ ] 代码规范符合要求
- [ ] 单元测试覆盖率达标
- [ ] Widget测试完整
- [ ] 响应式布局正确
- [ ] 主题支持完整
- [ ] 无障碍功能正常
- [ ] 埋点集成完整
- [ ] 错误处理完善

### 测试阶段检查
- [ ] 单元测试通过
- [ ] Widget测试通过
- [ ] 集成测试通过
- [ ] E2E测试通过
- [ ] 性能测试达标
- [ ] 响应式测试通过
- [ ] 主题测试通过
- [ ] 无障碍测试通过
- [ ] 异常处理测试通过
- [ ] 兼容性测试通过

### 发布前检查
- [ ] 代码审查通过
- [ ] 文档更新完整
- [ ] 部署脚本准备
- [ ] 监控配置完成
- [ ] 回滚方案准备
- [ ] 用户验收通过
- [ ] 性能指标达标
- [ ] 安全扫描通过
- [ ] 兼容性验证通过
- [ ] 发布计划确认

## 持续改进

### 1. 反馈收集
- 用户反馈分析
- 性能数据监控
- 错误日志分析
- 使用数据统计

### 2. 优化迭代
- 性能优化
- 用户体验改进
- 功能完善
- 稳定性提升

### 3. 知识积累
- 最佳实践总结
- 问题解决方案
- 工具和流程改进
- 团队技能提升

---

**重要提醒**:
1. 每个功能开发必须严格遵循此规则
2. 所有检查项目必须全部通过才能发布
3. 文档更新必须与代码实现同步
4. 测试和埋点必须覆盖所有要求
5. 持续改进是质量保证的关键
