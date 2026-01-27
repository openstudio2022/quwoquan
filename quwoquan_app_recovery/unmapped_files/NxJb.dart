import 'dart:math';
import 'package:quwoquan_app/features/profile/models/user_models.dart';
import 'package:quwoquan_app/features/home/models/post_models.dart';

/// Mock用户数据服务
class UserMockService {
  static final Random _random = Random();
  
  // 模拟用户数据
  static final List<User> _mockUsers = [
    User(
      id: 'user_1',
      username: '百丈虹',
      displayName: '百丈虹',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&h=300&fit=crop&crop=face',
      backgroundImage: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop',
      bio: '热爱摄影 | 旅行达人 | 生活美学\n记录生活的美好瞬间 📸',
      isVerified: true,
      followers: 12580,
      following: 892,
      posts: 156,
      likes: 1250,
      bookmarks: 89,
      isFollowing: false,
      createdAt: DateTime.now().subtract(Duration(days: 365)),
    ),
    User(
      id: 'user_2',
      username: '清风明月',
      displayName: '清风明月',
      avatar: 'https://images.unsplash.com/photo-1494790108755-2616b612b786?w=300&h=300&fit=crop&crop=face',
      backgroundImage: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop',
      bio: '设计师 | 艺术爱好者\n用设计诠释生活美学',
      isVerified: false,
      followers: 3420,
      following: 156,
      posts: 89,
      likes: 456,
      bookmarks: 23,
      isFollowing: true,
      createdAt: DateTime.now().subtract(Duration(days: 200)),
    ),
  ];

  /// 根据用户名获取用户信息
  Future<User?> getUserByUsername(String username) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(500)));
    
    try {
      return _mockUsers.firstWhere((user) => user.username == username);
    } catch (e) {
      return null;
    }
  }
  
  /// 获取用户发布的帖子
  Future<List<Post>> getUserPosts(String username, {int page = 1, int limit = 10}) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 200 + _random.nextInt(300)));
    
    // 生成模拟帖子数据
    final posts = List.generate(limit, (index) => Post(
      id: 'post_${username}_${(page - 1) * limit + index + 1}',
      author: username,
      content: '这是${username}的第${(page - 1) * limit + index + 1}个帖子',
      images: ['https://images.unsplash.com/photo-1506905925346-21bda4d32df${_random.nextInt(10)}?w=400&h=600&fit=crop'],
      likes: _random.nextInt(100),
      comments: _random.nextInt(20),
      shares: _random.nextInt(10),
      createdAt: DateTime.now().subtract(Duration(days: _random.nextInt(30))),
    ));
    
    return posts;
  }
  
  /// 获取用户作品网格
  Future<List<String>> getUserPostsGrid(String username) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 150 + _random.nextInt(200)));
    
    // 生成模拟图片URL
    return List.generate(12, (index) => 
      'https://picsum.photos/300/300?random=${_random.nextInt(1000)}'
    );
  }
  
  /// 关注用户
  Future<bool> followUser(String userId) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(200)));
    
    // 模拟操作成功
    return true;
  }
  
  /// 取消关注用户
  Future<bool> unfollowUser(String userId) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(200)));
    
    // 模拟操作成功
    return true;
  }
}
