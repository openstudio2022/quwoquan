import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';

import 'package:quwoquan_core/quwoquan_core.dart';
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
  
  String _activeTab = 'all';
  bool _showStickyHeader = false;
  bool _showStickyButtons = false;
  bool _isFollowing = false;
  bool _loading = true;
  String? _error;
  
  // 用户数据
  User? _userData;
  
  // 吸顶相关
  final GlobalKey _profileInfoKey = GlobalKey();
  final GlobalKey _buttonsKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this); // 4个tab: 作品、动态、收藏、标签
    _scrollController = ScrollController();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    
    _setupScrollListener();
    
    // 延迟加载用户数据，避免在initState中修改provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadUserData();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _scrollController.dispose();
    _fadeController.dispose();
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
    return List.generate(20, (index) => {
      'id': 'post_$index',
      'username': widget.username,
      'caption': '这是第${index + 1}个帖子',
      'images': ['https://picsum.photos/300/${300 + (index % 3) * 100}?random=$index'],
      'likesCount': 10 + index,
      'commentsCount': 5 + index,
      'savesCount': 2 + index,
      'createdAt': DateTime.now().subtract(Duration(hours: index)).toIso8601String(),
    });
  }

  /// 设置滚动监听
  void _setupScrollListener() {
    _scrollController.addListener(() {
      _updateStickyStates();
    });
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
    
    return Scaffold(
      backgroundColor: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
      body: Stack(
        children: [
          // 主内容
          _buildMainContent(isDark),
          
          // 吸顶导航栏
          if (_showStickyHeader) _buildStickyHeader(isDark),
          
          // 吸顶按钮栏
          if (_showStickyButtons) _buildStickyButtons(isDark),
          
          // 返回按钮
          _buildBackButton(isDark),
        ],
      ),
    );
  }

  /// 构建加载状态
  Widget _buildLoadingState(bool isDark) {
    return Scaffold(
      backgroundColor: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
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
                    color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
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
      backgroundColor: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
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
                  color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
                ),
                SizedBox(height: 16.h),
                Text(
                  '加载失败',
                  style: TextStyle(
                    color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
                    fontSize: 18.sp,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(height: 8.h),
                Text(
                  _error ?? '未知错误',
                  style: TextStyle(
                    color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
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

  /// 构建主内容
  Widget _buildMainContent(bool isDark) {
    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        // 用户信息区域
        SliverToBoxAdapter(
          child: _buildProfileInfo(isDark),
        ),
        
        // 统计信息
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
    );
  }

  /// 构建用户信息区域
  Widget _buildProfileInfo(bool isDark) {
    if (_userData == null) {
      return Container(
        key: _profileInfoKey,
        padding: EdgeInsets.all(16.w),
        child: Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
          ),
        ),
      );
    }
    
    return Container(
      key: _profileInfoKey,
      padding: EdgeInsets.all(16.w),
      child: Column(
        children: [
          // 头像和基本信息
          Row(
            children: [
              // 头像
              CircleAvatar(
                radius: 50.r,
                backgroundImage: _userData!.avatar != null && _userData!.avatar!.isNotEmpty 
                    ? NetworkImage(_userData!.avatar!)
                    : null,
                child: _userData!.avatar == null || _userData!.avatar!.isEmpty
                    ? Icon(Icons.person, size: 50.sp)
                    : null,
              ),
              SizedBox(width: 24.w),
              
              // 基本信息
              Expanded(
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
                            color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
                          ),
                        ),
                        if (_userData!.isVerified) ...[
                          SizedBox(width: 8.w),
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
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ],
                    ),
                    SizedBox(height: 8.h),
                    Text(
                      _userData!.bio ?? '',
                      style: TextStyle(
                        fontSize: 14.sp,
                        color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// 构建统计信息区域
  Widget _buildStatsSection(bool isDark) {
    if (_userData == null) {
      return Container(
        padding: EdgeInsets.symmetric(horizontal: 16.w),
        child: Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
          ),
        ),
      );
    }
    
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 16.w),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _buildStatItem('作品', _userData!.posts, isDark),
          _buildStatItem('关注', _userData!.following, isDark),
          _buildStatItem('粉丝', _userData!.followers, isDark),
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
            color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
          ),
        ),
        SizedBox(height: 4.h),
        Text(
          label,
          style: TextStyle(
            fontSize: 14.sp,
            color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
          ),
        ),
      ],
    );
  }

  /// 构建操作按钮区域
  Widget _buildActionButtons(bool isDark) {
    return Container(
      key: _buttonsKey,
      padding: EdgeInsets.all(16.w),
      child: Row(
        children: [
          // 关注/私信按钮
          Expanded(
            child: ElevatedButton(
              onPressed: _handleFollowToggle,
              style: ElevatedButton.styleFrom(
                backgroundColor: _isFollowing ? Colors.grey : AppColors.primaryColor,
                foregroundColor: Colors.white,
                padding: EdgeInsets.symmetric(vertical: 12.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.r),
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
          SizedBox(width: 12.w),
          
          // 私信按钮
          Expanded(
            child: OutlinedButton(
              onPressed: _handleMessage,
              style: OutlinedButton.styleFrom(
                foregroundColor: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
                side: BorderSide(
                  color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
                ),
                padding: EdgeInsets.symmetric(vertical: 12.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.r),
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
          SizedBox(width: 12.w),
          
          // 更多选项按钮
          OutlinedButton(
            onPressed: _showMoreOptions,
            style: OutlinedButton.styleFrom(
              foregroundColor: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
              side: BorderSide(
                color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
              ),
              padding: EdgeInsets.symmetric(vertical: 12.h, horizontal: 16.w),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8.r),
              ),
            ),
            child: Icon(Icons.more_horiz),
          ),
        ],
      ),
    );
  }

  /// 构建Tab导航
  Widget _buildTabNavigation(bool isDark) {
    return Container(
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
            width: 1,
          ),
        ),
      ),
      child: TabBar(
        controller: _tabController,
        onTap: (index) {
          setState(() {
            _activeTab = ['all', 'moments', 'saved', 'tagged'][index];
          });
        },
        indicatorColor: AppColors.primaryColor,
        labelColor: AppColors.primaryColor,
        unselectedLabelColor: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
        tabs: const [
          Tab(text: '作品'),
          Tab(text: '动态'),
          Tab(text: '收藏'),
          Tab(text: '标签'),
        ],
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
        return allPosts.where((post) => post['type'] == 'moment').toList();
      case 'saved':
        return allPosts.where((post) => post['isSaved'] == true).toList();
      case 'tagged':
        return allPosts.where((post) => post['isTagged'] == true).toList();
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
          color: isDark ? AppColors.dark.backgroundSecondary : AppColors.light.backgroundSecondary,
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
                  color: isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary,
                  child: Icon(
                    Icons.error_outline,
                    color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
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
          color: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
          border: Border(
            bottom: BorderSide(
              color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
              width: 1,
            ),
          ),
        ),
        child: Row(
          children: [
            Text(
              _userData!.displayName,
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.bold,
                color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
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
          color: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
          border: Border(
            bottom: BorderSide(
              color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
              width: 1,
            ),
          ),
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
                  foregroundColor: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
                  side: BorderSide(
                    color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
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
                foregroundColor: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
                side: BorderSide(
                  color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
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

  /// 构建返回按钮
  Widget _buildBackButton(bool isDark) {
    return Positioned(
      top: 50.h,
      left: 16.w,
      child: GestureDetector(
        onTap: widget.onBack,
        child: Container(
          padding: EdgeInsets.all(8.w),
          decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.5),
            shape: BoxShape.circle,
          ),
          child: Icon(
            Icons.arrow_back,
            color: Colors.white,
            size: 24.sp,
          ),
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
          color: isDark ? AppColors.dark.backgroundSecondary : AppColors.light.backgroundPrimary,
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
                color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
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
        color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
        size: 20.sp,
      ),
      title: Text(
        title,
        style: TextStyle(
          color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
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
}
