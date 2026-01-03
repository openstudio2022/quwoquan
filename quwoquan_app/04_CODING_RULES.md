# 趣我圈App 编码规则

## 📋 文档概述

### 基本信息
- **项目名称**: 趣我圈 (QuWoQuan)
- **文档版本**: v1.0
- **创建日期**: 2024年12月19日
- **适用范围**: 趣我圈App端侧和云侧开发
- **技术栈**: Flutter + Dart + Riverpod + GoRouter
- **实现基础**: 基于Figma设计原型的Flutter功能迁移和商用化增强

### 编码原则
- **可读性**: 代码清晰易懂
- **可维护性**: 易于修改和扩展
- **可测试性**: 便于单元测试
- **性能**: 优化执行效率
- **安全**: 确保代码安全
- **原型一致性**: 严格遵循Figma设计原型实现
- **设计系统一致性**: 使用设计系统的语义颜色和间距，避免魔鬼数字

### 🔄 原型迁移编码指导

#### 代码实现优先级
1. **Figma设计还原**: 严格按照Figma设计稿实现UI组件和布局
2. **JS原型逻辑**: 基于JS原型的交互逻辑和业务流程
3. **Flutter最佳实践**: 遵循Flutter开发最佳实践和性能优化
4. **参考代码**: Figma生成的Flutter代码仅作为参考

#### 原型迁移编码规范
```yaml
原型迁移编码规范:
  设计系统实现:
    - 严格按照Figma设计系统定义颜色、字体、间距等
    - 确保设计令牌与Figma组件属性完全对应
    - 实现响应式设计时保持设计比例和视觉层次
    - 支持多主题时保持设计一致性
    - 禁止使用魔鬼数字：所有颜色、间距、尺寸必须使用设计系统的语义值
    - 颜色使用：AppColors.primaryColor、AppColors.secondaryColor、AppColors.accentColor等语义颜色
    - 功能性颜色：AppColors.success、AppColors.warning、AppColors.error、AppColors.info
    - 特殊功能色：AppColors.special.linkColor、AppColors.special.hoverColor等
    - 间距使用：响应式语义间距系统，自动适配不同屏幕尺寸
      * 组内间距：context.getIntraGroupSpacing('md')
      * 组间间距：context.getInterGroupSpacing('lg')
      * 容器间距：context.getContainerSpacing('sm')
      * 语义常量：AppSpacing.getSpacing(DesignSemanticConstants.intraGroup, DesignSemanticConstants.md, context: context)
    - 圆角使用：AppBorderRadius.values[DesignSemanticConstants.md]等语义圆角
    - 文本常量：UITextConstants.loading、UITextConstants.retry等语义文本
    - 内容类型：ContentTypeConstants.image、ContentTypeConstants.video等语义类型

  UI组件实现:
    - 每个Figma组件对应一个Flutter Widget
    - 组件属性与Figma组件属性一一对应
    - 实现组件的所有状态和变体
    - 确保组件的可复用性和一致性

  交互逻辑实现:
    - 基于JS原型分析用户交互流程
    - 实现所有原型中的交互行为和反馈
    - 确保状态管理与原型行为一致
    - 实现动画和过渡效果与原型一致

  数据流实现:
    - 分析JS原型中的数据流和状态管理
    - 使用Riverpod实现状态管理
    - 确保数据流与原型逻辑一致
    - 实现错误处理与原型行为一致

  代码质量:
    - 参考但不依赖Figma生成的Flutter代码
    - 按照项目编码规范重新组织代码
    - 添加必要的注释和文档
    - 确保代码的可测试性和可维护性
```

#### 原型对比验证
```yaml
原型对比验证:
  视觉对比:
    - 逐页面与Figma设计稿进行像素级对比
    - 确保布局、颜色、字体、间距完全一致
    - 验证响应式适配效果与设计一致
    - 确认多主题切换效果符合设计

  交互对比:
    - 逐功能与JS原型进行交互行为对比
    - 确保用户操作流程与原型完全一致
    - 验证反馈机制和状态变化与原型一致
    - 确认动画效果和过渡与原型一致

  功能对比:
    - 逐功能点与原型进行功能完整性对比
    - 确保所有原型功能都有对应实现
    - 验证业务逻辑和数据流与原型一致
    - 确认错误处理和边界情况与原型一致

  性能对比:
    - 确保性能表现符合原型预期
    - 验证启动时间和响应时间符合要求
    - 确认内存使用和电池消耗合理
    - 验证网络请求和数据加载效率
```

## 🏗️ 架构规范

### 1. 项目结构

