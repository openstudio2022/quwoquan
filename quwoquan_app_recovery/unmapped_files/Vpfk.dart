import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';
import 'package:quwoquan_app/features/profile/services/user_service_provider.dart';

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
  late AnimationController _pullController; // 下拉动画控制器
  
  String _activeTab = 'all';
  bool _showStickyHeader = false;
  bool _showStickyButtons = false;
  bool _isFollowing = false;
  bool _loading = true;
  String? _error;
  
  // 下拉吸顶效果相关
  double _pullOffset = 0.0; // 下拉偏移量
  bool _isPulling = false;
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
      await userDataNotifier.loadUser(widget.username);
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

  /// 处理滚动通知 - 实现背景图拉伸效果
  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final scrollOffset = notification.metrics.pixels;
      
      // 当向下滚动（下拉）时，计算拉伸偏移量
      if (scrollOffset < 0) {
        final newPullOffset = -scrollOffset * 0.5; // 拉伸系数
        if (newPullOffset != _pullOffset) {
          setState(() {
            _pullOffset = newPullOffset;
          });
        }
      } else {
        // 向上滚动时，重置拉伸
        if (_pullOffset != 0) {
          setState(() {
            _pullOffset = 0;
          });
        }
      }
    }
    
    return false;
  }

  /// 计算背景图高度（简化版本）
  double _getBackgroundImageHeight() {
    // 静止状态：固定为屏幕高度的1/4
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    return screenQuarter;
  }

  /// 计算用户内容区域的margin高度（简化版本）
  double _calculateUserContentMargin() {
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    final double paddingTop = MediaQuery.of(context).padding.top;
    
    // 调试日志
    print('=== _calculateUserContentMargin 调试信息 ===');
    print('屏幕高度: ${MediaQuery.of(context).size.height}');
    print('屏幕1/4高度: $screenQuarter');
    print('状态栏高度: $paddingTop');
    print('当前_pullOffset: $_pullOffset');
    
    // 静止状态：内容区应该紧贴背景图底部
    // 背景图Sliver高度 = screenQuarter + paddingTop + _pullOffset
    // 内容区Sliver位置 = screenQuarter + paddingTop + _pullOffset
    // 为了让内容区视觉顶部在screenQuarter + _pullOffset位置，需要负margin
    // 但是Flutter不允许负margin，所以我们需要用Transform来向上偏移
    final double calculatedMargin = 0.0; // 不使用margin，改用Transform
    
    print('计算出的margin: $calculatedMargin');
    print('期望的内容区视觉顶部位置: ${screenQuarter + _pullOffset}');
    print('==========================================');
    
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
              _isFollowing = widget.followingUsers?.contains(widget.username) ?? userData.isFollowing;
              _loading = false;
              _error = null;
            });
            
            // 通知父组件用户数据变化
            widget.onUserDataChange?.call(userData);
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
    
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent, // 透明背景，让背景图片显示
        extendBodyBehindAppBar: true,
      body: Stack(
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
              print('背景图片加载失败: $exception');
            },
          ),
        ),
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.black.withValues(alpha: 0.3),
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
                      _userData!.displayName,
                      style: TextStyle(
                        fontSize: 24.sp,
                        fontWeight: FontWeight.bold,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                    if (_userData!.isVerified) ...[
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
                  Colors.black.withValues(alpha: 0.2),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// 构建Tab内容区域
  Widget _buildTabContent(bool isDark) {
    return Container(
      height: 600.h, // 固定高度，避免无限高度问题
      child: _buildSimplePostsGrid(isDark),
    );
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
                          _userData!.displayName,
                          style: TextStyle(
                            fontSize: 24.sp,
                            fontWeight: FontWeight.bold,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                          ),
                        ),
                        if (_userData!.isVerified) ...[
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
          // 关注按钮
          Expanded(
            flex: 2,
            child: ElevatedButton(
              onPressed: _handleFollowToggle,
              style: ElevatedButton.styleFrom(
                backgroundColor: _isFollowing 
                    ? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary)
                    : AppColors.primaryColor,
                foregroundColor: _isFollowing 
                    ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
                    : AppColors.white,
                padding: EdgeInsets.symmetric(vertical: AppSpacing.sm.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius.r),
                ),
              ),
              child: Text(
                _isFollowing ? '已关注' : '关注',
                style: TextStyle(
                  fontSize: 16.sp,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm.w),
          
          // 私信按钮
          Expanded(
            flex: 2,
            child: OutlinedButton(
              onPressed: _handleMessage,
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
                '私信',
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
          (post['tags'] != null && (post['tags'] as List).any((tag) => 
            (tag as String).contains('生活') || (tag as String).contains('日常')
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
          (post['tags'] != null && (post['tags'] as List).any((tag) => 
            (tag as String).contains('视频')
          ))
        ).toList();
      case 'articles':
        return allPosts.where((post) => 
          post['type'] == 'article' || 
          (post['caption'] != null && (post['caption'] as String).length > 100) ||
          (post['tags'] != null && (post['tags'] as List).any((tag) => 
            (tag as String).contains('文章') || (tag as String).contains('分享')
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
              _userData!.displayName,
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.bold,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
            ),
            if (_userData!.isVerified) ...[
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
                  color: Colors.white,
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
                  backgroundColor: _isFollowing ? Colors.grey : AppColors.primaryColor,
                  foregroundColor: Colors.white,
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
        onTap: widget.onBack,
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

  /// 构建可滚动的内容区域 - 背景图拉伸效果
  Widget _buildScrollableContent(bool isDark) {
    return Positioned(
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
          // 使用单个Sliver包含整个Stack布局
          SliverToBoxAdapter(
            child: Builder(
              builder: (context) {
                final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
                final double paddingTop = MediaQuery.of(context).padding.top;
                final double bgHeight = _getBackgroundImageHeight();
                final double actualHeight = bgHeight + paddingTop + _pullOffset;
                
                print('=== 重新设计的布局调试信息 ===');
                print('_getBackgroundImageHeight(): $bgHeight');
                print('paddingTop: $paddingTop');
                print('_pullOffset: $_pullOffset');
                print('实际容器高度: $actualHeight');
                print('期望的背景图视觉底部位置: ${screenQuarter + _pullOffset}');
                print('========================');
                
                return Container(
                  height: actualHeight,
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      // 1. 背景图容器（底层）
                      Positioned.fill(
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.grey[200], // 占位背景色，解决白色框问题
                            image: DecorationImage(
                              image: NetworkImage(_userData?.backgroundImage ?? 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop'),
                              fit: BoxFit.cover,
                              alignment: Alignment.topCenter,
                              onError: (exception, stackTrace) {
                                print('背景图片加载失败: $exception');
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
                                  Colors.black.withOpacity(0.3),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                      
                      // 2. 内容区容器（中层，在背景图之上）
                      Positioned(
                        top: screenQuarter + _pullOffset, // 内容区顶部位置
                        left: 0,
                        right: 0,
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
                              // 用户内容（内容区底层）
                              Padding(
                                padding: EdgeInsets.only(
                                  top: 60.h, // 为头像留出空间
                                  left: AppSpacing.md.w,
                                  right: AppSpacing.md.w,
                                  bottom: AppSpacing.md.h,
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    // 用户信息
                                    _buildUserInfo(isDark),
                                    SizedBox(height: AppSpacing.md.h),
                                    // 统计信息
                                    _buildStatsSection(isDark),
                                    // 操作按钮
                                    _buildActionButtons(isDark),
                                  ],
                                ),
                              ),
                              
                              // 3. 头像（顶层，悬浮在内容之上）
                              Positioned(
                                top: -30.h, // 向上偏移，侵入背景
                                left: AppSpacing.md.w,
                                child: Container(
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: AppColors.white,
                                      width: 3.w,
                                    ),
                                    boxShadow: [
                                      BoxShadow(
                                        color: Colors.black.withOpacity(0.1),
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
                                            print('头像图片加载失败: $exception');
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
                    ],
                  ),
                );
              },
            ),
          ),
          // Tab区域 - 包含Tab导航和Tab内容（作品网格）
          SliverToBoxAdapter(
            child: Container(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
              child: Column(
                children: [
                  // Tab导航
                  _buildTabNavigation(isDark),
                  // Tab内容 - 作品网格
                  _buildTabContent(isDark),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
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
