import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/shared/components/immersive_media_viewer.dart';
import 'package:quwoquan_app/shared/components/video_media_viewer.dart';

/// 视频媒体查看器页面
/// 专门处理视频播放的沉浸式查看器
class VideoMediaViewerPage extends ConsumerStatefulWidget {
  final int initialIndex;
  final List<MediaItem> mediaItems;
  final List<dynamic> posts;

  const VideoMediaViewerPage({
    super.key,
    required this.initialIndex,
    required this.mediaItems,
    required this.posts,
  });

  @override
  ConsumerState<VideoMediaViewerPage> createState() => _VideoMediaViewerPageState();
}

class _VideoMediaViewerPageState extends ConsumerState<VideoMediaViewerPage> {
  bool _isOpen = true;
  Set<String> _followingUsers = {};
  Set<String> _savedPosts = {};
  Set<String> _likedPosts = {};

  @override
  void initState() {
    super.initState();
    // 模拟用户数据
    _followingUsers = {'user1', 'user3'};
    _savedPosts = {'video_2'};
    _likedPosts = {'video_1', 'video_3'};
  }

  void _onClose() {
    setState(() {
      _isOpen = false;
    });
    context.pop();
  }

  void _onUserClick(String username) {
    context.go('/user/$username');
  }

  void _onFollowClick(String username, bool isFollowing) {
    setState(() {
      if (isFollowing) {
        _followingUsers.add(username);
      } else {
        _followingUsers.remove(username);
      }
    });
  }

  void _onCommentsClick(dynamic post) {
    // 显示评论弹窗
    debugPrint('Comments clicked for post: ${post['id']}');
  }

  void _onMoreClick(dynamic post) {
    // 显示更多操作弹窗
    debugPrint('More clicked for post: ${post['id']}');
  }

  void _onLikeClick(dynamic post) {
    setState(() {
      final postId = post['id'] as String;
      if (_likedPosts.contains(postId)) {
        _likedPosts.remove(postId);
      } else {
        _likedPosts.add(postId);
      }
    });
  }

  void _onSaveClick(dynamic post) {
    setState(() {
      final postId = post['id'] as String;
      if (_savedPosts.contains(postId)) {
        _savedPosts.remove(postId);
      } else {
        _savedPosts.add(postId);
      }
    });
  }

  void _onShareClick(dynamic post) {
    // 处理分享
    debugPrint('Share clicked for post: ${post['id']}');
  }

  int _getPostLikesCount(dynamic post) {
    return post['likesCount'] as int? ?? 0;
  }

  int _getPostBookmarksCount(dynamic post) {
    return post['savesCount'] as int? ?? 0;
  }

  @override
  Widget build(BuildContext context) {
    return VideoMediaViewer(
      isOpen: _isOpen,
      onClose: _onClose,
      mediaItems: widget.mediaItems,
      initialIndex: widget.initialIndex,
      posts: widget.posts,
      initialPostIndex: widget.initialIndex,
      onUserClick: _onUserClick,
      onFollowClick: _onFollowClick,
      onCommentsClick: _onCommentsClick,
      onMoreClick: _onMoreClick,
      onLikeClick: _onLikeClick,
      onSaveClick: _onSaveClick,
      onShareClick: _onShareClick,
      followingUsers: _followingUsers,
      savedPosts: _savedPosts,
      likedPosts: _likedPosts,
      getPostLikesCount: _getPostLikesCount,
      getPostBookmarksCount: _getPostBookmarksCount,
      isBlocked: false,
      source: 'video',
      isCommentsOpen: false,
      commentsHeight: 0.0,
    );
  }
}
