import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import '../../../core/theme/app_theme.dart';

class DiscoveryPage extends StatefulWidget {
  const DiscoveryPage({super.key});

  @override
  State<DiscoveryPage> createState() => _DiscoveryPageState();
}

class _DiscoveryPageState extends State<DiscoveryPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final List<String> _categories = ['推荐', '关注', '热门', '最新'];

  // 模拟数据
  final List<DiscoveryItem> _recommendedItems = [
    DiscoveryItem(
      id: '1',
      title: 'Flutter开发技巧分享',
      author: '技术达人',
      image: 'https://via.placeholder.com/200x300',
      likes: 1250,
      type: 'article',
    ),
    DiscoveryItem(
      id: '2',
      title: '美丽的日落风景',
      author: '摄影师小王',
      image: 'https://via.placeholder.com/300x200',
      likes: 890,
      type: 'image',
    ),
    DiscoveryItem(
      id: '3',
      title: '美食制作教程',
      author: '美食博主',
      image: 'https://via.placeholder.com/250x350',
      likes: 2100,
      type: 'video',
    ),
    DiscoveryItem(
      id: '4',
      title: '旅行日记：日本之旅',
      author: '旅行者',
      image: 'https://via.placeholder.com/300x250',
      likes: 1560,
      type: 'article',
    ),
    DiscoveryItem(
      id: '5',
      title: '健身打卡第30天',
      author: '健身达人',
      image: 'https://via.placeholder.com/200x400',
      likes: 750,
      type: 'image',
    ),
    DiscoveryItem(
      id: '6',
      title: '音乐分享：治愈系歌曲',
      author: '音乐爱好者',
      image: 'https://via.placeholder.com/300x300',
      likes: 980,
      type: 'music',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _categories.length, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('发现'),
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () {
              // TODO: 实现搜索功能
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('搜索功能开发中...')),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.filter_list),
            onPressed: () {
              _showFilterOptions();
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: _categories.map((category) => Tab(text: category)).toList(),
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildRecommendedTab(),
          _buildFollowingTab(),
          _buildTrendingTab(),
          _buildLatestTab(),
        ],
      ),
    );
  }

  Widget _buildRecommendedTab() {
    return RefreshIndicator(
      onRefresh: () async {
        // TODO: 实现刷新逻辑
        await Future.delayed(const Duration(seconds: 1));
      },
      child: MasonryGridView.count(
        padding: EdgeInsets.all(8.w),
        crossAxisCount: 2,
        mainAxisSpacing: 8.h,
        crossAxisSpacing: 8.w,
        itemCount: _recommendedItems.length,
        itemBuilder: (context, index) {
          return _buildDiscoveryCard(_recommendedItems[index]);
        },
      ),
    );
  }

  Widget _buildFollowingTab() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.people_outline,
            size: 64.sp,
            color: AppTheme.textSecondary,
          ),
          SizedBox(height: 16.h),
          Text(
            '关注的内容',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          SizedBox(height: 8.h),
          Text(
            '关注更多用户，发现精彩内容',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: AppTheme.textSecondary,
            ),
          ),
          SizedBox(height: 24.h),
          ElevatedButton(
            onPressed: () {
              // TODO: 实现推荐关注功能
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('推荐关注功能开发中...')),
              );
            },
            child: const Text('发现用户'),
          ),
        ],
      ),
    );
  }

  Widget _buildTrendingTab() {
    return ListView.builder(
      padding: EdgeInsets.all(8.w),
      itemCount: 10,
      itemBuilder: (context, index) {
        return Card(
          margin: EdgeInsets.symmetric(vertical: 4.h),
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: AppTheme.primaryColor,
              child: Text('${index + 1}'),
            ),
            title: Text('热门话题 ${index + 1}'),
            subtitle: Text('${(index + 1) * 1000} 讨论'),
            trailing: const Icon(Icons.trending_up),
            onTap: () {
              // TODO: 实现话题详情
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('话题 ${index + 1} 详情开发中...')),
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildLatestTab() {
    return RefreshIndicator(
      onRefresh: () async {
        // TODO: 实现刷新逻辑
        await Future.delayed(const Duration(seconds: 1));
      },
      child: MasonryGridView.count(
        padding: EdgeInsets.all(8.w),
        crossAxisCount: 2,
        mainAxisSpacing: 8.h,
        crossAxisSpacing: 8.w,
        itemCount: _recommendedItems.length,
        itemBuilder: (context, index) {
          return _buildDiscoveryCard(_recommendedItems[index]);
        },
      ),
    );
  }

  Widget _buildDiscoveryCard(DiscoveryItem item) {
    return GestureDetector(
      onTap: () {
        _showItemDetail(item);
      },
      child: Card(
        elevation: 2,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 图片
            Container(
              height: _getRandomHeight(),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.vertical(top: Radius.circular(8.r)),
                image: DecorationImage(
                  image: NetworkImage(item.image),
                  fit: BoxFit.cover,
                ),
              ),
              child: Stack(
                children: [
                  Positioned(
                    top: 8.h,
                    right: 8.w,
                    child: Container(
                      padding: EdgeInsets.symmetric(horizontal: 6.w, vertical: 2.h),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(4.r),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            _getTypeIcon(item.type),
                            color: Colors.white,
                            size: 12.sp,
                          ),
                          SizedBox(width: 2.w),
                          Text(
                            _getTypeLabel(item.type),
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 10.sp,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            
            // 内容
            Padding(
              padding: EdgeInsets.all(8.w),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: 4.h),
                  Text(
                    item.author,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AppTheme.textSecondary,
                    ),
                  ),
                  SizedBox(height: 8.h),
                  Row(
                    children: [
                      Icon(
                        Icons.favorite_border,
                        size: 14.sp,
                        color: AppTheme.textSecondary,
                      ),
                      SizedBox(width: 4.w),
                      Text(
                        _formatLikes(item.likes),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  double _getRandomHeight() {
    final heights = [120.h, 160.h, 200.h, 180.h, 140.h];
    return heights[DateTime.now().millisecond % heights.length];
  }

  IconData _getTypeIcon(String type) {
    switch (type) {
      case 'video':
        return Icons.play_circle_outline;
      case 'image':
        return Icons.image;
      case 'music':
        return Icons.music_note;
      default:
        return Icons.article;
    }
  }

  String _getTypeLabel(String type) {
    switch (type) {
      case 'video':
        return '视频';
      case 'image':
        return '图片';
      case 'music':
        return '音乐';
      default:
        return '文章';
    }
  }

  String _formatLikes(int likes) {
    if (likes >= 1000) {
      return '${(likes / 1000).toStringAsFixed(1)}k';
    }
    return likes.toString();
  }

  void _showItemDetail(DiscoveryItem item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.3,
        maxChildSize: 0.95,
        builder: (context, scrollController) => Container(
          decoration: BoxDecoration(
            color: Theme.of(context).scaffoldBackgroundColor,
            borderRadius: BorderRadius.vertical(top: Radius.circular(16.r)),
          ),
          child: Column(
            children: [
              Container(
                width: 40.w,
                height: 4.h,
                margin: EdgeInsets.symmetric(vertical: 12.h),
                decoration: BoxDecoration(
                  color: AppTheme.dividerColor,
                  borderRadius: BorderRadius.circular(2.r),
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  controller: scrollController,
                  padding: EdgeInsets.all(16.w),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      SizedBox(height: 8.h),
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 16.r,
                            backgroundColor: AppTheme.primaryColor,
                            child: Text(
                              item.author[0],
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 12.sp,
                              ),
                            ),
                          ),
                          SizedBox(width: 8.w),
                          Text(
                            item.author,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ],
                      ),
                      SizedBox(height: 16.h),
                      Container(
                        height: 200.h,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(8.r),
                          image: DecorationImage(
                            image: NetworkImage(item.image),
                            fit: BoxFit.cover,
                          ),
                        ),
                      ),
                      SizedBox(height: 16.h),
                      Text(
                        '这里是详细内容...',
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showFilterOptions() {
    showModalBottomSheet(
      context: context,
      builder: (context) => Container(
        padding: EdgeInsets.all(16.w),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '筛选选项',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            SizedBox(height: 16.h),
            ListTile(
              leading: const Icon(Icons.image),
              title: const Text('图片'),
              trailing: Switch(
                value: true,
                onChanged: (value) {},
              ),
            ),
            ListTile(
              leading: const Icon(Icons.video_library),
              title: const Text('视频'),
              trailing: Switch(
                value: false,
                onChanged: (value) {},
              ),
            ),
            ListTile(
              leading: const Icon(Icons.article),
              title: const Text('文章'),
              trailing: Switch(
                value: true,
                onChanged: (value) {},
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DiscoveryItem {
  final String id;
  final String title;
  final String author;
  final String image;
  final int likes;
  final String type;

  const DiscoveryItem({
    required this.id,
    required this.title,
    required this.author,
    required this.image,
    required this.likes,
    required this.type,
  });
}

