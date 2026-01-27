import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/profile/models/user_models.dart';
import 'package:quwoquan_app/features/profile/services/user_service_provider.dart';

/// 我的主页 - 采用与作者主页一致的架构，并修复下拉拉伸问题
class MyProfilePage extends ConsumerStatefulWidget {
  const MyProfilePage({super.key});

  @override
  ConsumerState<MyProfilePage> createState() => _MyProfilePageState();
}

class _MyProfilePageState extends ConsumerState<MyProfilePage> with TickerProviderStateMixin {
  late TabController _tabController;
  late ScrollController _scrollController;
  late AnimationController _pullController; // 下拉动画控制器
  
  bool _loading = true;
  String? _error;
  
  // 下拉效果相关
  double _pullOffset = 0.0; // 逻辑拉伸偏移量
  
  // 用户数据
  User? _userData;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _scrollController = ScrollController();
    _pullController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    
    _setupScrollListener();
    
    // 加载当前登录用户信息
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadCurrentUserData();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _scrollController.dispose();
    _pullController.dispose();
    super.dispose();
  }

  /// 加载当前用户数据
  void _loadCurrentUserData() async {
    try {
      // 这里应该使用当前登录用户的用户名，暂时使用模拟数据或从provider获取
      final userDataNotifier = ref.read(userDataProvider.notifier);
      await userDataNotifier.loadUser('test_user'); 
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = '加载个人数据失败: $e';
        });
      }
    }
  }

  void _setupScrollListener() {
    _scrollController.addListener(() {
      if (mounted) {
        setState(() {
          // 触发重建以应用位移补偿
        });
      }
    });
  }

  /// 处理滚动通知 - 实现背景图拉伸效果
  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final scrollOffset = notification.metrics.pixels;
      
      if (scrollOffset < 0) {
        if (mounted) {
          setState(() {
            _pullOffset = -scrollOffset; // 1:1 拉伸，不设阻尼以保证不突破
          });
        }
      } else {
        if (_pullOffset != 0) {
          if (mounted) {
            setState(() {
              _pullOffset = 0;
            });
          }
        }
      }
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    // 监听用户数据
    ref.listen<AsyncValue<User?>>(userDataProvider, (previous, next) {
      next.when(
        data: (User? userData) {
          if (userData != null && mounted) {
            setState(() {
              _userData = userData;
              _loading = false;
            });
          }
        },
        loading: () {
          if (mounted) setState(() => _loading = true);
        },
        error: (error, _) {
          if (mounted) {
            setState(() {
              _loading = false;
              _error = error.toString();
            });
          }
        },
      );
    });

    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (_error != null) return Scaffold(body: Center(child: Text(_error!)));

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent,
        extendBodyBehindAppBar: true, // 🔑 关键：允许侵入状态栏
        body: _buildScrollableContent(isDark),
      ),
    );
  }

  Widget _buildScrollableContent(bool isDark) {
    final double screenQuarter = MediaQuery.of(context).size.height * 0.25;
    final double paddingTop = MediaQuery.of(context).padding.top;
    final double backgroundHeight = screenQuarter + paddingTop;
    
    final double scrollOffset = _scrollController.hasClients ? _scrollController.offset : 0.0;
    final double pullOffset = scrollOffset < 0 ? -scrollOffset : 0.0;

    // 🔑 核心修复逻辑：
    // 1. bgTop = scrollOffset (仅下拉时)，抵消物理位移
    final double bgTop = scrollOffset < 0 ? scrollOffset : 0;
    // 2. 动态高度包含拉伸量
    final double dynamicBgHeight = backgroundHeight + pullOffset;
    // 3. 内容区起点
    final double userContentTop = backgroundHeight;

    return NotificationListener<ScrollNotification>(
      onNotification: _handleScrollNotification,
      child: CustomScrollView(
        controller: _scrollController,
        physics: const BouncingScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: SizedBox(
              height: userContentTop + 400.h, // 调低预估高度，由内容自适应
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  // 1. 背景图 - 精准补偿位移
                  Positioned(
                    top: bgTop, // 🔑 抵消物理位移，保持顶部固定
                    left: 0,
                    right: 0,
                    height: dynamicBgHeight, // 🔑 随下拉拉伸
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.grey[300],
                        image: DecorationImage(
                          image: NetworkImage(_userData?.backgroundImage ?? 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop'),
                          fit: BoxFit.cover,
                          alignment: Alignment.topCenter,
                        ),
                      ),
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.transparent, Colors.black.withValues(alpha: 0.3)],
                          ),
                        ),
                      ),
                    ),
                  ),
                  
                  // 2. 用户区 - 紧贴背景底部
                  Positioned(
                    top: userContentTop,
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
                          _buildUserInfoSection(isDark),
                          // 头像
                          Positioned(
                            top: 0,
                            left: AppSpacing.md.w,
                            child: Transform.translate(
                              offset: Offset(0, -45.r), // 侵入背景
                              child: CircleAvatar(
                                radius: 45.r,
                                backgroundColor: Colors.white,
                                child: CircleAvatar(
                                  radius: 42.r,
                                  backgroundImage: NetworkImage(_userData?.avatar ?? ''),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          
          // Tab + Grid
          SliverToBoxAdapter(
            child: Container(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
              child: Column(
                children: [
                  _buildTabNavigation(isDark),
                  _buildStatsSection(isDark),
                  _buildSimplePostsGrid(isDark),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUserInfoSection(bool isDark) {
    return Padding(
      padding: EdgeInsets.fromLTRB(AppSpacing.md.w, 60.h, AppSpacing.md.w, AppSpacing.md.h),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _userData?.displayName ?? '',
            style: TextStyle(
              fontSize: 20.sp,
              fontWeight: FontWeight.bold,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
            ),
          ),
          SizedBox(height: 4.h),
          Text(
            '@${_userData?.username ?? ""}',
            style: TextStyle(
              fontSize: 14.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
          ),
          SizedBox(height: 8.h),
          Text(
            _userData?.bio ?? '这个人很懒...',
            style: TextStyle(
              fontSize: 14.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatsSection(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 16.h),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _buildStatItem('作品', _userData?.posts ?? 0, isDark),
          _buildStatItem('关注', _userData?.following ?? 0, isDark),
          _buildStatItem('点赞', _userData?.likes ?? 0, isDark),
        ],
      ),
    );
  }

  Widget _buildStatItem(String label, int count, bool isDark) {
    return Column(
      children: [
        Text(count.toString(), style: TextStyle(fontSize: 18.sp, fontWeight: FontWeight.bold)),
        Text(label, style: TextStyle(fontSize: 12.sp, color: Colors.grey)),
      ],
    );
  }

  Widget _buildTabNavigation(bool isDark) {
    return Container(
      height: 48.h,
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: Colors.grey.withValues(alpha: 0.2))),
      ),
      child: const Center(child: Text('作品', style: TextStyle(fontWeight: FontWeight.bold))),
    );
  }

  Widget _buildSimplePostsGrid(bool isDark) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.all(8.w),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        crossAxisSpacing: 2,
        mainAxisSpacing: 2,
      ),
      itemCount: 12,
      itemBuilder: (context, index) => Container(color: Colors.grey[200]),
    );
  }
}
