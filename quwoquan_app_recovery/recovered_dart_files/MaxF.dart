import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/shared/components/author_profile.dart';
import 'package:quwoquan_app/shared/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/shared/components/comment_system/comment_models.dart';

/// 用户主页页面 - 基于AuthorProfile组件实现
class UserProfilePage extends ConsumerWidget {
  final String username;

  const UserProfilePage({
    super.key,
    required this.username,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AuthorProfile(
      username: username,
      onBack: () => context.pop(), // 使用pop保持导航栈状态
      onPhotoClick: (post, mediaIndex, postList, source, userProfileData) => _handlePhotoClick(context, post, mediaIndex, postList, source, userProfileData),
      onFollowClick: _handleFollowClick,
      onCommentsClick: (post) => _handleCommentsClick(context, post),
      onLikeClick: _handleLikeClick,
      onSaveClick: _handleSaveClick,
      onShareClick: _handleShareClick,
      followingUsers: const {}, // TODO: 从状态管理获取
      likedPosts: const {}, // TODO: 从状态管理获取
      savedPosts: const {}, // TODO: 从状态管理获取
      getPostLikesCount: (post) => post['likesCount'] ?? 0,
      getPostBookmarksCount: (post) => post['savesCount'] ?? 0,
      isCurrentUser: false, // 他人主页
      modal: false, // 全屏模式
    );
  }

  /// 处理图片点击
  void _handlePhotoClick(BuildContext context, dynamic post, int mediaIndex, List<dynamic> postList, String source, dynamic userProfileData) {
    // 导航到媒体查看器，使用push保持导航栈
    context.push('/media-viewer/${post['username']}/$mediaIndex');
  }

  /// 处理关注点击
  void _handleFollowClick(String username, bool isFollowing) {
    // TODO: 实现关注/取消关注逻辑
    debugPrint('Follow $username: $isFollowing');
  }

  /// 处理评论点击
  void _handleCommentsClick(BuildContext context, dynamic post) {
    // 显示评论弹窗
    final commentConfig = CommentConfig(
      postId: post['id'] ?? 'mock_post_id',
      postAuthorId: post['username'] ?? 'mock_author_id',
      allowComments: true,
      isUserLoggedIn: true, // TODO: 从状态管理获取
      isUserAuthor: false, // TODO: 检查是否为作者
    );

    CommentViewer.showModal(
      context: context,
      postId: post['id'] ?? 'mock_post_id',
      initialComments: [], // 初始为空，由CommentViewer内部加载
      config: commentConfig,
      modalHeight: CommentModalHeight.adaptive,
      onCommentAdded: (commentId) {
        debugPrint('Comment added: $commentId');
      },
      onCommentLiked: (comment) {
        debugPrint('Comment liked: ${comment.id}');
      },
      onReplyAdded: (commentId, replyId) {
        debugPrint('Reply added: $replyId to $commentId');
      },
      onUserTapped: (comment) {
        debugPrint('User tapped: ${comment.username}');
      },
      onLoadMore: () {
        debugPrint('Load more comments');
      },
      onClose: () {
        debugPrint('Comment modal closed');
      },
    );
  }

  /// 处理点赞点击
  void _handleLikeClick(dynamic post) {
    // TODO: 实现点赞/取消点赞逻辑
    debugPrint('Like post: ${post['id']}');
  }

  /// 处理收藏点击
  void _handleSaveClick(dynamic post) {
    // TODO: 实现收藏/取消收藏逻辑
    debugPrint('Save post: ${post['id']}');
  }

  /// 处理分享点击
  void _handleShareClick(dynamic post) {
    // TODO: 实现分享逻辑
    debugPrint('Share post: ${post['id']}');
  }
}
