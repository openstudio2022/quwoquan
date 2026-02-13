// ignore_for_file: unused_field, unused_element, unused_local_variable, avoid_print, unnecessary_underscores

import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';

import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 作者主页组件 - 基于原型代码实现
/// 包含完整的个人资料展示、作品展示、交互功能
class AuthorProfile extends ConsumerStatefulWidget {
  final String username;
  final VoidCallback onBack;
  final Function(dynamic, int, List<dynamic>, String, dynamic)? onPhotoClick;
  final Function(String, bool)? onFollowClick;
  final Function(dynamic)? onCommentsClick;
  final Function(dynamic)? onLikeClick;
  final Function(dynamic)? onSaveClick;
  final Function(dynamic)? onShareClick;
  final Set<String>? followingUsers;
  final Set<String>? likedPosts;
  final Set<String>? savedPosts;
  final Function(dynamic)? getPostLikesCount;
  final Function(dynamic)? getPostBookmarksCount;
  
  // 新增：吸顶状态回调
  final Function(bool)? onStickyHeaderChange;
  final Function(bool)? onStickyButtonsChange;
  final Function(User?)? onUserDataChange;
  
  // 新增：弹窗模式支持
  final bool modal;
  final VoidCallback? onClose;
  
  // 新增：是否为当前用户
  final bool isCurrentUser;

  const AuthorProfile({
    super.key,
    required this.username,
    required this.onBack,
    this.onPhotoClick,
    this.onFollowClick,
    this.onCommentsClick,
    this.onLikeClick,
    this.onSaveClick,
    this.onShareClick,
    this.followingUsers,
    this.likedPosts,
    this.savedPosts,
    this.getPostLikesCount,
    this.getPostBookmarksCount,
    this.onStickyHeaderChange,
    this.onStickyButtonsChange,
    this.onUserDataChange,
    this.modal = false,
    this.onClose,
    this.isCurrentUser = false,
  });

  @override
  ConsumerState<AuthorProfile> createState() => _AuthorProfileState();
}

class _AuthorProfileState extends ConsumerState<AuthorProfile> with TickerProviderStateMixin {
  late TabController _tabController;
  late ScrollController _scrollController;
  late AnimationController _fadeController;
  late AnimationController _pullController;

  // 与 AuthorProfile.tsx 一致：主 Tab 创作 | 互动 | 生活
  String _activeTab = 'works';
  String _workCategory = 'all'; // all | photo | video | article
  String _lifestyleCategory = 'all'; // all | footprint | soul | taste | private
  String _communitySubTab = 'likes'; // likes | comments
  String _interactionDirection = 'received'; // received | sent
  bool _worksViewModeGrid = true;
  bool _lifestyleViewModeGrid = true;
  bool _isFollowing = false;
  bool _isResonanceOpen = false;
  bool _loading = true;
  String? _error;
  
  // 下拉吸顶效果相关
  double _pullOffset = 0.0; // 经过弹簧效果处理后的有效下拉距离
  double _rawPullOffset = 0.0; // 用户原始下拉距离（用于弹簧计算）
  bool _isPulling = false;
  bool _isPullingDown = false; // 是否正在下拉
  double _maxPullHeight = 0.0;
  
  // 用户数据
  User? _userData;
  
