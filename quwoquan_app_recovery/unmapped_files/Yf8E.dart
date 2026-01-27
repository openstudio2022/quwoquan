import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';
import 'package:quwoquan_app/features/profile/services/user_service_provider.dart';

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
  late TabController _tabController;
  late ScrollController _scrollController;
  late AnimationController _fadeController;
  late AnimationController _pullController; // 下拉动画控制器
  
  String _activeTab = 'all';
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
  static const double kBackgroundMaxRatio = 0.50;       // 背景最大高度（1/2）
  
  // 吸顶相关
  final GlobalKey _profileInfoKey = GlobalKey();
  final GlobalKey _buttonsKey = GlobalKey();
  final GlobalKey _backgroundKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this); // 4个tab: 作品、动态、收藏、标签
    _scrollController = ScrollController();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _pullController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    
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
    _tabController.dispose();
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
              
              debugPrint('=== 图片尺寸加载完成 ===');
              debugPrint('图片宽度: $_actualImageWidth');
              debugPrint('图片高度: $_actualImageHeight');
              debugPrint('原始图片高度: ${_getRawImageHeight()}');
              debugPrint('背景初始高度: ${_getBackgroundInitialHeight()}');
              debugPrint('内容区顶部位置: ${_getContentStaticTop()}');
              debugPrint('可拉伸空间 - 内容: ${_getContentPullSpace()}');
              debugPrint('可拉伸空间 - 背景: ${_getBackgroundPullSpace()}');
              debugPrint('拉伸比例: ${_getStretchRatio()}');
            }
          },
          onError: (exception, stackTrace) {
            if (mounted) {
              setState(() {
                _isImageLoaded = true; // 加载失败，使用占位高度
              });
              debugPrint('图片加载失败: $exception');
            }
          },
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          _isImageLoaded = true;
        });
        debugPrint('获取图片尺寸失败: $e');
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
          
          // 调试日志
          debugPrint('=== 下拉状态（弹簧效果） ===');
          debugPrint('原始下拉: $_rawPullOffset');
          debugPrint('弹簧处理后: $_pullOffset');
          debugPrint('最大可拉伸: $maxContentPull');
          debugPrint('弹簧系数: ${_pullOffset / _rawPullOffset}');
          debugPrint('内容拉伸: ${_getContentPullOffset()}');
          debugPrint('背景拉伸: ${_getBackgroundPullOffset()}');
          debugPrint('当前内容顶部: ${_getCurrentContentTop()}');
          debugPrint('当前背景高度: ${_getSafeBackgroundHeight()}');
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
    
    // 调试：验证弹簧函数限制
    debugPrint('=== 弹簧函数限制验证 ===');
    debugPrint('原始下拉: $rawPullOffset');
    debugPrint('最大可拉伸: $maxEffectivePull');
    debugPrint('弹簧效果: $springEffect');
    debugPrint('计算结果: ${maxEffectivePull * springEffect}');
    debugPrint('最终结果: $result');
    debugPrint('是否超限: ${result > maxEffectivePull}');
    
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
    
    debugPrint('=== 内容区限制验证 ===');
    debugPrint('原始下拉: $_pullOffset');
    debugPrint('最大可拉伸: $maxPull');
    debugPrint('静态顶部: $staticTop');
    debugPrint('当前顶部: $currentTop');
    debugPrint('最大顶部: $maxTop');
    debugPrint('是否超限: ${currentTop > maxTop}');
    
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

  /// 11. 获取当前背景图高度（含拉伸）
  double _getCurrentBackgroundHeight() {
    final paddingTop = _getPaddingTop();
    final initialHeight = _getBackgroundInitialHeight();
    final pullOffset = _getBackgroundPullOffset();
    
    return paddingTop + initialHeight + pullOffset;
  }

  /// 12. 获取当前内容区顶部位置（含拉伸）
  double _getCurrentContentTop() {
    final staticTop = _getContentStaticTop();
    final pullOffset = _getContentPullOffset();
    
    return staticTop + pullOffset;
  }

  /// 13. 获取占位空间高度（确保内容在正确位置）
  double _getPlaceholderHeight() {
    return _getCurrentContentTop();
  }

  /// 14. 容错：确保背景底部≥内容顶部
  double _getSafeBackgroundHeight() {
    final calculatedHeight = _getCurrentBackgroundHeight();
    final contentTop = _getCurrentContentTop();
    final paddingTop = _getPaddingTop();
    
    // 背景底部必须 >= 内容顶部
    final minRequiredHeight = contentTop + paddingTop;
    
    return calculatedHeight > minRequiredHeight ? calculatedHeight : minRequiredHeight;
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
        debugPrint('最大下拉高度: $_maxPullHeight');
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
    ref.listen<AsyncValue<User?>>(userDataProvider, (previous, next) {
      next.when(
        data: (User? userData) {
          if (userData != null) {
            setState(() {
              _userData = userData;
              _isFollowing = userData.isFollowing;
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
        },
        loading: () {
          setState(() {
            _loading = true;
            _error = null;
          });
        },
        error: (error, stackTrace) {
          setState(() {
            _loading = false;
            _error = '加载用户数据失败: $error';
          });
        },
      );
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
            padding: EdgeInsets.all(16.w),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.error_outline,
                  size: 64.sp,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                ),
                SizedBox(height: 16.h),
                Text(
                  '加载失败',
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                    fontSize: 18.sp,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(height: 8.h),
                Text(
                  _error ?? '未知错误',
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                    fontSize: 14.sp,
                  ),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: 24.h),
                ElevatedButton(
                  onPressed: _loadUserData,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primaryColor,
                    foregroundColor: Colors.white,
                  ),
                  child: Text('重试'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 15. 获取背景图top位置（支持上推）
  double _getBackgroundTop() {
    final scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    if (scrollOffset > 0) {
      // 上推：背景图跟随上移
      return -(scrollOffset.clamp(0.0, _getSafeBackgroundHeight()));
    }
    
    // 下拉或正常：固定在顶部
    return 0;
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
          height: _getSafeBackgroundHeight(), // 🔑 使用容错后的高度
          child: Container(
            decoration: BoxDecoration(
              color: Colors.grey[300], // 占位背景色
              image: DecorationImage(
                image: NetworkImage(_userData?.backgroundImage ?? 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop'),
                fit: BoxFit.cover, // 🔑 居中缩放裁剪
                alignment: Alignment.center,
                onError: (exception, stackTrace) {
                  debugPrint('背景图片加载失败: $exception');
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
                    Colors.black.withValues(alpha: 0.3),
                  ],
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
                            offset: Offset(0, -30.h), // 🔑 向上偏移30.h，侵入背景
                            child: Container(
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: AppColors.white,
                                  width: 3.w,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.1),
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
                                onBackgroundImageError: _userData?.avatar != null && _userData!.avatar!.isNotEmpty
                                    ? (exception, stackTrace) {
                                        debugPrint('头像图片加载失败: $exception');
                                      }
                                    : null,
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
                _userData!.displayName,
                style: TextStyle(
                  fontSize: 20.sp, // 调整用户名字体从24.sp到20.sp
                  fontWeight: FontWeight.bold,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                ),
              ),
              if (_userData!.isVerified) ...[
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

  /// 构建统计信息区域
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
    
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md.w,
        vertical: AppSpacing.sm.h,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _buildStatItem('作品', _userData!.posts, isDark),
          _buildStatItem('关注', _userData!.following, isDark),
          _buildStatItem('点赞', _userData!.likes, isDark),
          _buildStatItem('收藏', _userData!.bookmarks, isDark),
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

  /// 构建操作按钮区域
  Widget _buildActionButtons(bool isDark) {
    return Container(
      key: _buttonsKey,
      padding: EdgeInsets.all(AppSpacing.md.w),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // 编辑按钮
          Expanded(
            flex: 2,
            child: ElevatedButton(
              onPressed: _handleEditProfile,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryColor,
                foregroundColor: AppColors.white,
                padding: EdgeInsets.symmetric(vertical: AppSpacing.sm.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius.r),
                ),
              ),
              child: Text(
                '编辑资料',
                style: TextStyle(
                  fontSize: 16.sp,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm.w),
          
          // 设置按钮
          Expanded(
            flex: 2,
            child: OutlinedButton(
              onPressed: _handleSettings,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                side: BorderSide(
                  color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
                ),
                padding: EdgeInsets.symmetric(vertical: AppSpacing.sm.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius.r),
                ),
              ),
              child: Text(
                '设置',
                style: TextStyle(
                  fontSize: 16.sp,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 构建Tab导航
  Widget _buildTabNavigation(bool isDark) {
    final tabs = [
      {'id': 'all', 'label': '全部'},
      {'id': 'moments', 'label': '动态'},
      {'id': 'images', 'label': '图片'},
      {'id': 'videos', 'label': '视频'},
      {'id': 'articles', 'label': '文章'},
    ];

    return Container(
      height: AppSpacing.subTabNavigationHeight.h,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary), // 使用primary背景色
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: 1,
          ),
        ),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm.w),
        child: Row(
          children: tabs.map((tab) {
            final isActive = tab['id'] == _activeTab;

            return GestureDetector(
              onTap: () {
          setState(() {
                  _activeTab = tab['id']!;
          });
        },
              child: Container(
                margin: EdgeInsets.only(right: AppSpacing.xs.w),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm.w,
                  vertical: 1.h,
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
                    tab['label']!,
                    style: TextStyle(
                      fontSize: 14.sp,
                      fontWeight: isActive ? FontWeight.w500 : FontWeight.normal,
                      color: isActive
                          ? AppColorsFunctional.getColor(isDark, ColorType.selectionForeground)
                          : AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
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
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            // 返回按钮
            GestureDetector(
        onTap: () => Navigator.of(context).pop(),
        child: Container(
                padding: EdgeInsets.all(AppSpacing.sm.w),
          decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.3), // 更透明的背景
            shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.2),
                    width: 1,
                  ),
          ),
          child: Icon(
                  Icons.chevron_left, // 使用小于符号样式的图标
                  color: AppColors.white,
                  size: AppSpacing.iconMedium.sp,
                ),
              ),
            ),
            
            // 更多功能按钮
            GestureDetector(
              onTap: _showMoreOptions,
              child: Container(
                padding: EdgeInsets.all(AppSpacing.sm.w),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.3), // 更透明的背景
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.2),
                    width: 1,
                  ),
                ),
                child: Icon(
                  Icons.more_horiz,
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

  // 交互处理方法
  void _handleEditProfile() {
    _showToast('编辑资料功能开发中...');
  }

  void _handleSettings() {
    _showToast('设置功能开发中...');
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