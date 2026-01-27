import 'dart:math';
import 'package:quwoquan_app/shared/components/comment_system/comment_models.dart';

/// 评论Mock服务
/// 提供模拟的评论数据
class CommentMockService {
  static final Random _random = Random();
  
  // 模拟评论数据
  static final List<CommentModel> _mockComments = [];
  
  static void _initializeMockData() {
    if (_mockComments.isNotEmpty) return;
    
    // 模拟用户数据
    final users = [
      {'username': 'user1', 'displayName': '百丈虹', 'avatar': null, 'location': '福建漳州', 'device': 'iPhone 14', 'role': '元老'},
      {'username': 'user2', 'displayName': '清风明月', 'avatar': null, 'location': '北京', 'device': 'Android', 'role': 'VIP'},
      {'username': 'user3', 'displayName': '云淡风轻', 'avatar': null, 'location': '上海', 'device': 'iPhone 13', 'role': '普通用户'},
    ];
    
    // 模拟帖子ID列表
    final postIds = List.generate(20, (index) => 'post_$index');
    
    // 模拟评论文本
    final commentTexts = [
      '这张照片太美了！👍',
      '拍得真不错，构图很棒',
      '我也去过这个地方，真的很漂亮',
      '请问这是在哪里拍的？',
      '色彩搭配很和谐',
      '技术越来越好了',
      '收藏了，谢谢分享',
      '很有创意的角度',
      '光线处理得很好',
      '这个角度很特别',
      '拍出了不一样的感觉',
      '构图很有层次感',
      '色彩饱和度刚好',
      '很有意境的一张照片',
      '拍摄技巧很棒',
      '这个场景很熟悉',
      '拍出了诗意的感觉',
      '很有艺术感',
      '构图很平衡',
      '光线运用得很好',
    ];
    
    int commentId = 0;
    
    // 为每个帖子生成一些评论
    for (final postId in postIds) {
      // 每个帖子随机生成3-15条评论
      final commentCount = 3 + _random.nextInt(13);
      
      for (int i = 0; i < commentCount; i++) {
        final user = users[_random.nextInt(users.length)];
        final commentText = commentTexts[_random.nextInt(commentTexts.length)];
        
        final comment = CommentModel(
          id: 'comment_$commentId',
          username: user['username'] as String,
          displayName: user['displayName'] as String,
          avatar: user['avatar'] as String?,
          text: commentText,
          likes: _random.nextInt(50),
          timeAgo: '${_random.nextInt(24)}小时前',
          location: user['location'] as String?,
          deviceInfo: user['device'] as String?,
          isAuthor: _random.nextBool(),
          userRole: user['role'] as String?,
          roleType: _getRoleType(user['role'] as String),
          replies: [],
          replyCount: _random.nextInt(5),
          isLiked: _random.nextBool(),
          isAuthorLiked: _random.nextBool(),
          parentId: null,
          level: 0,
          floorNumber: i + 1,
          isCollapsed: false,
          isHidden: false,
          canReply: true,
          canLike: true,
          postId: postId,
          createdAt: DateTime.now().subtract(Duration(hours: _random.nextInt(48))),
        );
        
        _mockComments.add(comment);
        commentId++;
      }
    }
  }
  
  static UserRoleType _getRoleType(String role) {
    switch (role) {
      case '元老': return UserRoleType.elder;
      case 'VIP': return UserRoleType.vip;
      case '版主': return UserRoleType.moderator;
      case '管理员': return UserRoleType.admin;
      default: return UserRoleType.normal;
    }
  }

  /// 获取帖子的评论列表
  Future<List<CommentModel>> getPostComments({
    required String postId,
    int page = 1,
    int limit = 20,
  }) async {
    _initializeMockData();
    
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(500)));
    
    // 根据postId过滤评论
    final postComments = _mockComments.where((comment) => comment.postId == postId).toList();
    
    final startIndex = (page - 1) * limit;
    final endIndex = startIndex + limit;
    
    if (startIndex >= postComments.length) {
      return [];
    }
    
    return postComments.sublist(
      startIndex,
      endIndex > postComments.length ? postComments.length : endIndex,
    );
  }

  /// 添加评论
  Future<CommentModel> addComment({
    required String postId,
    required String text,
    String? parentId,
  }) async {
    _initializeMockData();
    
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 200 + _random.nextInt(300)));
    
    final newComment = CommentModel(
      id: 'comment_${DateTime.now().millisecondsSinceEpoch}',
      username: 'current_user',
      displayName: '当前用户',
      avatar: null,
      text: text,
      likes: 0,
      timeAgo: '刚刚',
      location: '未知位置',
      deviceInfo: 'Flutter App',
      isAuthor: true,
      userRole: '普通用户',
      roleType: UserRoleType.normal,
      replies: [],
      replyCount: 0,
      isLiked: false,
      isAuthorLiked: false,
      parentId: parentId,
      level: parentId != null ? 1 : 0,
      floorNumber: _mockComments.length + 1,
      isCollapsed: false,
      isHidden: false,
      canReply: true,
      canLike: true,
      postId: postId,
      createdAt: DateTime.now(),
    );
    
    _mockComments.add(newComment);
    return newComment;
  }

  /// 添加回复
  Future<CommentModel> addReply({
    required String postId,
    required String commentId,
    required String text,
  }) async {
    return await addComment(
      postId: postId,
      text: text,
      parentId: commentId,
    );
  }

  /// 点赞/取消点赞评论
  Future<bool> toggleCommentLike({
    required String commentId,
    required bool isLiked,
  }) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 80 + _random.nextInt(150)));
    
    // 模拟操作成功
    return true;
  }

  /// 删除评论
  Future<bool> deleteComment({
    required String commentId,
  }) async {
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(200)));
    
    _mockComments.removeWhere((comment) => comment.id == commentId);
    return true;
  }

  /// 获取评论的回复列表
  Future<List<CommentModel>> getCommentReplies({
    required String commentId,
    int page = 1,
    int limit = 10,
  }) async {
    _initializeMockData();
    
    // 模拟网络延迟
    await Future.delayed(Duration(milliseconds: 100 + _random.nextInt(300)));
    
    final replies = _mockComments
        .where((comment) => comment.parentId == commentId)
        .toList();
    
    final startIndex = (page - 1) * limit;
    final endIndex = startIndex + limit;
    
    if (startIndex >= replies.length) {
      return [];
    }
    
    return replies.sublist(
      startIndex,
      endIndex > replies.length ? replies.length : endIndex,
    );
  }
}