#### 1.1 端侧结构 (Flutter App)
```yaml
目录结构:
  lib/
    app/                    # 全局应用状态和配置
      state/               # 全局状态定义
      providers/           # 全局状态提供者
      config/              # 应用配置
      services/            # 全局服务
    
    core/                  # 核心功能
      design_system/       # 设计系统
        colors/            # 颜色系统
        typography/        # 字体系统
        spacing/           # 间距系统
        borders/           # 边框系统
        shadows/           # 阴影系统
        theme/             # 主题系统
        tokens/            # 设计令牌
        accessibility/     # 无障碍支持
        responsive/        # 响应式设计
        breakpoints/       # 断点系统
        animation/         # 动画系统
      navigation/          # 路由导航
      data/               # 数据层
        models/           # 数据模型
        services/         # 数据服务
        interfaces/       # 数据接口
      constants/          # 常量定义
      resources/          # 资源管理
        fonts/            # 字体资源
        icons/            # 图标资源
        images/           # 图片资源
      utils/              # 工具类
    
    features/             # 功能模块
      home/               # 首页功能
        pages/            # 页面
        widgets/          # 组件
        providers/        # 状态管理
        models/           # 数据模型
        services/         # 服务
      search/             # 搜索功能
      create/             # 创建功能
      chat/               # 聊天功能
      profile/            # 个人资料功能
    
    shared/               # 共享组件
      widgets/            # 通用组件
      components/         # 复合组件
      utils/              # 共享工具
    
    analytics/            # 分析系统
      services/           # 分析服务
      models/             # 数据模型
      providers/          # 状态管理
      utils/              # 工具类
      widgets/            # UI组件
    
    test/                 # 测试代码
      unit/               # 单元测试
      widget/             # Widget测试
      integration/        # 集成测试
      e2e/                # 端到端测试
      golden/             # Golden测试
      mocks/              # Mock数据
```

#### 1.2 云侧结构 (Backend Service)
```yaml
目录结构:
  quwoquan_service/
    api/                  # API接口层
      v1/                 # API版本1
        auth/             # 认证接口
        users/            # 用户接口
        posts/            # 内容接口
        search/           # 搜索接口
        chat/             # 聊天接口
        analytics/        # 分析接口
      middleware/         # 中间件
      validators/         # 验证器
      handlers/           # 处理器
    
    services/             # 业务服务层
      auth/               # 认证服务
      user/               # 用户服务
      post/               # 内容服务
      search/             # 搜索服务
      chat/               # 聊天服务
      notification/       # 通知服务
      analytics/          # 分析服务
      file/               # 文件服务
    
    models/               # 数据模型层
      user/               # 用户模型
      post/               # 内容模型
      chat/               # 聊天模型
      analytics/          # 分析模型
      common/             # 通用模型
    
    database/             # 数据存储层
      migrations/         # 数据库迁移
      seeds/              # 种子数据
      repositories/       # 数据仓库
      connections/        # 数据库连接
    
    analytics/            # 分析服务层
      collectors/         # 数据收集器
      processors/         # 数据处理器
      storage/            # 数据存储
      exporters/          # 数据导出器
    
    monitoring/           # 监控服务层
      metrics/            # 指标监控
      logs/               # 日志监控
      alerts/             # 告警监控
      health/             # 健康检查
    
    config/               # 配置管理
      environments/       # 环境配置
      constants/          # 常量定义
      secrets/            # 密钥管理
    
    utils/                # 工具类
      helpers/            # 辅助函数
      validators/         # 验证工具
      formatters/         # 格式化工具
      encoders/           # 编码工具
    
    tests/                # 测试代码
      unit/               # 单元测试
      integration/        # 集成测试
      e2e/                # 端到端测试
      fixtures/           # 测试数据
      mocks/              # Mock服务
```

### 2. 颜色语义系统编码规范

#### 2.1 颜色使用规范
```yaml
颜色语义系统使用规范:
  主色调使用:
    - 主蓝色: AppColors.primaryColor (#1877F2)
    - 悬停状态: AppColors.primaryColorHover (#166FE5)
    - 激活状态: AppColors.primaryColorActive (#1565C0)
    - 浅色版本: AppColors.primaryColorLight (#E7F3FF)
    - 深色版本: AppColors.primaryColorDark (#0D47A1)
    
  次要色调使用:
    - 主紫色: AppColors.secondaryColor (#8B5CF6)
    - 悬停状态: AppColors.secondaryColorHover (#7C3AED)
    - 激活状态: AppColors.secondaryColorActive (#6D28D9)
    - 浅色版本: AppColors.secondaryColorLight (#F3E8FF)
    - 深色版本: AppColors.secondaryColorDark (#4C1D95)
    
  强调色调使用:
    - 主绿色: AppColors.accentColor (#10B981)
    - 悬停状态: AppColors.accentColorHover (#059669)
    - 激活状态: AppColors.accentColorActive (#047857)
    - 浅色版本: AppColors.accentColorLight (#D1FAE5)
    - 深色版本: AppColors.accentColorDark (#064E3B)
    
  功能性颜色使用:
    - 成功色: AppColors.success (#00BA7C)
    - 警告色: AppColors.warning (#FF9500)
    - 错误色: AppColors.error (#ED4956)
    - 信息色: AppColors.info (#1877F2)
    
  特殊功能色使用:
    - 链接色: AppColors.special.linkColor
    - 悬停色: AppColors.special.hoverColor
    - 选中色: AppColors.special.selectedColor
    - 焦点色: AppColors.special.focusColor
    - 禁用色: AppColors.special.disabledColor
    
  禁止使用:
    - 硬编码颜色值: Color(0xFF1877F2)
    - 魔鬼数字: const Color(0xFFFFFFFF)
    - 非语义颜色: Colors.blue, Colors.red
```

