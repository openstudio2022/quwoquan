import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import '../../../shared/widgets/custom_button.dart';
import '../../../core/theme/app_theme.dart';

class FeedPage extends StatefulWidget {
  const FeedPage({super.key});

  @override
  State<FeedPage> createState() => _FeedPageState();
}

class _FeedPageState extends State<FeedPage> {
  final ScrollController _scrollController = ScrollController();
  bool _isLoading = false;

  // 模拟数据
  final List<FeedPost> _posts = [
    FeedPost(
      id: '1',
      author: '张三',
      avatar: 'https://via.placeholder.com/40',
      content: '今天天气真好，适合出门拍照！📸',
      images: ['https://via.placeholder.com/300x200'],
      likes: 24,
      comments: 8,
      shares: 3,
      timeAgo: '2小时前',
      isLiked: false,
    ),
    FeedPost(
      id: '2',
      author: '李四',
      avatar: 'https://via.placeholder.com/40',
      content: '分享一个超棒的Flutter开发技巧，让你的应用性能提升50%！',
      images: ['https://via.placeholder.com/300x200', 'https://via.placeholder.com/300x200'],
      likes: 156,
      comments: 23,
      shares: 45,
      timeAgo: '4小时前',
      isLiked: true,
    ),
    FeedPost(
      id: '3',
      author: '王五',
      avatar: 'https://via.placeholder.com/40',
      content: '周末和朋友一起爬山，山顶的风景太美了！',
      images: ['https://via.placeholder.com/300x200'],
      likes: 89,
      comments: 12,
      shares: 7,
      timeAgo: '1天前',
      isLiked: false,
    ),
  ];

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('首页'),
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
            icon: const Icon(Icons.notifications_outlined),
            onPressed: () {
              // TODO: 实现通知功能
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('通知功能开发中...')),
              );
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refreshFeed,
        child: ListView.builder(
          controller: _scrollController,
          padding: EdgeInsets.symmetric(vertical: 8.h),
          itemCount: _posts.length,
          itemBuilder: (context, index) {
            return FeedPostCard(
              post: _posts[index],
              onLike: () => _toggleLike(index),
              onComment: () => _showComments(index),
              onShare: () => _sharePost(index),
              onProfileTap: () => _goToProfile(_posts[index].author),
            );
          },
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.go('/create'),
        backgroundColor: AppTheme.primaryColor,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Future<void> _refreshFeed() async {
    setState(() {
      _isLoading = true;
    });

    try {
      // TODO: 实现刷新逻辑
      await Future.delayed(const Duration(seconds: 1));
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _toggleLike(int index) {
    setState(() {
      _posts[index] = _posts[index].copyWith(
        isLiked: !_posts[index].isLiked,
        likes: _posts[index].isLiked 
            ? _posts[index].likes - 1 
            : _posts[index].likes + 1,
      );
    });
  }

  void _showComments(int index) {
    // TODO: 实现评论功能
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('评论功能开发中...')),
    );
  }

  void _sharePost(int index) {
    // TODO: 实现分享功能
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('分享功能开发中...')),
    );
  }

  void _goToProfile(String username) {
    // TODO: 实现跳转到用户资料
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('跳转到 $username 的资料页')),
    );
  }
}

class FeedPostCard extends StatelessWidget {
  final FeedPost post;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onShare;
  final VoidCallback onProfileTap;

  const FeedPostCard({
    super.key,
    required this.post,
    required this.onLike,
    required this.onComment,
    required this.onShare,
    required this.onProfileTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 16.w, vertical: 8.h),
      child: Padding(
        padding: EdgeInsets.all(16.w),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 用户信息
            Row(
              children: [
                GestureDetector(
                  onTap: onProfileTap,
                  child: CircleAvatar(
                    radius: 20.r,
                    backgroundImage: NetworkImage(post.avatar),
                  ),
                ),
                SizedBox(width: 12.w),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GestureDetector(
                        onTap: onProfileTap,
                        child: Text(
                          post.author,
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      Text(
                        post.timeAgo,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.more_horiz),
                  onPressed: () {
                    _showMoreOptions(context);
                  },
                ),
              ],
            ),
            
            SizedBox(height: 12.h),
            
            // 内容
            Text(
              post.content,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            
            SizedBox(height: 12.h),
            
            // 图片
            if (post.images.isNotEmpty)
              Container(
                height: 200.h,
                child: PageView.builder(
                  itemCount: post.images.length,
                  itemBuilder: (context, index) {
                    return Container(
                      margin: EdgeInsets.only(right: 8.w),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8.r),
                        image: DecorationImage(
                          image: NetworkImage(post.images[index]),
                          fit: BoxFit.cover,
                        ),
                      ),
                    );
                  },
                ),
              ),
            
            SizedBox(height: 16.h),
            
            // 互动按钮
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildActionButton(
                  icon: post.isLiked ? Icons.favorite : Icons.favorite_border,
                  label: '${post.likes}',
                  color: post.isLiked ? AppTheme.errorColor : AppTheme.textSecondary,
                  onTap: onLike,
                ),
                _buildActionButton(
                  icon: Icons.chat_bubble_outline,
                  label: '${post.comments}',
                  onTap: onComment,
                ),
                _buildActionButton(
                  icon: Icons.share_outlined,
                  label: '${post.shares}',
                  onTap: onShare,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    Color? color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16.w, vertical: 8.h),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: color ?? AppTheme.textSecondary,
              size: 20.sp,
            ),
            SizedBox(width: 4.w),
            Text(
              label,
              style: TextStyle(
                color: color ?? AppTheme.textSecondary,
                fontSize: 14.sp,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showMoreOptions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (context) => Container(
        padding: EdgeInsets.all(16.w),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.bookmark_border),
              title: const Text('收藏'),
              onTap: () {
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('收藏功能开发中...')),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.report_outlined),
              title: const Text('举报'),
              onTap: () {
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('举报功能开发中...')),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

// 数据模型
class FeedPost {
  final String id;
  final String author;
  final String avatar;
  final String content;
  final List<String> images;
  final int likes;
  final int comments;
  final int shares;
  final String timeAgo;
  final bool isLiked;

  const FeedPost({
    required this.id,
    required this.author,
    required this.avatar,
    required this.content,
    required this.images,
    required this.likes,
    required this.comments,
    required this.shares,
    required this.timeAgo,
    required this.isLiked,
  });

  FeedPost copyWith({
    String? id,
    String? author,
    String? avatar,
    String? content,
    List<String>? images,
    int? likes,
    int? comments,
    int? shares,
    String? timeAgo,
    bool? isLiked,
  }) {
    return FeedPost(
      id: id ?? this.id,
      author: author ?? this.author,
      avatar: avatar ?? this.avatar,
      content: content ?? this.content,
      images: images ?? this.images,
      likes: likes ?? this.likes,
      comments: comments ?? this.comments,
      shares: shares ?? this.shares,
      timeAgo: timeAgo ?? this.timeAgo,
      isLiked: isLiked ?? this.isLiked,
    );
  }
}

