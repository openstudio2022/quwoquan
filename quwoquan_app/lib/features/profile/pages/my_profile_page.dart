// ignore_for_file: unused_field, unused_local_variable, unused_element, sized_box_for_whitespace

import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 我的主页页面 - 基于作者主页实现
class MyProfilePage extends ConsumerWidget {
  const MyProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _MyProfileContent();
  }
}

/// 我的主页内容组件 - 复制自AuthorProfile
class _MyProfileContent extends ConsumerStatefulWidget {
  @override
  ConsumerState<_MyProfileContent> createState() => _MyProfileContentState();
}

class _MyProfileContentState extends ConsumerState<_MyProfileContent> with TickerProviderStateMixin {
  late ScrollController _scrollController;
  late AnimationController _fadeController;
  late AnimationController _pullController; // 下拉动画控制器
  
  int _mainTabIndex = 0; // 0=创作 1=互动 2=生活
  int _subTabIndex = 0;  // 创作: 全部/图片/视频/文章; 生活: 足迹/书影音/味蕾/爱物
  bool _showStickyHeader = false;
  bool _showStickyButtons = false;
  bool _isFollowing = false;
  bool _loading = true;
  String? _error;
  
  // 下拉吸顶效果相关
  double _pullOffset = 0.0; // 经过弹簧效果处理后的有效下拉距离
  double _rawPullOffset = 0.0; // 用户原始下拉距离（用于弹簧计算）
  bool _isPulling = false;
  bool _isPullingDown = false; // 是否正在下拉
  double _maxPullHeight = 0.0;
  
  // 图片加载状态
  bool _isImageLoaded = false;
  double? _actualImageWidth;
  double? _actualImageHeight;
  
  // 用户数据
  User? _userData;
  
  // 常量定义
  static const double kDefaultAspectRatio = 4.0 / 3.0;  // 占位图比例
  static const double kContentStaticRatio = 0.25;       // 内容区静态位置（1/4）
  static const double kContentMaxRatio = 0.50;          // 内容区最大位置（1/2）
  static const double kBackgroundMinRatio = 0.25;       // 背景最小高度（1/4）
  static const double kBackgroundMaxRatio = 0.25;       // 🔑 背景最大高度（1/4）- 静止状态固定1/4
  
  // 吸顶相关
  final GlobalKey _profileInfoKey = GlobalKey();
  final GlobalKey _buttonsKey = GlobalKey();
  final GlobalKey _backgroundKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _pullController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    // 需要 TickerProvider，暂时使用 mixin
    
    _setupScrollListener();
    _setupPullListener();
    
    // 延迟加载用户数据，避免在initState中修改provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadUserData();
      _calculateMaxPullHeight();
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _fadeController.dispose();
    _pullController.dispose();
    
    // 恢复默认状态栏设置
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
    