#### 2.2 颜色语义常量使用
```yaml
颜色语义常量使用规范:
  导入方式:
    - import 'package:quwoquan_core/quwoquan_core.dart';
    
  常量使用:
    - 颜色语义: ColorSemanticConstants.primary
    - 设计语义: DesignSemanticConstants.container
    - 内容类型: ContentTypeConstants.image
    - 文本常量: UITextConstants.loading
    
  示例代码:
    - 正确: AppColors.primaryColor
    - 错误: const Color(0xFF1877F2)
    - 正确: context.getContainerSpacing(DesignSemanticConstants.md)
    - 正确: AppSpacing.getSpacing('container', 'md', context: context)
    - 错误: EdgeInsets.all(16.w)
    - 错误: const EdgeInsets.all(20)
```

### 3. 响应式间距系统编码规范

#### 3.1 间距系统使用原则
```yaml
使用原则:
  语义优先: 优先使用语义化间距，避免硬编码数值
  响应式: 利用自动屏幕检测，无需手动判断设备类型
  一致性: 相同语义使用相同的间距等级
  层次性: 不同语义保持清晰的视觉层次关系
  
核心组件:
  AppSpacing: 主要的响应式间距系统类
  DesignSemanticConstants: 语义常量定义
  AppSpacingExtension: BuildContext扩展方法
```

#### 3.2 间距使用方法
```dart
// ✅ 推荐使用方式 - 自动响应式
Padding(
  padding: EdgeInsets.all(context.getContainerSpacing('md')),
  child: Column(
    children: [
      Text('标题'),
      SizedBox(height: context.getIntraGroupSpacing('sm')),
      Text('内容'),
      SizedBox(height: context.getInterGroupSpacing('lg')),
      ElevatedButton(onPressed: () {}, child: Text('按钮')),
    ],
  ),
)

// ✅ 使用语义常量
Padding(
  padding: EdgeInsets.all(
    context.getContainerSpacing(DesignSemanticConstants.md)
  ),
  child: Column(
    children: [
      Text('标题'),
      SizedBox(height: context.getIntraGroupSpacing(DesignSemanticConstants.sm)),
      Text('内容'),
    ],
  ),
)

// ✅ 指定屏幕类型（特殊场景）
double spacing = AppSpacing.getSpacing(
  'intraGroup', 
  'md', 
  screenType: 'tablet'
);

// ❌ 错误方式 - 硬编码数值
Padding(
  padding: EdgeInsets.all(16.0), // 错误：硬编码
  child: Column(
    children: [
      Text('标题'),
      SizedBox(height: 8.0), // 错误：硬编码
      Text('内容'),
    ],
  ),
)
```

#### 3.3 间距语义选择指南
```yaml
intraGroup (组内间距):
  使用场景: 同一组内相关元素之间的间距
  示例: 标签组、按钮组、表单项内部元素
  等级选择:
    xs: 紧密标签组 (4-8px)
    sm: 标签组、按钮组 (6-12px)
    md: 表单项、列表项 (8-16px)
    lg: 卡片内容 (12-20px)
    xl: 宽松布局 (16-24px)

interGroup (组间间距):
  使用场景: 不同组之间的间距
  示例: 相关组、独立模块、页面区块
  等级选择:
    xs: 紧密相关组 (8-16px)
    sm: 相关组 (12-24px)
    md: 一般组 (16-32px)
    lg: 独立组 (24-40px)
    xl: 页面区块 (32-48px)

container (容器间距):
  使用场景: 容器内边距
  示例: 卡片内边距、页面内边距、弹窗内边距
  等级选择:
    xs: 极小容器 (8-16px)
    sm: 小容器 (12-20px)
    md: 中等容器 (16-24px)
    lg: 大容器 (20-32px)
    xl: 超大容器 (24-40px)
```

#### 3.4 屏幕适配说明
```yaml
自动适配机制:
  Mobile (< 768px): 紧凑间距，适合触摸操作
  Tablet (768px - 1024px): 中等间距，平衡触摸和视觉
  Desktop (> 1024px): 宽松间距，适合鼠标操作
  
适配策略:
  - 屏幕越大，间距越宽松
  - 保持视觉比例和层次关系
  - 确保触摸友好的最小间距
  - 提供舒适的视觉呼吸空间
```

### 4. 模块化原则

#### 3.1 模块划分
```yaml
模块划分原则:
  功能模块:
    - 按业务功能划分
    - 模块间低耦合
    - 模块内高内聚
    - 接口清晰定义

  技术模块:
    - 按技术层次划分
    - 依赖关系清晰
    - 可独立测试
    - 可独立部署

  共享模块:
    - 通用功能提取
    - 避免重复代码
    - 统一接口规范
    - 版本兼容管理
```

#### 2.2 依赖管理
```yaml
依赖原则:
  依赖方向:
    - 上层依赖下层
    - 同层不相互依赖
    - 避免循环依赖
    - 依赖倒置原则

  依赖注入:
    - 使用Provider模式
    - 接口依赖而非实现
    - 便于单元测试
    - 便于模块替换
```

