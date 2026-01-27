import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';

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
  double _pullOffset = 0.0; // 下拉偏移量
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
          // 下拉状态
          _isPullingDown = true;
          _pullOffset = -scrollOffset * 0.8; // 🔑 增加拉伸系数，更明显的拉伸效果
        } else {
          // 上推或正常状态
          _isPullingDown = false;
          _pullOffset = 0;
        }
      });
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
              _isFollowing = userData.isFollowing;
              _loading = false;
              _error = null;
            });
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

  /// 获取背景图顶部位置
  double _getBackgroundTop() {
    final double scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    
    if (_pullOffset > 0) {
      // 下拉状态：顶部固定，直接使用屏幕顶部
      return 0; // ✅ 直接使用屏幕顶部
    } else if (scrollOffset > 0) {
      // 上推状态：跟随滚动偏移上移
      return -scrollOffset;
    } else {
      // 正常状态：顶部固定，直接使用屏幕顶部
      return 0; // ✅ 直接使用屏幕顶部
    }
  }

  /// 获取背景图高度（固定高度，不随拉伸变化）
  double _getBackgroundHeight() {
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    final double paddingTop = MediaQuery.of(context).padding.top;
    
    // ✅ 背景图高度始终固定，拉伸通过图像缩放实现
    return screenQuarter + paddingTop;
  }

  /// 构建可滚动的内容区域 - 全局Stack架构
  Widget _buildScrollableContent(bool isDark) {
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    final double paddingTop = MediaQuery.of(context).padding.top;
    
    return Stack(
      children: [
        // 1. 底层：全局背景图 (Positioned) - 固定高度，支持上推跟随
        Positioned(
          top: _getBackgroundTop(), // 🔑 恢复动态top位置，支持上推跟随
          left: 0,
          right: 0,
          height: _getBackgroundHeight(), // 🔑 固定高度
          child: Transform.scale(
            scale: _pullOffset > 0 ? 1.0 + (_pullOffset / (_getBackgroundHeight() * 2)) : 1.0, // 🔑 拉伸时图像缩放
            alignment: Alignment.topCenter, // 🔑 从顶部开始缩放
            child: Container(
              decoration: BoxDecoration(
                color: Colors.grey[300], // 占位背景色
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
                // 占位Sliver（为背景图留出空间）
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: _getBackgroundHeight(), // ✅ 背景图固定高度，内容区顶部与背景图底部精确对齐
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