    super.dispose();
  }

  /// 加载用户数据
  void _loadUserData() async {
    try {
      final userDataNotifier = ref.read(userDataProvider.notifier);
      await userDataNotifier.loadUser('我的账号');
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '加载用户数据失败: $e';
      });
    }
  }

  /// 加载图片尺寸
  void _loadImageSize() async {
    final imageUrl = _userData?.backgroundImage;
    if (imageUrl == null || imageUrl.isEmpty) {
      setState(() {
        _isImageLoaded = true; // 无图片，使用占位高度
      });
      return;
    }
    
    try {
      final NetworkImage provider = NetworkImage(imageUrl);
      final ImageStream stream = provider.resolve(ImageConfiguration.empty);
      
      stream.addListener(
        ImageStreamListener(
          (ImageInfo info, bool synchronousCall) {
            if (mounted) {
              setState(() {
                _actualImageWidth = info.image.width.toDouble();
                _actualImageHeight = info.image.height.toDouble();
                _isImageLoaded = true;
              });
              
            }
          },
          onError: (exception, stackTrace) {
            if (mounted) {
              setState(() {
                _isImageLoaded = true; // 加载失败，使用占位高度
              });
            }
          },
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          _isImageLoaded = true;
        });
      }
    }
  }

  /// 生成模拟帖子数据
  List<Map<String, dynamic>> _generateMockPosts() {
    final types = ['image', 'video', 'moment', 'article'];
    final tags = [
      ['生活', '日常'],
      ['摄影', '风光'],
      ['视频', '分享'],
      ['文章', '思考'],
      ['生活', '日常'],
    ];
    
    return List.generate(20, (index) {
      final type = types[index % types.length];
      final postTags = tags[index % tags.length];
      
      return {
      'id': 'post_$index',
      'username': '我的账号',
        'type': type,
        'caption': type == 'article' 
            ? '这是一篇长文章，包含了很多内容和思考。' * (3 + index % 3)
            : '这是第${index + 1}个${type == 'image' ? '图片' : type == 'video' ? '视频' : type == 'moment' ? '动态' : '文章'}',
        'images': type == 'video' 
            ? ['https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=300&h=400&fit=crop']
            : ['https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=300&h=${300 + (index % 3) * 100}&fit=crop'],
      'likesCount': 10 + index,
      'commentsCount': 5 + index,
      'savesCount': 2 + index,
        'tags': postTags,
      'createdAt': DateTime.now().subtract(Duration(hours: index)).toIso8601String(),
      };
    });
  }

  /// 设置滚动监听
  void _setupScrollListener() {
    _scrollController.addListener(() {
      _updateStickyStates();
    });
  }

  /// 处理滚动通知 - 实现背景图拉伸效果
  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final scrollOffset = notification.metrics.pixels;
      
      setState(() {
        if (scrollOffset < 0) {
          // 下拉状态：应用弹簧阻尼效果
          _isPullingDown = true;
          _rawPullOffset = -scrollOffset;
          final maxContentPull = _getContentPullSpace();
          
          // 🔑 关键：使用弹簧阻尼函数处理下拉距离
          _pullOffset = _getSpringPullOffset(_rawPullOffset, maxContentPull);
          
        } else {
          // 正常或上推
          _isPullingDown = false;
          _rawPullOffset = 0;
          _pullOffset = 0;
        }
      });
    }
    
    return false;
  }

  // ==================== 新的高度计算方法 ====================
  
  /// 1. 获取屏幕尺寸（辅助方法）
  double _getScreenWidth() => MediaQuery.of(context).size.width;
  double _getScreenHeight() => MediaQuery.of(context).size.height;
  double _getPaddingTop() => MediaQuery.of(context).padding.top;

  /// 弹簧阻尼函数 - 模拟弹簧重力效果
  /// rawPullOffset: 用户原始下拉距离
  /// maxEffectivePull: 内容区可拉伸的最大距离
  /// 返回: 经过弹簧效果处理后的有效下拉距离
  double _getSpringPullOffset(double rawPullOffset, double maxEffectivePull) {
    if (rawPullOffset <= 0) return 0.0;
    if (maxEffectivePull <= 0) return 0.0;
    
    // 弹簧阻尼系数：控制弹簧的"硬度"
    // 值越小，阻尼越大，需要更大的原始下拉才能达到相同的效果
    final double dampingFactor = maxEffectivePull / 1.2; // 经验值，可调整
    
    // 使用指数衰减函数模拟弹簧效果
    // 当 rawPullOffset 较小时，接近线性关系
    // 当 rawPullOffset 较大时，趋于饱和，产生阻尼感
    final double springEffect = 1.0 - exp(-rawPullOffset / dampingFactor);
    
    // 确保结果在 [0, maxEffectivePull] 范围内
    final double result = (maxEffectivePull * springEffect).clamp(0.0, maxEffectivePull);
    
    
    return result;
  }

  /// 2. 计算图片原始高度（基于宽高比）
  double _getRawImageHeight() {
    if (!_isImageLoaded || _actualImageWidth == null || _actualImageHeight == null) {
      // 未加载：使用4:3占位
      return _getScreenWidth() / kDefaultAspectRatio;
    }
    
    // 已加载：根据实际比例
    final aspectRatio = _actualImageWidth! / _actualImageHeight!;
    return _getScreenWidth() / aspectRatio;
  }

  /// 3. 计算背景图初始高度（应用限制）
  double _getBackgroundInitialHeight() {
    final screenHeight = _getScreenHeight();
    final rawHeight = _getRawImageHeight();
    final minHeight = screenHeight * kBackgroundMinRatio;
    final maxHeight = screenHeight * kBackgroundMaxRatio;
    
    // 应用范围限制
    return rawHeight.clamp(minHeight, maxHeight);
  }

  /// 4. 获取内容区静态顶部位置（固定）
  double _getContentStaticTop() {
    return _getScreenHeight() * kContentStaticRatio;
  }

  /// 5. 获取内容区最大顶部位置（固定）
  double _getContentMaxTop() {
    return _getScreenHeight() * kContentMaxRatio;
  }

  /// 6. 获取内容区可拉伸空间（固定）
  double _getContentPullSpace() {
    return _getContentMaxTop() - _getContentStaticTop();
  }

  /// 7. 获取背景图可拉伸空间
  double _getBackgroundPullSpace() {
    final maxHeight = _getScreenHeight() * kBackgroundMaxRatio;
    final initialHeight = _getBackgroundInitialHeight();
    return (maxHeight - initialHeight).clamp(0.0, double.infinity);
  }

  /// 8. 计算拉伸比例
  double _getStretchRatio() {
    final contentSpace = _getContentPullSpace();
    final backgroundSpace = _getBackgroundPullSpace();
    
    if (backgroundSpace <= 0) {
      return double.infinity; // 背景无法拉伸
    }
    
    return contentSpace / backgroundSpace;
  }

  /// 9. 计算内容区实际下拉距离
  double _getContentPullOffset() {
    // _pullOffset 已经通过弹簧函数处理，并且弹簧函数内部已经确保了不会超过 maxContentPull
    // 这里不需要再次 clamp，直接返回即可
    final result = _pullOffset;
    
    // 调试：验证内容区限制
    final maxPull = _getContentPullSpace();
    final staticTop = _getContentStaticTop();
    final currentTop = staticTop + result;
    final maxTop = _getContentMaxTop();
    
    
    return result;
  }

  /// 10. 计算背景图实际拉伸距离
  double _getBackgroundPullOffset() {
    final ratio = _getStretchRatio();
    
    if (ratio.isInfinite) {
      return 0.0; // 背景无法拉伸
    }
    
    final contentPull = _getContentPullOffset();
    return contentPull / ratio;
  }

  /// 11. 获取当前背景图高度（固定，不随拉伸变化）
  double _getCurrentBackgroundHeight() {
    final paddingTop = _getPaddingTop();
    final screenHeight = _getScreenHeight();
    
    // 🔑 关键：背景容器高度固定为屏幕1/4 + paddingTop
    // 不依赖图像实际比例，确保始终为屏幕1/4
    final backgroundHeight = screenHeight * 0.25;
    
    
    return paddingTop + backgroundHeight;
  }

  /// 12. 获取当前内容区顶部位置（含拉伸）
  double _getCurrentContentTop() {
    // 🔑 关键：内容区顶部位置 = 占位高度 = 背景容器高度
    // 这样确保内容区顶部始终与背景容器底部对齐
    final result = _getCurrentBackgroundHeight();
    
    
    return result;
  }

  /// 13. 获取占位空间高度（确保内容在正确位置）
  double _getPlaceholderHeight() {
    final backgroundHeight = _getCurrentBackgroundHeight();
    final scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    // 🔑 关键：占位高度计算逻辑重构
    // 我们要确保：内容区的视觉顶部 (visualTop) 始终等于 背景图的视觉底部 (visualBottom)
    // 1. visualTop = placeholderHeight - scrollOffset
    // 2. visualBottom = backgroundTop + backgroundHeight * scale
    // 3. 下拉时 backgroundTop = 0, scale = 1.0 + (_pullOffset / (backgroundHeight * 2))
    // 所以 visualBottom = backgroundHeight + _pullOffset / 2
    
    // 联立等式：placeholderHeight - scrollOffset = backgroundHeight + _pullOffset / 2
    // 得出：placeholderHeight = backgroundHeight + _pullOffset / 2 + scrollOffset
    
    double totalHeight;
    if (scrollOffset < 0) {
      // 下拉状态：精确对齐背景图底部
      // 注意：scrollOffset 是负值，所以这里用 + scrollOffset 会减小高度，抵消 CustomScrollView 的物理下移
      totalHeight = backgroundHeight + (_pullOffset / 2) + scrollOffset;
    } else {
      // 正常或上推状态：占位高度固定为背景高度
      totalHeight = backgroundHeight;
    }
    
    
    // 🔑 关键：确保高度不为负数
    return totalHeight.clamp(0.0, double.infinity);
  }

  /// 14. 容错：确保背景底部≥内容顶部
  double _getSafeBackgroundHeight() {
    // 🔑 关键：直接返回背景容器高度，避免循环依赖
    return _getCurrentBackgroundHeight();
  }

  /// 设置下拉监听
  void _setupPullListener() {
    _scrollController.addListener(() {
      if (_scrollController.position.pixels < 0) {
        setState(() {
          _rawPullOffset = -_scrollController.position.pixels;
          final maxContentPull = _getContentPullSpace();
          // 🔑 使用弹簧阻尼函数处理下拉距离
          _pullOffset = _getSpringPullOffset(_rawPullOffset, maxContentPull);
          _isPulling = true;
        });
      } else if (_isPulling) {
        setState(() {
          _isPulling = false;
          _rawPullOffset = 0;
          _pullOffset = 0;
        });
        _animatePullBack();
      }
    });
  }

  /// 计算最大下拉高度
  void _calculateMaxPullHeight() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final screenHeight = MediaQuery.of(context).size.height;
        // 最大下拉距离 = 内容可拉伸空间 = 屏幕高度 × 0.25
        _maxPullHeight = screenHeight * (kContentMaxRatio - kContentStaticRatio);
      }
    });
  }

  /// 动画回弹
  void _animatePullBack() {
    if (_pullOffset > 0) {
      _pullController.forward().then((_) {
        _pullController.reset();
        setState(() {
          _pullOffset = 0.0;
        });
      });
    }
  }

  /// 更新吸顶状态
  void _updateStickyStates() {
    if (_profileInfoKey.currentContext != null) {
      final RenderBox renderBox = _profileInfoKey.currentContext!.findRenderObject() as RenderBox;
      final position = renderBox.localToGlobal(Offset.zero);
      
      setState(() {
        _showStickyHeader = position.dy < 100;
      });
    }
    
    if (_buttonsKey.currentContext != null) {
      final RenderBox renderBox = _buttonsKey.currentContext!.findRenderObject() as RenderBox;
      final position = renderBox.localToGlobal(Offset.zero);
      
      setState(() {
        _showStickyButtons = position.dy < 150;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    // 强制设置状态栏为完全透明
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
    
    // 确保状态栏完全透明，移除任何覆盖层
    WidgetsBinding.instance.addPostFrameCallback((_) {
      SystemChrome.setSystemUIOverlayStyle(
        const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
        ),
      );
    });
    
    // 监听用户数据provider状态变化
    ref.listen(userDataProvider, (previous, next) {
      if (next != null) {
        setState(() {
          _userData = next;
          _isFollowing = next.isFollowing ?? false;
          _loading = false;
          _error = null;
        });
        // 用户数据加载后，重新加载图片尺寸
        _loadImageSize();
      } else {
        setState(() {
          _loading = false;
          _error = '用户不存在';
        });
      }
    });
    
    if (_loading) {
      return _buildLoadingState(isDark);
    }
    
    if (_error != null) {
      return _buildErrorState(isDark);
    }
    
    return Scaffold(
      backgroundColor: Colors.transparent,
      extendBodyBehindAppBar: true, // 🔑 关键：允许内容侵入状态栏
      body: AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
        ),
        child: Stack(
          children: [
            // 底层：可滚动的内容区域 - 背景图跟随滚动
            _buildScrollableContent(isDark),
            
            // 顶层：悬浮层
            // 顶部工具栏
            _buildTopToolbar(isDark),
          ],
        ),
      ),
    );
  }

  /// 构建加载状态
  Widget _buildLoadingState(bool isDark) {
    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(16.w),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(
                  color: AppColors.primaryColor,
                ),
                SizedBox(height: 16.h),
                Text(
                  '加载中...',
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                    fontSize: 16.sp,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 构建错误状态
  Widget _buildErrorState(bool isDark) {
    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(AppSpacing.md.w),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.error_outline,
                  size: (AppSpacing.iconLarge * 2).sp,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                ),
                SizedBox(height: AppSpacing.md.h),
                Text(
                  UITextConstants.loadFailed,
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                    fontSize: 18.sp,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(height: AppSpacing.sm.h),
                Text(
                  _error ?? UITextConstants.unknown,
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                    fontSize: 14.sp,
                  ),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: AppSpacing.lg.h),
                ElevatedButton(
                  onPressed: _loadUserData,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primaryColor,
                    foregroundColor: AppColors.white,
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg.w,
                      vertical: AppSpacing.md.h,
                    ),
                  ),
                  child: Text(UITextConstants.retry),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 15. 获取背景图top位置（支持上推和下拉）
  double _getBackgroundTop() {
    final scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    if (_pullOffset > 0) {
      // 🔑 关键：下拉时，背景图顶部固定在屏幕顶部
      return 0;
    } else if (scrollOffset > 0) {
      // 上推：背景图跟随上移
      return -(scrollOffset.clamp(0.0, _getSafeBackgroundHeight()));
    } else {
      // 正常状态：固定在屏幕顶部
      return 0;
    }
  }

  /// 构建可滚动的内容区域 - 全局Stack架构
  Widget _buildScrollableContent(bool isDark) {
    return Stack(
      children: [
        // 1. 底层：全局背景图 (Positioned)
        Positioned(
          top: _getBackgroundTop(),
          left: 0,
          right: 0,
          height: _getSafeBackgroundHeight(),
          child: Transform.scale(
            scale: _pullOffset > 0 ? 1.0 + (_pullOffset / (_getSafeBackgroundHeight() * 2)) : 1.0, // 🔑 拉伸时图像缩放
            alignment: Alignment.topCenter, // 🔑 从顶部开始缩放
            child: Container(
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary), // 占位背景色
                image: DecorationImage(
                  image: NetworkImage(_userData?.backgroundImage ?? 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop'),
                  fit: BoxFit.cover, // 🔑 居中缩放裁剪
                  alignment: Alignment.topCenter, // 🔑 从顶部对齐，确保填满容器
                  onError: (exception, stackTrace) {
                  },
                ),
              ),
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      AppColors.overlayMedium,
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        
        // 2. 中层：可滚动内容 (Positioned)
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          child: NotificationListener<ScrollNotification>(
            onNotification: _handleScrollNotification,
            child: CustomScrollView(
              controller: _scrollController,
              physics: const BouncingScrollPhysics(), // 支持下拉回弹
              slivers: [
                // 占位Sliver（确保内容在正确位置）
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: _getPlaceholderHeight(), // 🔑 动态占位高度
                  ),
                ),
                
                // 用户区（含头像）
                SliverToBoxAdapter(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
                      borderRadius: BorderRadius.only(
                        topLeft: Radius.circular(AppSpacing.borderRadius.r),
                        topRight: Radius.circular(AppSpacing.borderRadius.r),
                      ),
                    ),
                    child: Stack(
                      clipBehavior: Clip.none, // 🔑 允许头像溢出容器边界
                      children: [
                        // 用户信息内容
                        Padding(
                          padding: EdgeInsets.only(
                            top: 60.h, // 为头像留出空间
                            left: AppSpacing.md.w,
                            right: AppSpacing.md.w,
                            bottom: AppSpacing.md.h,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min, // 🔑 关键：最小高度，根据内容自适应
                            children: [
                              _buildUserInfo(isDark),
                              SizedBox(height: AppSpacing.md.h),
                              _buildResonanceCard(isDark),
                              SizedBox(height: AppSpacing.md.h),
                              _buildStatsSection(isDark),
                              _buildActionButtons(isDark),
                            ],
                          ),
                        ),
                        
                        // 头像（向上偏移，侵入背景图）
                        Positioned(
                          top: 0,
                          left: AppSpacing.md.w,
                          child: Transform.translate(
                            offset: Offset(0, -45.h), // 🔑 关键：增加向上偏移量，确保头像完全在背景之上
                            child: Container(
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: AppColors.white,
                                  width: 3.w,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: AppColors.overlayLight,
                                    blurRadius: 8.r,
                                    offset: Offset(0, 2.h),
                                  ),
                                ],
                              ),
                              child: CircleAvatar(
                                radius: 45.r,
                                backgroundImage: _userData?.avatar != null && _userData!.avatar!.isNotEmpty
                                    ? NetworkImage(_userData!.avatar!)
                                    : null,
                                onBackgroundImageError: null,
                                child: _userData?.avatar == null || _userData!.avatar!.isEmpty
                                    ? Icon(
                                        Icons.person,
                                        size: 32.sp,
                                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
                                      )
                                    : null,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                
                // Tab导航 + 网格内容
                SliverToBoxAdapter(
                  child: Container(
                    color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
                    child: Column(
                      children: [
                        _buildTabNavigation(isDark),
                        _buildTabContent(isDark),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  /// 构建用户信息
  Widget _buildUserInfo(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: AppSpacing.md.h,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                _userData!.displayName ?? '',
                style: TextStyle(
                  fontSize: 20.sp, // 调整用户名字体从24.sp到20.sp
                  fontWeight: FontWeight.bold,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                ),
              ),
              if (_userData!.isVerified == true) ...[
                SizedBox(width: AppSpacing.xs.w),
                Container(
                  padding: EdgeInsets.all(2.w),
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.check,
                    size: 12.sp,
                    color: AppColors.white,
                  ),
                ),
              ],
            ],
          ),
          SizedBox(height: AppSpacing.xs.h),
          Text(
            '@${_userData!.username}',
            style: TextStyle(
              fontSize: 16.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
          ),
          SizedBox(height: AppSpacing.sm.h),
          Text(
            _userData!.bio ?? '这个人很懒，什么都没有写',
            style: TextStyle(
              fontSize: 14.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  /// 交集卡片（1:1 MyProfilePage.tsx「本周有 128 位趣友与你有交集」）
  Widget _buildResonanceCard(bool isDark) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return InkWell(
      onTap: _handleResonance,
      borderRadius: BorderRadius.circular(24.r),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md.w,
          vertical: AppSpacing.md.h,
        ),
        decoration: BoxDecoration(
          color: AppColors.primaryColor.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(24.r),
          border: Border.all(
            color: AppColors.primaryColor.withValues(alpha: 0.2),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                SizedBox(
                  width: 36.w,
                  height: 36.w,
                  child: CircleAvatar(
                    backgroundColor: AppColorsFunctional.getColor(
                        isDark, ColorType.backgroundSecondary),
                    child: Icon(Icons.people_outline,
                        size: 18.sp, color: fg),
                  ),
                ),
                SizedBox(width: 12.w),
                Text(
                  '本周有 ',
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w600,
                    color: fg,
                  ),
                ),
                Text(
                  '128',
                  style: TextStyle(
                    fontSize: 18.sp,
                    fontWeight: FontWeight.w900,
                    color: AppColors.primaryColor,
                  ),
                ),
                Text(
                  ' 位趣友与你有交集',
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w600,
                    color: fg,
                  ),
                ),
              ],
            ),
            Icon(
              Icons.chevron_right,
              size: 20.sp,
              color: AppColors.primaryColor.withValues(alpha: 0.6),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建统计信息区域（1:1 Figma：关注 | 圈子 | 粉丝 | 获赞，点击进入对应列表）
  Widget _buildStatsSection(bool isDark) {
    if (_userData == null) {
      return Container(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        ),
        child: Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
          ),
        ),
      );
    }
    final followingCount = _userData!.following ?? 128;
    const circlesCount = 12;
    const fansCount = 456;
    final likesCount = _userData!.likes ?? 4200;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md.w,
        vertical: AppSpacing.sm.h,
      ),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary)
                .withValues(alpha: 0.3),
          ),
        ),
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          InkWell(
            onTap: () => _handleStats('following'),
            borderRadius: BorderRadius.circular(8.r),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8.h, horizontal: 12.w),
              child: _buildStatItem(UITextConstants.follow, followingCount, isDark),
            ),
          ),
          InkWell(
            onTap: () {},
            borderRadius: BorderRadius.circular(8.r),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8.h, horizontal: 12.w),
              child: _buildStatItem('圈子', circlesCount, isDark),
            ),
          ),
          InkWell(
            onTap: () => _handleStats('fans'),
            borderRadius: BorderRadius.circular(8.r),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8.h, horizontal: 12.w),
              child: _buildStatItem(UITextConstants.circleFans, fansCount, isDark),
            ),
          ),
          InkWell(
            onTap: () => _handleStats('likes'),
            borderRadius: BorderRadius.circular(8.r),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8.h, horizontal: 12.w),
              child: _buildStatItem(UITextConstants.circleLikes, likesCount, isDark),
            ),
          ),
        ],
      ),
    );
  }

  /// 构建统计项目
  Widget _buildStatItem(String label, int count, bool isDark) {
    return Column(
      children: [
        Text(
          _formatCount(count),
          style: TextStyle(
            fontSize: 18.sp,
            fontWeight: FontWeight.bold,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          ),
        ),
        SizedBox(height: 4.h),
        Text(
          label,
          style: TextStyle(
            fontSize: 14.sp,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
          ),
        ),
      ],
    );
  }

  /// 构建操作按钮区域（含 PersonaSwitcher 1:1 对应 PersonaSwitcher.tsx）
  Widget _buildActionButtons(bool isDark) {
    return Container(
      key: _buttonsKey,
      padding: EdgeInsets.all(AppSpacing.md.w),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 身份/分身切换
          Align(
            alignment: Alignment.centerLeft,
            child: InkWell(
              onTap: () => _showPersonaMenu(context, isDark),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius.r),
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: 4.h, horizontal: 8.w),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      UITextConstants.personaPrimary,
                      style: TextStyle(
                        fontSize: 14.sp,
                        fontWeight: FontWeight.w500,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                    SizedBox(width: 4.w),
                    Icon(
                      Icons.keyboard_arrow_down,
                      size: 18.sp,
                      color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(height: 8.h),
          Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // 资料编辑（1:1 Figma 浅灰 pill）
          Material(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
            borderRadius: BorderRadius.circular(24.r),
            child: InkWell(
              onTap: _handleEditProfile,
              borderRadius: BorderRadius.circular(24.r),
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: 24.w,
                  vertical: 12.h,
                ),
                child: Text(
                  UITextConstants.profileEditLabel,
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w800,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundSecondary),
                  ),
                ),
              ),
            ),
          ),
          SizedBox(width: 10.w),
          // 分身管理（1:1 Figma 深灰 pill）
          Material(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
            borderRadius: BorderRadius.circular(24.r),
            child: InkWell(
              onTap: _handlePersonas,
              borderRadius: BorderRadius.circular(24.r),
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: 24.w,
                  vertical: 12.h,
                ),
                child: Text(
                  UITextConstants.profilePersonasLabel,
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w800,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundPrimary),
                  ),
                ),
              ),
            ),
          ),
          SizedBox(width: 10.w),
          // 私人助理入口（1:1 Figma 纯图标，无蓝底）
          GestureDetector(
            onTap: _handleAssistantEntry,
            child: Container(
              width: 40.w,
              height: 40.w,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.transparent,
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.auto_awesome,
                size: AppSpacing.iconMedium.sp,
                color: AppColors.primaryColor,
              ),
            ),
          ),
          // 设置入口在顶栏，此处仅保留 资料编辑 | 分身管理 | 私人助理（1:1 Figma）
        ],
      ),
        ],
      ),
    );
  }

  void _showPersonaMenu(BuildContext context, bool isDark) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppSpacing.borderRadius.r)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(Icons.person, color: AppColors.primaryColor),
              title: Text(UITextConstants.personaPrimary),
              onTap: () {
                Navigator.pop(ctx);
              },
            ),
            ListTile(
              leading: Icon(Icons.settings, color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)),
              title: Text(UITextConstants.personaManage),
              onTap: () {
                Navigator.pop(ctx);
                context.push('/profile/personas');
              },
            ),
          ],
        ),
      ),
    );
  }

  /// 构建Tab导航：主 Tab（创作/互动/生活）+ 子 Tab（按主 Tab 切换）
  Widget _buildTabNavigation(bool isDark) {
    const mainTabs = [
      AppConceptConstants.creation,
      AppConceptConstants.interaction,
      AppConceptConstants.life,
    ];
    const creationSubTabs = [
      AppConceptConstants.all,
      AppConceptConstants.images,
      AppConceptConstants.videos,
      AppConceptConstants.articles,
    ];
    const lifeSubTabs = [
      AppConceptConstants.footprint,
      AppConceptConstants.bookMovieMusic,
      AppConceptConstants.taste,
      AppConceptConstants.aiwu,
    ];

    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: 1,
          ),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 主 Tab 行
          SizedBox(
            height: AppSpacing.tabNavigationHeight.h,
            child: Row(
              children: List.generate(mainTabs.length, (i) {
                final isActive = i == _mainTabIndex;
                return Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() {
                      _mainTabIndex = i;
                      _subTabIndex = 0;
                    }),
                    child: Center(
                      child: Text(
                        mainTabs[i],
                        style: TextStyle(
                          fontSize: 14.sp,
                          fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                          color: isActive
                              ? AppColors.primaryColor
                              : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
          // 子 Tab 行（创作、生活有子分类）
          if (_mainTabIndex == 0 || _mainTabIndex == 2) ...[
            Container(
              height: AppSpacing.subTabNavigationHeight.h,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm.w),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: List.generate(
                    _mainTabIndex == 0 ? creationSubTabs.length : lifeSubTabs.length,
                    (i) {
                      final label = _mainTabIndex == 0 ? creationSubTabs[i] : lifeSubTabs[i];
                      final isActive = i == _subTabIndex;
                      return GestureDetector(
                        onTap: () => setState(() => _subTabIndex = i),
                        child: Container(
                          margin: EdgeInsets.only(right: AppSpacing.xs.w),
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.sm.w,
                            vertical: AppSpacing.xs.h,
                          ),
                          decoration: BoxDecoration(
                            color: isActive
                                ? AppColorsFunctional.getColor(isDark, ColorType.selectionBackground)
                                : Colors.transparent,
                            borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius.r),
                            border: isActive
                                ? Border.all(
                                    color: AppColorsFunctional.getColor(isDark, ColorType.selectionBorder),
                                    width: 1.0,
                                  )
                                : null,
                          ),
                          child: Center(
                            child: Text(
                              label,
                              style: TextStyle(
                                fontSize: 12.sp,
                                fontWeight: isActive ? FontWeight.w500 : FontWeight.normal,
                                color: isActive
                                    ? AppColorsFunctional.getColor(isDark, ColorType.selectionForeground)
                                    : AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// 构建Tab内容区域
  Widget _buildTabContent(bool isDark) {
    return Container(
      height: 600.h, // 固定高度，避免无限高度问题
      child: _buildSimplePostsGrid(isDark),
    );
  }

  /// 构建简单的作品网格 - 兼容Column布局
  Widget _buildSimplePostsGrid(bool isDark) {
    final posts = _generateMockPosts();
    return GridView.builder(
      padding: EdgeInsets.all(AppSpacing.md.w),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: AppSpacing.sm.w,
        mainAxisSpacing: AppSpacing.sm.h,
        childAspectRatio: 0.8,
      ),
      itemCount: posts.length,
      itemBuilder: (context, index) {
        final post = posts[index];
        return _buildSimplePostItem(post, isDark);
      },
    );
  }

  /// 构建简单的作品项
  Widget _buildSimplePostItem(Map<String, dynamic> post, bool isDark) {
    final images = post['images'] as List<String>?;
    final type = post['type'] as String;
    
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: BorderRadius.circular(8.r),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8.r),
        child: images != null && images.isNotEmpty
            ? Image.network(
                images.first,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) {
                  return Container(
                    color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                    child: Icon(
                      type == 'video' ? Icons.play_circle_outline : Icons.image,
                      size: 40.sp,
                      color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
                    ),
                  );
                },
              )
            : Container(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                child: Icon(
                  type == 'video' ? Icons.play_circle_outline : Icons.image,
                  size: 40.sp,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
                ),
              ),
      ),
    );
  }

  /// 构建顶部工具栏
  Widget _buildTopToolbar(bool isDark) {
    return Positioned(
      top: 50.h,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md.w,
          vertical: AppSpacing.sm.h,
        ),
        decoration: BoxDecoration(
          color: Colors.transparent, // 移除黑色渐变背景，避免状态栏覆盖层
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.end, // 右对齐，只显示设置按钮
          children: [
            // 设置按钮
            GestureDetector(
              onTap: _handleSettings,
              child: Container(
                padding: EdgeInsets.all(AppSpacing.sm.w),
                decoration: BoxDecoration(
                  color: AppColors.overlayMedium, // 更透明的背景
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: AppColors.overlayLight,
                    width: 1,
                  ),
                ),
                child: Icon(
                  Icons.settings,
                  color: AppColors.white,
                  size: AppSpacing.iconMedium.sp,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 显示更多选项
  void _showMoreOptions() {
    // 添加mounted检查，防止在widget销毁后访问ref
    if (!mounted) return;
    
    final isDark = ref.watch(isDarkProvider);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(20.r),
            topRight: Radius.circular(20.r),
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40.w,
              height: 4.h,
              margin: EdgeInsets.only(top: 12.h, bottom: 20.h),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
                borderRadius: BorderRadius.circular(2.r),
              ),
            ),
            _buildMoreOptionItem(Icons.edit, '编辑资料', isDark, () => _handleEditProfile()),
            _buildMoreOptionItem(Icons.settings, '设置', isDark, () => _handleSettings()),
            _buildMoreOptionItem(Icons.share, UITextConstants.shareTo, isDark, () => _handleShare()),
            SizedBox(height: 20.h),
          ],
        ),
      ),
    );
  }

  /// 构建更多选项项目
  Widget _buildMoreOptionItem(IconData icon, String title, bool isDark, VoidCallback onTap) {
    return ListTile(
      leading: Icon(
        icon,
        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
        size: 20.sp,
      ),
      title: Text(
        title,
        style: TextStyle(
          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          fontSize: 16.sp,
          fontWeight: FontWeight.w500,
        ),
      ),
      onTap: () {
        Navigator.pop(context);
        onTap();
      },
    );
  }

  // 交互处理方法（1:1 对应 MyProfilePage.tsx 跳转）
  void _handleEditProfile() {
    context.push('/profile/edit');
  }

  void _handlePersonas() {
    context.push('/profile/personas');
  }

  void _handleResonance() {
    context.push('/profile/resonance');
  }

  void _handleStats(String type) {
    context.push('/profile/stats?type=$type');
  }

  void _handleSettings() {
    context.push('/settings');
  }

  void _handleAssistantEntry() {
    context.push('/assistant/management');
  }

  void _handleShare() {
    _showToast('分享功能开发中...');
  }

  void _showToast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        margin: EdgeInsets.all(16.w),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.r),
        ),
      ),
    );
  }

  /// 格式化数量显示
  String _formatCount(int count) {
    if (count >= 1000000) {
      return '${(count / 1000000).toStringAsFixed(1)}M';
    } else if (count >= 10000) {
      return '${(count / 10000).toStringAsFixed(1)}万';
    } else if (count >= 1000) {
      return '${(count / 1000).toStringAsFixed(1)}k';
    } else {
      return count.toString();
    }
  }
}