## 📝 代码规范

### 1. 命名规范

#### 1.1 文件命名
```yaml
命名规则:
  页面文件: xxx_page.dart
  组件文件: xxx_widget.dart
  状态文件: xxx_state.dart
  服务文件: xxx_service.dart
  模型文件: xxx.dart
  工具文件: xxx_utils.dart
  常量文件: xxx_constants.dart
  配置文件: xxx_config.dart
  测试文件: xxx_test.dart
  Mock文件: xxx_mock.dart
```

#### 1.2 类命名
```yaml
命名规则:
  页面类: XxxPage
  组件类: XxxWidget
  状态类: XxxState
  提供者类: XxxNotifier
  服务类: XxxService
  模型类: Xxx
  工具类: XxxUtils
  常量类: XxxConstants
  配置类: XxxConfig
  异常类: XxxException
```

#### 1.3 变量命名
```yaml
命名规则:
  常量: UPPER_SNAKE_CASE
  变量: camelCase
  私有变量: _camelCase
  布尔变量: is/has/can开头
  集合变量: 复数形式
  函数变量: 动词开头
```

#### 1.4 函数命名
```yaml
命名规则:
  公共函数: camelCase
  私有函数: _camelCase
  异步函数: async后缀或动词开头
  构造函数: 类名
  工厂函数: factory前缀
  扩展函数: 描述性命名
```

### 2. 代码风格

#### 2.1 格式化规范
```yaml
格式化规则:
  缩进: 2个空格
  行长度: 80字符
  空行: 逻辑分组
  括号: 同行开始
  分号: 必须添加
  引号: 单引号优先
```

#### 2.2 注释规范
```yaml
注释类型:
  文档注释:
    - 使用///格式
    - 描述类/函数功能
    - 包含参数说明
    - 包含返回值说明
    - 包含异常说明

  行内注释:
    - 使用//格式
    - 解释复杂逻辑
    - 说明业务规则
    - 标记TODO/FIXME
    - 避免重复代码说明

  块注释:
    - 使用/* */格式
    - 大段代码说明
    - 临时代码注释
    - 版权信息说明
```

### 3. 导入规范

#### 3.1 导入顺序
```dart
// 1. Dart SDK导入
import 'dart:async';
import 'dart:io';

// 2. Flutter框架导入
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// 3. 第三方包导入
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

// 4. 项目内部导入
import '../../core/design_system/colors/app_colors.dart';
import '../../core/design_system/typography/app_typography.dart';
import '../widgets/tab_navigation_widget.dart';
import '../providers/home_provider.dart';
```

#### 3.2 导入规则
```yaml
导入规则:
  相对路径:
    - 同级目录: ./filename
    - 上级目录: ../filename
    - 跨级目录: ../../filename

  绝对路径:
    - 项目根目录: package:quwoquan_app/...
    - 核心模块: package:quwoquan_app/core/...
    - 功能模块: package:quwoquan_app/features/...

  导入限制:
    - 避免深层嵌套导入
    - 避免循环导入
    - 避免未使用的导入
    - 避免重复导入
```

## 🔄 状态管理规范

### 1. Riverpod状态管理

#### 1.1 状态定义
```dart
// 状态类必须是不可变的
class HomeState {
  final bool isLoading;
  final List<Post> posts;
  final String? error;
  final int currentPage;
  final bool hasMore;
  
  const HomeState({
    required this.isLoading,
    required this.posts,
    this.error,
    required this.currentPage,
    required this.hasMore,
  });
  
  // 提供copyWith方法
  HomeState copyWith({
    bool? isLoading,
    List<Post>? posts,
    String? error,
    int? currentPage,
    bool? hasMore,
  }) {
    return HomeState(
      isLoading: isLoading ?? this.isLoading,
      posts: posts ?? this.posts,
      error: error ?? this.error,
      currentPage: currentPage ?? this.currentPage,
      hasMore: hasMore ?? this.hasMore,
    );
  }
  
  // 提供相等性比较
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is HomeState &&
        other.isLoading == isLoading &&
        other.posts == posts &&
        other.error == error &&
        other.currentPage == currentPage &&
        other.hasMore == hasMore;
  }
  
  @override
  int get hashCode {
    return isLoading.hashCode ^
        posts.hashCode ^
        error.hashCode ^
        currentPage.hashCode ^
        hasMore.hashCode;
  }
}
```