  // 吸顶相关
  final GlobalKey _profileInfoKey = GlobalKey();
  final GlobalKey _buttonsKey = GlobalKey();
  final GlobalKey _backgroundKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this); // 与 TSX 一致：创作、互动、生活
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
      await userDataNotifier.loadUser(widget.username);
      // 从provider读取数据
      final userData = ref.read(userDataProvider);
      if (userData != null) {
        setState(() {
          _userData = userData;
          _isFollowing = widget.followingUsers?.contains(widget.username) ?? (userData.isFollowing ?? false);
          _loading = false;
          _error = null;
        });
        widget.onUserDataChange?.call(userData);
      }
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '加载用户数据失败: $e';
      });
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
      'username': widget.username,
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

  /// 处理滚动通知 - 实现背景图拉伸效果（与MyProfilePage保持一致）
  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final scrollOffset = notification.metrics.pixels;
      
      setState(() {
        if (scrollOffset < 0) {
          // 下拉状态：应用弹簧阻尼效果
          _isPullingDown = true;
          _rawPullOffset = -scrollOffset;
          final maxContentPull = _getScreenHeight() * 0.25; // 屏幕高度的1/4
          
          // 使用弹簧阻尼函数处理下拉距离
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

  /// 辅助方法：获取屏幕尺寸
  double _getScreenWidth() => MediaQuery.of(context).size.width;
  double _getScreenHeight() => MediaQuery.of(context).size.height;
  double _getPaddingTop() => MediaQuery.of(context).padding.top;
  
  /// 弹簧阻尼函数 - 模拟弹簧重力效果（与MyProfilePage保持一致）
  double _getSpringPullOffset(double rawPullOffset, double maxEffectivePull) {
    if (rawPullOffset <= 0) return 0.0;
    if (maxEffectivePull <= 0) return 0.0;
    
    final double dampingFactor = maxEffectivePull / 1.2;
    final double springEffect = 1.0 - exp(-rawPullOffset / dampingFactor);
    return (maxEffectivePull * springEffect).clamp(0.0, maxEffectivePull);
  }
  
  /// 获取当前背景图高度（固定，不随拉伸变化，与MyProfilePage保持一致）
  double _getCurrentBackgroundHeight() {
    final paddingTop = _getPaddingTop();
    final screenHeight = _getScreenHeight();
    final backgroundHeight = screenHeight * 0.25;
    return paddingTop + backgroundHeight;
  }
  
  /// 获取背景图top位置（支持上推和下拉，与MyProfilePage保持一致）
  double _getBackgroundTop() {
    final scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    if (_pullOffset > 0) {
      // 🔑 关键：下拉时，背景图顶部固定在屏幕顶部
      return 0;
    } else if (scrollOffset > 0) {
      // 上推：背景图跟随上移
      final backgroundHeight = _getCurrentBackgroundHeight();
      return -(scrollOffset.clamp(0.0, backgroundHeight));
    } else {
      // 正常状态：固定在屏幕顶部
      return 0;
    }
  }
  
  /// 获取占位空间高度（确保内容在正确位置）
  double _getPlaceholderHeight() {
    final backgroundHeight = _getCurrentBackgroundHeight();
    final scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    double totalHeight;
    if (scrollOffset < 0) {
      // 下拉状态：精确对齐背景图底部
      totalHeight = backgroundHeight + (_pullOffset / 2) + scrollOffset;
    } else {
      // 正常或上推状态：占位高度固定为背景高度
      totalHeight = backgroundHeight;
    }
    
    return totalHeight.clamp(0.0, double.infinity);
  }
  
  /// 容错：确保背景底部≥内容顶部
  double _getSafeBackgroundHeight() {
    return _getCurrentBackgroundHeight();
  }
  
  /// 计算背景图高度（简化版本）- 保留以兼容旧代码
  double _getBackgroundImageHeight() {
    // 静止状态：固定为屏幕高度的1/4
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    return screenQuarter;
  }

  /// 计算用户内容区域的margin高度（简化版本）
  double _calculateUserContentMargin() {
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    final double paddingTop = MediaQuery.of(context).padding.top;
    
    // 静止状态：内容区应该紧贴背景图底部
    // 背景图Sliver高度 = screenQuarter + paddingTop + _pullOffset
    // 内容区Sliver位置 = screenQuarter + paddingTop + _pullOffset
    // 为了让内容区视觉顶部在screenQuarter + _pullOffset位置，需要负margin
    // 但是Flutter不允许负margin，所以我们需要用Transform来向上偏移
    final double calculatedMargin = 0.0; // 不使用margin，改用Transform
    
    return calculatedMargin;
  }

  /// 设置下拉监听
  void _setupPullListener() {
    _scrollController.addListener(() {
      if (_scrollController.position.pixels < 0) {
        setState(() {
          _pullOffset = -_scrollController.position.pixels;
          _isPulling = true;
        });
      } else if (_isPulling) {
        setState(() {
          _isPulling = false;
        });
        _animatePullBack();
      }
    });
  }

  /// 计算最大下拉高度
  void _calculateMaxPullHeight() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final screenHeight = MediaQuery.of(context).size.height;
      _maxPullHeight = screenHeight / 3; // 屏幕高度的1/3
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
    // Sticky state tracking removed - fields were never used
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
          _isFollowing = widget.followingUsers?.contains(widget.username) ?? (next.isFollowing ?? false);
          _loading = false;
          _error = null;
        });
        
        // 通知父组件用户数据变化
        widget.onUserDataChange?.call(next);
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
    
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent,
        extendBodyBehindAppBar: true,
        body: Stack(
          children: [
            _buildScrollableContent(isDark),
            _buildTopToolbar(isDark),
            if (_isResonanceOpen) _buildResonanceOverlay(isDark),
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
                    foregroundColor: AppColors.white,
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

  /// 构建背景图片
  Widget _buildBackgroundImage(bool isDark) {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
        child: Container(
          height: MediaQuery.of(context).size.height * 0.2 + MediaQuery.of(context).padding.top, // 20% 屏幕高度 + 状态栏高度
        decoration: BoxDecoration(
          image: DecorationImage(
            image: NetworkImage('https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop'),
            fit: BoxFit.cover,
                          onError: (exception, stackTrace) {
                            // Handle error
                          },
          ),
        ),
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                AppColors.overlayMedium,
                Colors.transparent,
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 构建主内容
  Widget _buildMainContent(bool isDark) {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      child: NotificationListener<ScrollNotification>(
        onNotification: (ScrollNotification notification) {
          if (notification is ScrollUpdateNotification) {
            if (_scrollController.position.pixels < 0) {
              setState(() {
                _pullOffset = (-_scrollController.position.pixels).clamp(0.0, _maxPullHeight);
                _isPulling = true;
              });
            } else if (_isPulling && _scrollController.position.pixels >= 0) {
              setState(() {
                _isPulling = false;
              });
              _animatePullBack();
            }
          }
          return false;
        },
        child: CustomScrollView(
      controller: _scrollController,
          physics: const BouncingScrollPhysics(),
          // 限制下拉：内容区不能越过图片底部
          cacheExtent: 0,
      slivers: [
            // 占位空间，为背景图片留出空间
        SliverToBoxAdapter(
              child: SizedBox(
                height: MediaQuery.of(context).size.height * 0.2 + MediaQuery.of(context).padding.top, // 与背景图片高度一致
                // 移除背景色，让背景图片显示
              ),
            ),
            
            // 用户信息区域（包含头像）
            SliverToBoxAdapter(
              child: _buildProfileSection(isDark),
            ),
            
            // 统计信息 - 与Profile区域无缝连接
        SliverToBoxAdapter(
          child: _buildStatsSection(isDark),
        ),
        
        // 操作按钮
        SliverToBoxAdapter(
          child: _buildActionButtons(isDark),
        ),
        
        // Tab导航
        SliverToBoxAdapter(
          child: _buildTabNavigation(isDark),
        ),
        
        // 作品网格
        _buildPostsGrid(isDark),
      ],
        ),
      ),
    );
  }

  /// 构建Profile区域（包含头像和用户信息）
  Widget _buildProfileSection(bool isDark) {
    if (_userData == null) {
      return Container(
        key: _profileInfoKey,
        padding: EdgeInsets.all(AppSpacing.md.w),
        child: Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
          ),
        ),
      );
    }
    
    return Container(
      key: _profileInfoKey,
      transform: Matrix4.translationValues(0, -60.h, 0), // 头像从内容顶部向背景侵入1/3
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md.w,
        60.h + AppSpacing.md.h, // 为头像留出空间
        AppSpacing.md.w,
        AppSpacing.sm.h, // 添加底部padding，避免透明区域
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(AppSpacing.borderRadius.r),
          topRight: Radius.circular(AppSpacing.borderRadius.r),
        ),
        // 移除复杂的阴影，简化布局
      ),
      // 确保完全覆盖，避免透明区域
      clipBehavior: Clip.hardEdge,
      child: Stack(
        clipBehavior: Clip.none, // 允许子组件超出边界
        children: [
          // 头像 - 绝对定位，从内容顶部向背景侵入1/3
          Positioned(
            top: -60.h, // 头像半径120.h的1/2，确保1/3侵入效果
            left: AppSpacing.md.w,
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: AppColors.white,
                  width: 3.w,
                ),
              ),
              child: CircleAvatar(
                radius: 60.r,
                backgroundColor: AppColors.white,
                child: CircleAvatar(
                  radius: 57.r,
                  backgroundImage: NetworkImage('https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&h=300&fit=crop&crop=face'),
                  onBackgroundImageError: (exception, stackTrace) {
                    print('头像图片加载失败: $exception');
                  },
                ),
              ),
            ),
          ),
          
          // 用户信息
          Padding(
            padding: EdgeInsets.only(left: 140.w), // 为头像留出空间
      child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
                    Text(
                      _userData!.displayName ?? _userData!.username ?? UITextConstants.unknownUser,
                      style: TextStyle(
                        fontSize: 24.sp,
                        fontWeight: FontWeight.bold,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                    if (_userData!.isVerified == true) ...[
                      SizedBox(width: AppSpacing.xs.w),
                      Container(
                        width: 20.w,
                        height: 20.w,
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
                    fontSize: 14.sp,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  ),
                ),
                SizedBox(height: AppSpacing.sm.h),
                Text(
                  _userData!.bio ?? '',
                  style: TextStyle(
                    fontSize: 14.sp,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 构建背景图片区域
  Widget _buildBackgroundSection(bool isDark) {
    return AnimatedBuilder(
      animation: _pullController,
      builder: (context, child) {
        final screenHeight = MediaQuery.of(context).size.height;
        final statusBarHeight = MediaQuery.of(context).padding.top;
        final baseHeight = screenHeight * 0.25 + statusBarHeight; // 25vh + 状态栏高度
        
        // 计算下拉高度，使用动画控制器进行平滑过渡
        double pullHeight = 0.0;
        if (_isPulling) {
          pullHeight = _pullOffset.clamp(0.0, _maxPullHeight);
        } else if (_pullController.isAnimating) {
          pullHeight = _pullOffset * (1.0 - _pullController.value);
        }
        
        final totalHeight = baseHeight + pullHeight;
        
        if (_userData == null) {
          return Container(
            key: _backgroundKey,
            height: totalHeight,
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
            ),
          );
        }
        
        return Container(
          key: _backgroundKey,
          height: totalHeight,
          decoration: BoxDecoration(
            image: _userData!.backgroundImage != null && _userData!.backgroundImage!.isNotEmpty
                ? DecorationImage(
                    image: NetworkImage(_userData!.backgroundImage!),
                    fit: BoxFit.cover,
                  )
                    : null,
              ),
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.transparent,
                  AppColors.overlayLight,
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// 与 AuthorProfile.tsx 一致：按主 Tab 切换 创作 / 互动 / 生活 内容
  Widget _buildTabContent(bool isDark) {
    if (_activeTab == 'works') return _buildWorksTabContent(isDark);
    if (_activeTab == 'interaction') return _buildInteractionTabContent(isDark);
    if (_activeTab == 'lifestyle') return _buildLifestyleTabContent(isDark);
    return const SizedBox.shrink();
  }

  /// 创作 Tab：子分类 全部/图片/视频/文章 + 网格/列表切换 + 作品列表（与 TSX 一致）
  Widget _buildWorksTabContent(bool isDark) {
    const workCats = [
      {'id': 'all', 'label': '全部'},
      {'id': 'photo', 'label': '图片'},
      {'id': 'video', 'label': '视频'},
      {'id': 'article', 'label': '文章'},
    ];
    final works = _getMockWorks();
    final filtered = _workCategory == 'all'
        ? works
        : works.where((w) => w['type'] == _workCategory).toList();
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Padding(
      padding: EdgeInsets.all(AppSpacing.md.w),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: workCats.map((c) {
                      final active = _workCategory == c['id'];
                      return Padding(
                        padding: EdgeInsets.only(right: AppSpacing.sm.w),
                        child: GestureDetector(
                          onTap: () => setState(() => _workCategory = c['id']!),
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.md.w,
                              vertical: AppSpacing.sm.h,
                            ),
                            decoration: BoxDecoration(
                              color: active
                                  ? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                              border: active ? null : Border.all(color: borderColor),
                            ),
                            child: Text(
                              c['label']!,
                              style: TextStyle(
                                fontSize: 12.sp,
                                fontWeight: FontWeight.w900,
                                color: active ? fg : muted,
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ),
              GestureDetector(
                onTap: () => setState(() => _worksViewModeGrid = !_worksViewModeGrid),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    _worksViewModeGrid ? Icons.view_list : Icons.grid_view,
                    size: AppSpacing.iconMedium,
                    color: muted,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.md.h),
          if (_worksViewModeGrid)
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: AppSpacing.sm,
                crossAxisSpacing: AppSpacing.sm,
                childAspectRatio: 1,
              ),
              itemCount: filtered.length,
              itemBuilder: (context, i) {
                final w = filtered[i];
                return ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      Image.network(
                        w['image'] as String,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(color: borderColor),
                      ),
                      if (w['type'] == 'video')
                        Positioned(
                          top: 8,
                          right: 8,
                          child: Icon(Icons.play_arrow, color: Colors.white, size: 14.sp),
                        ),
                      if (w['type'] == 'article')
                        Positioned(
                          top: 8,
                          right: 8,
                          child: Icon(Icons.article_outlined, color: Colors.white, size: 14.sp),
                        ),
                    ],
                  ),
                );
              },
            )
          else
            ...filtered.map((w) => Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.lg.h),
                  child: Container(
                    padding: EdgeInsets.all(AppSpacing.md.w),
                    decoration: BoxDecoration(
                      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary).withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(32),
                      border: Border.all(color: borderColor),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(16),
                          child: AspectRatio(
                            aspectRatio: 16 / 9,
                            child: Image.network(
                              w['image'] as String,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(color: borderColor),
                            ),
                          ),
                        ),
                        SizedBox(height: AppSpacing.md.h),
                        Text(
                          w['title'] as String,
                          style: TextStyle(
                            fontSize: 15.sp,
                            fontWeight: FontWeight.w900,
                            color: fg,
                          ),
                        ),
                        SizedBox(height: AppSpacing.xs.h),
                        Text(
                          w['desc'] as String,
                          style: TextStyle(
                            fontSize: 12.sp,
                            color: muted,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.sm.h),
                        Text(
                          '${w['date']} · ${w['likes']} 获赞',
                          style: TextStyle(
                            fontSize: 11.sp,
                            fontWeight: FontWeight.w700,
                            color: muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                )),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _getMockWorks() {
    return [
      {'id': 'w1', 'type': 'photo', 'title': '光影的节奏', 'image': 'https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400', 'likes': '1.2k', 'date': '2025-12-20', 'desc': '在布鲁塞尔的午后，捕捉到的一组极简主义建筑光影。'},
      {'id': 'w2', 'type': 'video', 'title': '森林的呼吸', 'image': 'https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400', 'likes': '840', 'date': '2025-12-15', 'desc': '4K延时摄影，记录大兴安岭清晨云雾缭绕的过程。'},
      {'id': 'w3', 'type': 'article', 'title': '极简摄影的真谛', 'image': 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400', 'likes': '2.1k', 'date': '2025-12-10', 'desc': '通过剥离不必要的元素，我们才能看见事物的本质。'},
      {'id': 'w4', 'type': 'photo', 'title': '咖啡厅一角', 'image': 'https://images.unsplash.com/photo-1650211573412-9d36d0cbbf00?q=80&w=400', 'likes': '560', 'date': '2025-12-05', 'desc': '深夜的咖啡馆，除了香味，还有孤独。'},
    ];
  }

  /// 互动 Tab：赞/评论 + Ta收到/Ta发出 + 互动列表占位（与 TSX 一致）
  Widget _buildInteractionTabContent(bool isDark) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Padding(
      padding: EdgeInsets.all(AppSpacing.md.w),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Row(
                children: [
                  _pill('赞', _communitySubTab == 'likes', () => setState(() => _communitySubTab = 'likes'), isDark),
                  SizedBox(width: AppSpacing.sm.w),
                  _pill('评论', _communitySubTab == 'comments', () => setState(() => _communitySubTab = 'comments'), isDark),
                ],
              ),
              SizedBox(width: AppSpacing.sm.w),
              Container(
                padding: EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                  borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                  border: Border.all(color: borderColor),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _smallPill('Ta收到', _interactionDirection == 'received', () => setState(() => _interactionDirection = 'received'), isDark),
                    _smallPill('Ta发出', _interactionDirection == 'sent', () => setState(() => _interactionDirection = 'sent'), isDark),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.lg.h),
          Text(
            _communitySubTab == 'likes'
                ? (_interactionDirection == 'received' ? '赞了 Ta 的照片/文章' : 'Ta 赞了 他人 的文章')
                : (_interactionDirection == 'received' ? '评论了 Ta 的照片' : 'Ta 评论了 他人 的照片'),
            style: TextStyle(fontSize: 14.sp, color: muted),
          ),
          SizedBox(height: AppSpacing.md.h),
          Container(
            padding: EdgeInsets.all(AppSpacing.lg.w),
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary).withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: borderColor),
            ),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundImage: const NetworkImage('https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=100'),
                ),
                SizedBox(width: AppSpacing.md.w),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('李摄影', style: TextStyle(fontSize: 14.sp, fontWeight: FontWeight.w900, color: fg)),
                      Text('赞了 Ta 的照片', style: TextStyle(fontSize: 12.sp, color: muted)),
                      Text('"我们确实搞砸了"！奥特曼罕见直播...', style: TextStyle(fontSize: 13.sp, color: fg)),
                      Text('5分钟前', style: TextStyle(fontSize: 11.sp, color: muted)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _pill(String label, bool active, VoidCallback onTap, bool isDark) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w, vertical: AppSpacing.sm.h),
        decoration: BoxDecoration(
          color: active ? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary) : null,
          borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
          border: active ? null : Border.all(color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary)),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12.sp,
            fontWeight: FontWeight.w900,
            color: active ? fg : muted,
          ),
        ),
      ),
    );
  }

  Widget _smallPill(String label, bool active, VoidCallback onTap, bool isDark) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary) : Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
          boxShadow: active ? [BoxShadow(color: AppColors.primaryColor.withValues(alpha: 0.2), blurRadius: 4)] : null,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 10.sp,
            fontWeight: FontWeight.w900,
            color: active ? AppColors.primaryColor : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
          ),
        ),
      ),
    );
  }

  /// 生活 Tab：全部/足迹/书影音/味蕾/爱物 + 网格/列表（与 TSX 一致）
  Widget _buildLifestyleTabContent(bool isDark) {
    const lifeCats = [
      {'id': 'all', 'label': '全部'},
      {'id': 'footprint', 'label': '足迹'},
      {'id': 'soul', 'label': '书影音'},
      {'id': 'taste', 'label': '味蕾'},
      {'id': 'private', 'label': '爱物'},
    ];
    final items = _getMockLifeItems();
    final filtered = _lifestyleCategory == 'all'
        ? items
        : items.where((e) => e['categoryKey'] == _lifestyleCategory).toList();
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Padding(
      padding: EdgeInsets.all(AppSpacing.md.w),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: lifeCats.map((c) {
                      final active = _lifestyleCategory == c['id'];
                      return Padding(
                        padding: EdgeInsets.only(right: AppSpacing.sm.w),
                        child: GestureDetector(
                          onTap: () => setState(() => _lifestyleCategory = c['id']!),
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.md.w,
                              vertical: AppSpacing.sm.h,
                            ),
                            decoration: BoxDecoration(
                              color: active
                                  ? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                              border: active ? null : Border.all(color: borderColor),
                            ),
                            child: Text(
                              c['label']!,
                              style: TextStyle(
                                fontSize: 12.sp,
                                fontWeight: FontWeight.w900,
                                color: active ? fg : muted,
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ),
              GestureDetector(
                onTap: () => setState(() => _lifestyleViewModeGrid = !_lifestyleViewModeGrid),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    _lifestyleViewModeGrid ? Icons.view_list : Icons.grid_view,
                    size: AppSpacing.iconMedium,
                    color: muted,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.md.h),
          if (_lifestyleViewModeGrid)
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: AppSpacing.sm,
                crossAxisSpacing: AppSpacing.sm,
                childAspectRatio: 1,
              ),
              itemCount: filtered.length,
              itemBuilder: (context, i) {
                final item = filtered[i];
                return ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Stack(
                    fit: StackFit.expand,
                    alignment: Alignment.bottomLeft,
                    children: [
                      Image.network(
                        item['image'] as String,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(color: borderColor),
                      ),
                      Container(
                        padding: EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.transparent, Colors.black54],
                          ),
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item['category'] as String,
                              style: TextStyle(
                                fontSize: 10.sp,
                                fontWeight: FontWeight.w900,
                                color: Colors.white70,
                              ),
                            ),
                            Text(
                              item['name'] as String,
                              style: TextStyle(
                                fontSize: 12.sp,
                                fontWeight: FontWeight.w900,
                                color: Colors.white,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
            )
          else
            ...filtered.map((item) => Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md.h),
                  child: Container(
                    padding: EdgeInsets.all(AppSpacing.md.w),
                    decoration: BoxDecoration(
                      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary).withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: borderColor),
                    ),
                    child: Row(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(16),
                          child: SizedBox(
                            width: 96,
                            height: 96,
                            child: Image.network(
                              item['image'] as String,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(color: borderColor),
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpacing.md.w),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: AppColors.primaryColor.withValues(alpha: 0.15),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      item['category'] as String,
                                      style: TextStyle(
                                        fontSize: 9.sp,
                                        fontWeight: FontWeight.w900,
                                        color: AppColors.primaryColor,
                                      ),
                                    ),
                                  ),
                                  SizedBox(width: AppSpacing.sm.w),
                                  Text(
                                    item['name'] as String,
                                    style: TextStyle(
                                      fontSize: 14.sp,
                                      fontWeight: FontWeight.w900,
                                      color: fg,
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: AppSpacing.xs.h),
                              Text(
                                item['desc'] as String,
                                style: TextStyle(fontSize: 11.sp, color: muted),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                )),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _getMockLifeItems() {
    return [
      {'id': 'i1', 'name': '阿那亚礼堂', 'category': '足迹', 'categoryKey': 'footprint', 'image': 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400', 'desc': '在海边的孤独感中寻找创作灵感。'},
      {'id': 'i2', 'name': '《摄影的哲学》', 'category': '书影音', 'categoryKey': 'soul', 'image': 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?q=80&w=400', 'desc': '比起技巧，我更痴迷于思考快门背后。'},
      {'id': 'i3', 'name': 'Dirty Coffee', 'category': '味蕾', 'categoryKey': 'taste', 'image': 'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?q=80&w=400', 'desc': '喜欢那种冷热交替的冲突感。'},
      {'id': 'i4', 'name': 'Leica M11', 'category': '爱物', 'categoryKey': 'private', 'image': 'https://images.unsplash.com/photo-1648049003029-3b3b32cb9a1f?q=80&w=400', 'desc': '它是我身体的延伸。'},
    ];
  }

  /// 构建用户信息区域
  Widget _buildProfileInfo(bool isDark) {
    if (_userData == null) {
      return Container(
        key: _profileInfoKey,
        padding: EdgeInsets.all(AppSpacing.md.w),
        child: Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
          ),
        ),
      );
    }
    
    return Container(
      key: _profileInfoKey,
      margin: EdgeInsets.only(top: 60.h), // 为头像留出空间
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md.w,
        AppSpacing.md.h,
        AppSpacing.md.w,
        AppSpacing.md.h,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(AppSpacing.borderRadius.r),
          topRight: Radius.circular(AppSpacing.borderRadius.r),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.only(left: 140.w), // 为头像留出空间
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          _userData!.displayName ?? _userData!.username ?? UITextConstants.unknownUser,
                          style: TextStyle(
                            fontSize: 24.sp,
                            fontWeight: FontWeight.bold,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                          ),
                        ),
                        if (_userData!.isVerified == true) ...[
                  SizedBox(width: AppSpacing.xs.w),
                          Container(
                            width: 20.w,
                            height: 20.w,
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
                        fontSize: 14.sp,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                      ),
                    ),
            SizedBox(height: AppSpacing.sm.h),
            Text(
              _userData!.bio ?? '',
              style: TextStyle(
                fontSize: 14.sp,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                ),
              ),
            ],
          ),
      ),
    );
  }

  /// 与 AuthorProfile.tsx 一致：「你们有 12 个交集点」卡片，点击打开交集详情
  Widget _buildResonanceCard(bool isDark) {
    const commonAvatars = [
      'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
      'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=100',
      'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
    ];
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md.h),
      child: Material(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(24),
        child: InkWell(
          onTap: () => setState(() => _isResonanceOpen = true),
          borderRadius: BorderRadius.circular(24),
          child: Container(
            padding: EdgeInsets.all((AppSpacing.md.w).clamp(0.0, double.infinity)),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(24),
              border: Border.all(
                color: AppColors.primaryColor.withValues(alpha: 0.2),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (int i = 0; i < commonAvatars.length; i++)
                      Transform.translate(
                        offset: Offset(i == 0 ? 0 : -12.0, 0),
                        child: CircleAvatar(
                          radius: 18,
                          backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
                          child: CircleAvatar(
                            radius: 16,
                            backgroundImage: NetworkImage(commonAvatars[i]),
                          ),
                        ),
                      ),
                  ],
                ),
                SizedBox(width: AppSpacing.md.w),
                Text(
                  '你们有 ',
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w700,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  ),
                ),
                Text(
                  '12',
                  style: TextStyle(
                    fontSize: 18.sp,
                    fontWeight: FontWeight.w900,
                    color: AppColors.primaryColor,
                  ),
                ),
                Text(
                  ' 个交集点',
                  style: TextStyle(
                    fontSize: 14.sp,
                    fontWeight: FontWeight.w700,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  ),
                ),
                const Spacer(),
                Text(
                  '交集详情',
                  style: TextStyle(
                    fontSize: 10.sp,
                    fontWeight: FontWeight.w900,
                    color: AppColors.primaryColor.withValues(alpha: 0.9),
                  ),
                ),
                SizedBox(width: AppSpacing.xs.w),
                Icon(
                  Icons.chevron_right,
                  size: AppSpacing.iconMedium,
                  color: AppColors.primaryColor.withValues(alpha: 0.7),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 与 AuthorProfile.tsx 一致：关注 | 圈子 | 粉丝 | 获赞，带竖线分隔，可点击打开列表
  Widget _buildStatsSection(bool isDark) {
    if (_userData == null) {
      return Container(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        ),
        child: const Center(
          child: CircularProgressIndicator(),
        ),
      );
    }
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md.w,
        vertical: AppSpacing.md.h,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(
          top: BorderSide(color: borderColor, width: 1),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: () => context.push('/profile/stats?type=following'),
              child: _buildStatItem('284', '关注', isDark),
            ),
          ),
          Container(width: 1, height: AppSpacing.lg, color: borderColor),
          Expanded(
            child: GestureDetector(
              onTap: () {}, // 圈子暂不打开列表
              child: _buildStatItem('8', '圈子', isDark),
            ),
          ),
          Container(width: 1, height: AppSpacing.lg, color: borderColor),
          Expanded(
            child: GestureDetector(
              onTap: () => context.push('/profile/stats?type=fans'),
              child: _buildStatItem('1.2k', '粉丝', isDark),
            ),
          ),
          Container(width: 1, height: AppSpacing.lg, color: borderColor),
          Expanded(
            child: GestureDetector(
              onTap: () => context.push('/profile/stats?type=likes'),
              child: _buildStatItem('4.8k', '获赞', isDark),
            ),
          ),
        ],
      ),
    );
  }

  /// 与 TSX 一致：数字 + 小号大写标签（如 "关注"）
  Widget _buildStatItem(String value, String label, bool isDark) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 22.sp,
            fontWeight: FontWeight.w900,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          ),
        ),
        SizedBox(height: 2.h),
        Text(
          label.toUpperCase(),
          style: TextStyle(
            fontSize: 11.sp,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
          ),
        ),
      ],
    );
  }

  /// 与 AuthorProfile.tsx 一致：关注（胶囊）+ 消息图标圆钮
  Widget _buildActionButtons(bool isDark) {
    final bgSecondary = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final fgMuted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Container(
      key: _buttonsKey,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md.w,
        vertical: AppSpacing.sm.h,
      ),
      child: Row(
        children: [
          Material(
            color: _isFollowing ? bgSecondary : AppColors.primaryColor,
            borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
            child: InkWell(
              onTap: _handleFollowToggle,
              borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg.w,
                  vertical: 12.h,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (!_isFollowing) ...[
                      Icon(
                        Icons.add,
                        size: AppSpacing.iconSmall,
                        color: Colors.white,
                      ),
                      SizedBox(width: AppSpacing.sm.w),
                    ],
                    Text(
                      _isFollowing ? '已关注' : '关注',
                      style: TextStyle(
                        fontSize: 14.sp,
                        fontWeight: FontWeight.w900,
                        color: _isFollowing ? fgMuted : Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.md.w),
          Material(
            color: bgSecondary,
            shape: const CircleBorder(),
            child: InkWell(
              onTap: _handleMessage,
              customBorder: const CircleBorder(),
              child: Container(
                width: 44,
                height: 44,
                alignment: Alignment.center,
                child: Icon(
                  Icons.chat_bubble_outline,
                  size: AppSpacing.iconMedium,
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 与 AuthorProfile.tsx 一致：创作 | 互动 | 生活，sticky 顶栏 + 底部蓝色下划线
  Widget _buildTabNavigation(bool isDark) {
    const labels = ['创作', '互动', '生活'];
    const ids = ['works', 'interaction', 'lifestyle'];
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary).withValues(alpha: 0.95),
        border: Border(bottom: BorderSide(color: borderColor, width: 1)),
      ),
      child: Row(
        children: List.generate(3, (i) {
          final isActive = _activeTab == ids[i];
          return Expanded(
            child: GestureDetector(
              onTap: () => setState(() => _activeTab = ids[i]),
              behavior: HitTestBehavior.opaque,
              child: Container(
                padding: EdgeInsets.symmetric(vertical: AppSpacing.md.h),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      labels[i],
                      style: TextStyle(
                        fontSize: 14.sp,
                        fontWeight: isActive ? FontWeight.w900 : FontWeight.w700,
                        color: isActive ? fg : muted,
                      ),
                    ),
                    if (isActive)
                      Container(
                        margin: EdgeInsets.only(top: 4.h),
                        width: 32,
                        height: 4,
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }

  /// 构建作品网格
  Widget _buildPostsGrid(bool isDark) {
    final posts = _getFilteredPosts();
    
    return SliverMasonryGrid.count(
      crossAxisCount: 3,
      mainAxisSpacing: 2.w,
      crossAxisSpacing: 2.w,
      childCount: posts.length,
      itemBuilder: (context, index) {
        final post = posts[index];
        return _buildPostItem(post, isDark);
      },
    );
  }

  /// 获取过滤后的帖子
  List<Map<String, dynamic>> _getFilteredPosts() {
    final allPosts = _generateMockPosts(); // 使用模拟数据
    
    switch (_activeTab) {
      case 'all':
        return allPosts;
      case 'moments':
        return allPosts.where((post) => 
          post['type'] == 'moment' || 
          (post['tags'] != null && (post['tags'] as List<dynamic>).any((tag) => 
            tag.toString().contains('生活') || tag.toString().contains('日常')
          ))
        ).toList();
      case 'images':
        return allPosts.where((post) => 
          post['type'] == 'image' || 
          (post['images'] != null && (post['images'] as List).isNotEmpty)
        ).toList();
      case 'videos':
        return allPosts.where((post) => 
          post['type'] == 'video' || 
          (post['tags'] != null && (post['tags'] as List<dynamic>).any((tag) => 
            tag.toString().contains('视频')
          ))
        ).toList();
      case 'articles':
        return allPosts.where((post) => 
          post['type'] == 'article' || 
          (post['caption'] != null && (post['caption'] as String).length > 100) ||
          (post['tags'] != null && (post['tags'] as List<dynamic>).any((tag) => 
            tag.toString().contains('文章') || tag.toString().contains('分享')
          ))
        ).toList();
      default:
        return allPosts;
    }
  }

  /// 构建帖子项目
  Widget _buildPostItem(Map<String, dynamic> post, bool isDark) {
    return GestureDetector(
      onTap: () => widget.onPhotoClick?.call(
        post,
        0,
        _getFilteredPosts(),
        'userProfile',
        _userData,
      ),
      child: Container(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
          borderRadius: BorderRadius.circular(8.r),
        ),
        child: AspectRatio(
          aspectRatio: 1.0,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8.r),
            child: Image.network(
              post['images'][0],
              fit: BoxFit.cover,
              loadingBuilder: (context, child, loadingProgress) {
                if (loadingProgress == null) return child;
                return Center(
                  child: CircularProgressIndicator(
                    color: AppColors.primaryColor,
                    value: loadingProgress.expectedTotalBytes != null
                        ? loadingProgress.cumulativeBytesLoaded / loadingProgress.expectedTotalBytes!
                        : null,
                  ),
                );
              },
              errorBuilder: (context, error, stackTrace) {
                return Container(
                  color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
                  child: Icon(
                    Icons.error_outline,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  /// 构建吸顶导航栏
  Widget _buildStickyHeader(bool isDark) {
    if (_userData == null) {
      return SizedBox.shrink();
    }
    
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(16.w, 50.h, 16.w, 16.h),
        decoration: BoxDecoration(
          color: Colors.transparent, // 移除背景色，避免黑色透明区域
          // 移除边框，避免视觉干扰
        ),
        child: Row(
          children: [
            // 吸顶返回按钮
            GestureDetector(
              onTap: widget.onBack,
              child: Container(
                padding: EdgeInsets.all(AppSpacing.sm.w),
                child: Icon(
                  Icons.chevron_left, // 使用小于符号样式的图标
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  size: AppSpacing.iconMedium.sp,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.sm.w),
            Text(
              _userData!.displayName ?? _userData!.username ?? UITextConstants.unknownUser,
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.bold,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
            ),
                        if (_userData!.isVerified == true) ...[
              SizedBox(width: 8.w),
              Container(
                width: 16.w,
                height: 16.w,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.check,
                  size: 10.sp,
                  color: AppColors.white,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// 构建吸顶按钮栏
  Widget _buildStickyButtons(bool isDark) {
    return Positioned(
      top: 100.h,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16.w, vertical: 8.h),
        decoration: BoxDecoration(
          color: Colors.transparent, // 移除背景色，避免黑色透明区域
          // 移除边框，避免视觉干扰
        ),
        child: Row(
          children: [
            Expanded(
              child: ElevatedButton(
                onPressed: _handleFollowToggle,
                style: ElevatedButton.styleFrom(
                  backgroundColor: _isFollowing ? AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary) : AppColors.primaryColor,
                  foregroundColor: AppColors.white,
                  padding: EdgeInsets.symmetric(vertical: 8.h),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(6.r),
                  ),
                ),
                child: Text(
                  _isFollowing ? '已关注' : '关注',
                  style: TextStyle(fontSize: 14.sp),
                ),
              ),
            ),
            SizedBox(width: 8.w),
            Expanded(
              child: OutlinedButton(
                onPressed: _handleMessage,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  side: BorderSide(
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  ),
                  padding: EdgeInsets.symmetric(vertical: 8.h),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(6.r),
                  ),
                ),
                child: Text(
                  '私信',
                  style: TextStyle(fontSize: 14.sp),
                ),
              ),
            ),
            SizedBox(width: 8.w),
            OutlinedButton(
              onPressed: _showMoreOptions,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                side: BorderSide(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                ),
                padding: EdgeInsets.symmetric(vertical: 8.h, horizontal: 12.w),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(6.r),
                ),
              ),
              child: Icon(Icons.more_horiz, size: 16.sp),
            ),
          ],
        ),
      ),
    );
  }

  /// 与 TSX ResonanceSpace 一致：交集详情全屏叠层，占位实现
  Widget _buildResonanceOverlay(bool isDark) {
    return Positioned.fill(
      child: Material(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md.w,
                  vertical: AppSpacing.sm.h,
                ),
                child: Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.arrow_back),
                      onPressed: () => setState(() => _isResonanceOpen = false),
                    ),
                    Text(
                      '交集详情',
                      style: TextStyle(
                        fontSize: 18.sp,
                        fontWeight: FontWeight.w900,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Center(
                  child: Text(
                    '交集详情（与 ResonanceSpace 一致，待完整迁移）',
                    style: TextStyle(
                      fontSize: 14.sp,
                      color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                    ),
                  ),
                ),
              ),
            ],
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
              onTap: () {
                widget.onBack();
              },
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
                  color: AppColors.overlayMedium, // 更透明的背景
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: AppColors.overlayLight,
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
            _buildMoreOptionItem(Icons.block, '屏蔽用户', isDark, () => _handleBlockUser()),
            _buildMoreOptionItem(Icons.flag, UITextConstants.report, isDark, () => _handleReport()),
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
  void _handleFollowToggle() {
    setState(() {
      _isFollowing = !_isFollowing;
    });
    widget.onFollowClick?.call(widget.username, _isFollowing);
  }

  void _handleMessage() {
    _showToast('私信功能开发中...');
  }

  void _handleBlockUser() {
    _showToast('已屏蔽用户');
  }

  void _handleReport() {
    _showToast('举报功能开发中...');
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

  /// 构建可滚动的内容区域 - 全局Stack架构（与MyProfilePage保持一致）
  Widget _buildScrollableContent(bool isDark) {
    return Stack(
      children: [
        // 1. 底层：全局背景图 (Positioned)
        Positioned(
          top: _getBackgroundTop(),
          left: 0,
          right: 0,
          height: _getCurrentBackgroundHeight() + (_pullOffset > 0 ? _pullOffset / 2 : 0),
          child: Transform.scale(
            scale: _pullOffset > 0 ? 1.0 + (_pullOffset / (_getCurrentBackgroundHeight() * 2)) : 1.0,
            alignment: Alignment.topCenter,
            child: Container(
              key: _backgroundKey,
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary), // 占位背景色（与MyProfilePage保持一致）
                image: _userData?.backgroundImage != null && _userData!.backgroundImage!.isNotEmpty
                    ? DecorationImage(
                        image: NetworkImage(_userData!.backgroundImage!),
                        fit: BoxFit.cover,
                        alignment: Alignment.topCenter,
                        onError: (exception, stackTrace) {
                          // Handle error
                        },
                      )
                    : null,
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
              physics: const BouncingScrollPhysics(),
              slivers: [
                // 占位Sliver（确保内容在正确位置）
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: _getPlaceholderHeight(),
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
                      clipBehavior: Clip.none,
                      children: [
                        // 用户信息内容
                        Padding(
                          padding: EdgeInsets.only(
                            top: 45.r + AppSpacing.sm.h,
                            left: AppSpacing.md.w,
                            right: AppSpacing.md.w,
                            bottom: AppSpacing.md.h,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              _buildUserInfo(isDark),
                              SizedBox(height: AppSpacing.md.h),
                              _buildResonanceCard(isDark),
                              _buildStatsSection(isDark),
                              _buildActionButtons(isDark),
                            ],
                          ),
                        ),
                        
                        // 头像（向上偏移，侵入背景图）
                        Positioned(
                          top: -45.r,
                          left: AppSpacing.md.w,
                          child: Container(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: AppColors.white,
                                width: 4.w,
                              ),
                            ),
                            child: CircleAvatar(
                              radius: 45.r,
                              backgroundImage: _userData?.avatar != null && _userData!.avatar!.isNotEmpty
                                  ? NetworkImage(_userData!.avatar!)
                                  : null,
                              onBackgroundImageError: _userData?.avatar != null && _userData!.avatar!.isNotEmpty
                                  ? (exception, stackTrace) {
                                      // Handle error
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
                _userData!.displayName ?? _userData!.username ?? UITextConstants.unknownUser,
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

}