#### 1.2 提供者定义
```dart
// 使用StateNotifier进行复杂状态管理
class HomeNotifier extends StateNotifier<HomeState> {
  final DataService _dataService;
  
  HomeNotifier(this._dataService) : super(const HomeState(
    isLoading: false,
    posts: [],
    currentPage: 1,
    hasMore: true,
  ));
  
  // 异步操作必须有错误处理
  Future<void> loadPosts() async {
    try {
      state = state.copyWith(isLoading: true, error: null);
      final posts = await _dataService.getPosts(page: state.currentPage);
      state = state.copyWith(
        isLoading: false,
        posts: [...state.posts, ...posts],
        currentPage: state.currentPage + 1,
        hasMore: posts.isNotEmpty,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }
  
  Future<void> refreshPosts() async {
    state = state.copyWith(
      posts: [],
      currentPage: 1,
      hasMore: true,
    );
    await loadPosts();
  }
  
  void clearError() {
    state = state.copyWith(error: null);
  }
}

// 提供者定义
final homeProvider = StateNotifierProvider<HomeNotifier, HomeState>((ref) {
  final dataService = ref.watch(dataServiceProvider);
  return HomeNotifier(dataService);
});
```

#### 1.3 状态使用
```dart
// 在Widget中正确使用Provider
class HomePage extends ConsumerWidget {
  const HomePage({Key? key}) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final homeState = ref.watch(homeProvider);
    final homeNotifier = ref.read(homeProvider.notifier);
    
    // 监听状态变化
    ref.listen<HomeState>(homeProvider, (previous, next) {
      if (next.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next.error!)),
        );
      }
    });
    
    return Scaffold(
      appBar: AppBar(title: const Text('首页')),
      body: _buildBody(homeState, homeNotifier),
    );
  }
  
  Widget _buildBody(HomeState state, HomeNotifier notifier) {
    if (state.isLoading && state.posts.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    
    return RefreshIndicator(
      onRefresh: notifier.refreshPosts,
      child: ListView.builder(
        itemCount: state.posts.length + (state.hasMore ? 1 : 0),
        itemBuilder: (context, index) {
          if (index == state.posts.length) {
            return const Center(child: CircularProgressIndicator());
          }
          return PostCard(post: state.posts[index]);
        },
      ),
    );
  }
}
```

### 2. 状态管理最佳实践

#### 2.1 状态设计原则
```yaml
设计原则:
  不可变性:
    - 状态对象不可变
    - 使用copyWith更新
    - 避免直接修改状态
    - 提供相等性比较

  单一职责:
    - 每个状态类职责单一
    - 避免状态类过大
    - 合理拆分状态
    - 保持状态简洁

  可预测性:
    - 状态变化可预测
    - 避免副作用
    - 纯函数更新
    - 状态同步一致
```

#### 2.2 性能优化
```yaml
优化策略:
  选择性监听:
    - 使用select监听特定字段
    - 避免不必要的重建
    - 减少监听范围
    - 优化监听性能

  状态缓存:
    - 合理使用缓存
    - 避免重复计算
    - 缓存失效策略
    - 内存管理

  异步处理:
    - 合理使用异步
    - 避免阻塞UI
    - 错误处理完善
    - 取消机制支持
```

## 🔧 错误处理规范

### 1. 异常处理

#### 1.1 异常分类
```dart
// 自定义异常类
class AppException implements Exception {
  final String message;
  final String? code;
  final dynamic data;
  
  const AppException(this.message, {this.code, this.data});
  
  @override
  String toString() => 'AppException: $message';
}

class NetworkException extends AppException {
  const NetworkException(String message) : super(message, code: 'NETWORK_ERROR');
}

class ValidationException extends AppException {
  const ValidationException(String message) : super(message, code: 'VALIDATION_ERROR');
}

class AuthenticationException extends AppException {
  const AuthenticationException(String message) : super(message, code: 'AUTH_ERROR');
}

class BusinessException extends AppException {
  const BusinessException(String message) : super(message, code: 'BUSINESS_ERROR');
}
```

#### 1.2 异常处理模式
```dart
// 统一异常处理
class ErrorHandler {
  static void handleError(Object error, StackTrace stackTrace) {
    if (error is NetworkException) {
      _handleNetworkError(error);
    } else if (error is ValidationException) {
      _handleValidationError(error);
    } else if (error is AuthenticationException) {
      _handleAuthError(error);
    } else if (error is BusinessException) {
      _handleBusinessError(error);
    } else {
      _handleUnknownError(error, stackTrace);
    }
  }
  
  static void _handleNetworkError(NetworkException error) {
    // 网络错误处理
    Logger.error('Network error: ${error.message}');
    // 显示网络错误提示
  }
  
  static void _handleValidationError(ValidationException error) {
    // 验证错误处理
    Logger.warning('Validation error: ${error.message}');
    // 显示验证错误提示
  }
  
  static void _handleAuthError(AuthenticationException error) {
    // 认证错误处理
    Logger.error('Auth error: ${error.message}');
    // 跳转到登录页面
  }
  
  static void _handleBusinessError(BusinessException error) {
    // 业务错误处理
    Logger.warning('Business error: ${error.message}');
    // 显示业务错误提示
  }
  
  static void _handleUnknownError(Object error, StackTrace stackTrace) {
    // 未知错误处理
    Logger.error('Unknown error: $error', stackTrace);
    // 显示通用错误提示
  }
}
```

#### 1.3 异步操作错误处理
```dart
// 异步操作错误处理示例
class DataService {
  Future<List<Post>> getPosts({int page = 1}) async {
    try {
      final response = await _httpClient.get('/posts?page=$page');
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return (data['posts'] as List)
            .map((json) => Post.fromJson(json))
            .toList();
      } else {
        throw NetworkException('Failed to load posts: ${response.statusCode}');
      }
    } on SocketException {
      throw NetworkException('No internet connection');
    } on TimeoutException {
      throw NetworkException('Request timeout');
    } on FormatException {
      throw NetworkException('Invalid response format');
    } catch (e) {
      if (e is AppException) {
        rethrow;
      }
      throw NetworkException('Unexpected error: $e');
    }
  }
}
```

### 2. 错误显示

#### 2.1 错误状态管理
```dart
// 错误状态管理
class ErrorState {
  final String? message;
  final String? code;
  final DateTime timestamp;
  final bool isRetryable;
  
  const ErrorState({
    this.message,
    this.code,
    required this.timestamp,
    this.isRetryable = false,
  });
  
  ErrorState copyWith({
    String? message,
    String? code,
    DateTime? timestamp,
    bool? isRetryable,
  }) {
    return ErrorState(
      message: message ?? this.message,
      code: code ?? this.code,
      timestamp: timestamp ?? this.timestamp,
      isRetryable: isRetryable ?? this.isRetryable,
    );
  }
}

// 全局错误提供者
final globalErrorProvider = StateProvider<ErrorState?>((ref) => null);

// 错误处理提供者
final errorHandlerProvider = Provider<ErrorHandler>((ref) {
  return ErrorHandler();
});
```

#### 2.2 错误UI组件
```dart
// 错误显示组件
class ErrorWidget extends ConsumerWidget {
  final String? message;
  final VoidCallback? onRetry;
  final bool isRetryable;
  
  const ErrorWidget({
    Key? key,
    this.message,
    this.onRetry,
    this.isRetryable = false,
  }) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.error_outline,
            size: 64,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(height: 16),
          Text(
            message ?? 'Something went wrong',
            style: Theme.of(context).textTheme.bodyLarge,
            textAlign: TextAlign.center,
          ),
          if (isRetryable && onRetry != null) ...[
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          ],
        ],
      ),
    );
  }
}
```

## ⚡ 性能优化规范

### 1. 构建优化

#### 1.1 Widget优化
```dart
// 使用const构造函数
class PostCard extends StatelessWidget {
  final Post post;
  
  const PostCard({
    Key? key,
    required this.post,
  }) : super(key: key);
  
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        children: [
          Text(post.title),
          Text(post.content),
        ],
      ),
    );
  }
}

// 使用Consumer而不是Provider.of
class PostList extends ConsumerWidget {
  const PostList({Key? key}) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(postsProvider);
    return ListView.builder(
      itemCount: posts.length,
      itemBuilder: (context, index) {
        return PostCard(post: posts[index]);
      },
    );
  }
}

// 使用select优化监听
class PostCounter extends ConsumerWidget {
  const PostCounter({Key? key}) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(postsProvider.select((posts) => posts.length));
    return Text('Posts: $count');
  }
}
```

#### 1.2 列表优化
```dart
// 使用ListView.builder进行性能优化
class PostList extends ConsumerWidget {
  const PostList({Key? key}) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(postsProvider);
    
    return ListView.builder(
      itemCount: posts.length,
      // 使用itemExtent提高性能
      itemExtent: 200,
      // 使用cacheExtent控制缓存
      cacheExtent: 1000,
      itemBuilder: (context, index) {
        return PostCard(post: posts[index]);
      },
    );
  }
}

// 使用Sliver进行复杂列表优化
class PostSliverList extends ConsumerWidget {
  const PostSliverList({Key? key}) : super(key: key);
  
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(postsProvider);
    
    return CustomScrollView(
      slivers: [
        SliverAppBar(
          title: const Text('Posts'),
          floating: true,
        ),
        SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) => PostCard(post: posts[index]),
            childCount: posts.length,
          ),
        ),
      ],
    );
  }
}
```

### 2. 内存管理

#### 2.1 资源释放
```dart
// 及时释放资源
class PostDetailPage extends ConsumerStatefulWidget {
  final String postId;
  
  const PostDetailPage({
    Key? key,
    required this.postId,
  }) : super(key: key);
  
  @override
  ConsumerState<PostDetailPage> createState() => _PostDetailPageState();
}

class _PostDetailPageState extends ConsumerState<PostDetailPage> {
  StreamSubscription? _subscription;
  Timer? _timer;
  
  @override
  void initState() {
    super.initState();
    _loadPost();
    _startTimer();
  }
  
  @override
  void dispose() {
    _subscription?.cancel();
    _timer?.cancel();
    super.dispose();
  }
  
  void _loadPost() {
    _subscription = ref.read(postServiceProvider)
        .getPost(widget.postId)
        .listen((post) {
      // 处理数据
    });
  }
  
  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 30), (timer) {
      // 定时任务
    });
  }
}
```

#### 2.2 图片优化
```dart
// 图片缓存和优化
class OptimizedImage extends StatelessWidget {
  final String imageUrl;
  final double? width;
  final double? height;
  final BoxFit fit;
  
  const OptimizedImage({
    Key? key,
    required this.imageUrl,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
  }) : super(key: key);
  
  @override
  Widget build(BuildContext context) {
    return CachedNetworkImage(
      imageUrl: imageUrl,
      width: width,
      height: height,
      fit: fit,
      placeholder: (context, url) => const CircularProgressIndicator(),
      errorWidget: (context, url, error) => const Icon(Icons.error),
      memCacheWidth: width?.toInt(),
      memCacheHeight: height?.toInt(),
    );
  }
}
```

### 3. 网络优化

#### 3.1 请求优化
```dart
// HTTP客户端配置
class HttpClient {
  static late Dio _dio;
  
  static void init() {
    _dio = Dio(BaseOptions(
      baseUrl: AppConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      sendTimeout: const Duration(seconds: 10),
    ));
    
    // 添加拦截器
    _dio.interceptors.addAll([
      LogInterceptor(),
      AuthInterceptor(),
      ErrorInterceptor(),
      CacheInterceptor(),
    ]);
  }
  
  static Dio get instance => _dio;
}

// 请求缓存
class CacheInterceptor extends Interceptor {
  final Map<String, CacheEntry> _cache = {};
  
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (options.method == 'GET' && options.extra['cache'] == true) {
      final cacheKey = _getCacheKey(options);
      final cached = _cache[cacheKey];
      
      if (cached != null && !cached.isExpired) {
        final response = Response(
          data: cached.data,
          statusCode: 200,
          requestOptions: options,
        );
        handler.resolve(response);
        return;
      }
    }
    
    handler.next(options);
  }
  
  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    if (response.requestOptions.method == 'GET' && 
        response.requestOptions.extra['cache'] == true) {
      final cacheKey = _getCacheKey(response.requestOptions);
      _cache[cacheKey] = CacheEntry(
        data: response.data,
        timestamp: DateTime.now(),
        ttl: const Duration(minutes: 5),
      );
    }
    
    handler.next(response);
  }
}
```

## 🔒 安全编码规范

### 1. 数据安全

#### 1.1 敏感数据处理
```dart
// 敏感数据加密
class SecureStorage {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(
      encryptedSharedPreferences: true,
    ),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock_this_device,
    ),
  );
  
  static Future<void> storeToken(String token) async {
    await _storage.write(key: 'auth_token', value: token);
  }
  
  static Future<String?> getToken() async {
    return await _storage.read(key: 'auth_token');
  }
  
  static Future<void> deleteToken() async {
    await _storage.delete(key: 'auth_token');
  }
}

// 数据脱敏
class DataMasker {
  static String maskEmail(String email) {
    final parts = email.split('@');
    if (parts.length != 2) return email;
    
    final username = parts[0];
    final domain = parts[1];
    
    if (username.length <= 2) return email;
    
    final maskedUsername = username[0] + 
        '*' * (username.length - 2) + 
        username[username.length - 1];
    
    return '$maskedUsername@$domain';
  }
  
  static String maskPhone(String phone) {
    if (phone.length < 7) return phone;
    
    return phone.substring(0, 3) + 
        '****' + 
        phone.substring(phone.length - 4);
  }
}
```

#### 1.2 输入验证
```dart
// 输入验证工具
class InputValidator {
  static String? validateEmail(String? value) {
    if (value == null || value.isEmpty) {
      return 'Email is required';
    }
    
    final emailRegex = RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$');
    if (!emailRegex.hasMatch(value)) {
      return 'Please enter a valid email';
    }
    
    return null;
  }
  
  static String? validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required';
    }
    
    if (value.length < 8) {
      return 'Password must be at least 8 characters';
    }
    
    if (!RegExp(r'[A-Z]').hasMatch(value)) {
      return 'Password must contain at least one uppercase letter';
    }
    
    if (!RegExp(r'[a-z]').hasMatch(value)) {
      return 'Password must contain at least one lowercase letter';
    }
    
    if (!RegExp(r'[0-9]').hasMatch(value)) {
      return 'Password must contain at least one number';
    }
    
    return null;
  }
  
  static String? validatePhone(String? value) {
    if (value == null || value.isEmpty) {
      return 'Phone number is required';
    }
    
    final phoneRegex = RegExp(r'^\+?[1-9]\d{1,14}$');
    if (!phoneRegex.hasMatch(value)) {
      return 'Please enter a valid phone number';
    }
    
    return null;
  }
}
```

### 2. 网络安全

#### 2.1 证书验证
```dart
// 证书验证
class CertificateValidator {
  static bool validateCertificate(X509Certificate cert, String host, int port) {
    // 证书验证逻辑
    try {
      // 检查证书有效性
      if (cert.startValidity.isAfter(DateTime.now())) {
        return false;
      }
      
      if (cert.endValidity.isBefore(DateTime.now())) {
        return false;
      }
      
      // 检查主机名匹配
      if (!cert.subject.contains(host)) {
        return false;
      }
      
      return true;
    } catch (e) {
      Logger.error('Certificate validation failed: $e');
      return false;
    }
  }
}
```

#### 2.2 请求签名
```dart
// 请求签名
class RequestSigner {
  static String signRequest(String method, String url, Map<String, dynamic> params) {
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    final nonce = _generateNonce();
    
    final signatureData = '$method$url$timestamp$nonce';
    final signature = _hmacSha256(signatureData, AppConfig.apiSecret);
    
    return signature;
  }
  
  static String _generateNonce() {
    return Random.secure().nextInt(1000000).toString().padLeft(6, '0');
  }
  
  static String _hmacSha256(String data, String key) {
    // HMAC-SHA256签名实现
    return 'signature';
  }
}
```

## 📊 代码质量保证

### 1. 静态分析

#### 1.1 代码检查
```yaml
静态分析工具:
  Dart Analyzer:
    - 语法错误检查
    - 类型错误检查
    - 未使用变量检查
    - 死代码检查

  Lint规则:
    - 代码风格检查
    - 最佳实践检查
    - 性能问题检查
    - 安全问题检查

  自定义规则:
    - 项目特定规则
    - 团队约定规则
    - 业务逻辑规则
    - 架构约束规则
```

#### 1.2 代码复杂度
```yaml
复杂度控制:
  圈复杂度:
    - 函数复杂度 < 10
    - 类复杂度 < 20
    - 文件复杂度 < 50
    - 模块复杂度 < 100

  代码行数:
    - 函数行数 < 50
    - 类行数 < 500
    - 文件行数 < 1000
    - 模块行数 < 5000

  嵌套深度:
    - 条件嵌套 < 4层
    - 循环嵌套 < 3层
    - 函数嵌套 < 6层
    - 类嵌套 < 3层
```

### 2. 代码审查

#### 2.1 审查要点
```yaml
审查内容:
  功能正确性:
    - 业务逻辑正确
    - 边界条件处理
    - 异常情况处理
    - 性能影响评估

  代码质量:
    - 代码可读性
    - 代码可维护性
    - 代码可测试性
    - 代码复用性

  安全问题:
    - 数据安全
    - 输入验证
    - 权限控制
    - 敏感信息保护

  架构合规:
    - 模块划分合理
    - 依赖关系清晰
    - 接口设计规范
    - 设计模式使用
```

#### 2.2 审查流程
```yaml
审查流程:
  提交前检查:
    - 静态分析通过
    - 单元测试通过
    - 代码格式化
    - 提交信息规范

  审查过程:
    - 功能测试
    - 代码审查
    - 安全审查
    - 性能审查

  审查结果:
    - 通过: 合并代码
    - 修改: 修改后重新审查
    - 拒绝: 重新开发
    - 讨论: 团队讨论决定
```

## ✅ 编码验收标准

### 1. 代码质量验收
```yaml
验收标准:
  静态分析:
    - 静态分析通过率100%
    - 代码覆盖率>80%
    - 复杂度指标达标
    - 重复代码<5%

  功能测试:
    - 功能测试通过率100%
    - 单元测试通过率100%
    - 集成测试通过率>95%
    - 性能测试达标

  安全测试:
    - 安全漏洞0个
    - 敏感数据保护100%
    - 输入验证100%
    - 权限控制正确
```

### 2. 代码规范验收
```yaml
验收标准:
  编码规范:
    - 命名规范100%遵循
    - 代码风格100%一致
    - 注释覆盖>80%
    - 文档完整

  架构规范:
    - 模块划分合理
    - 依赖关系清晰
    - 接口设计规范
    - 设计模式正确

  性能规范:
    - 响应时间达标
    - 内存使用合理
    - 网络请求优化
    - 资源释放及时
```

## 📋 相关文档引用

### 1. 设计规则文档
- **文档名称**: [03_DESIGN_RULES.md](./03_DESIGN_RULES.md)
- **关联章节**: 设计系统实现、组件开发规范

### 2. 颜色检查清单文档
- **文档名称**: [04.1_DESIGN_COLOR_CHECKLIST.md](./04.1_DESIGN_COLOR_CHECKLIST.md)
- **关联内容**: 颜色系统实现和检查标准

### 3. API设计规则文档
- **文档名称**: [04.2_API_DESIGN_RULES.md](./04.2_API_DESIGN_RULES.md)
- **关联章节**: 
  - 1.1 端侧结构 (API客户端实现)
  - 1.2 云侧结构 (API服务端实现)
  - 3. 错误处理规范 (API错误处理)
  - 4. 性能优化规范 (API性能优化)

### 4. 测试规则文档
- **文档名称**: [05_TESTING_RULES.md](./05_TESTING_RULES.md)
- **关联章节**: 单元测试、集成测试、API测试

---

**创建时间**: 2024年12月19日  
**版本**: v1.0  
**技术负责人**: 技术负责人  
**代码审查员**: 高级开发工程师  
**关联文档**: [03_DESIGN_RULES.md](./03_DESIGN_RULES.md), [04.1_DESIGN_COLOR_CHECKLIST.md](./04.1_DESIGN_COLOR_CHECKLIST.md), [04.2_API_DESIGN_RULES.md](./04.2_API_DESIGN_RULES.md)  
**下次评审**: 2025年1月19日
