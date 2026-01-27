import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/shared/components/immersive_media_viewer.dart' as viewer;

/// 沉浸式媒体查看器页面
class ImmersiveMediaViewerPage extends ConsumerStatefulWidget {
  final String username;
  final int initialIndex;

  const ImmersiveMediaViewerPage({
    super.key,
    required this.username,
    required this.initialIndex,
  });

  @override
  ConsumerState<ImmersiveMediaViewerPage> createState() => _ImmersiveMediaViewerPageState();
}

class _ImmersiveMediaViewerPageState extends ConsumerState<ImmersiveMediaViewerPage> {
  bool _isOpen = true;
  List<dynamic> _posts = [];
  List<viewer.MediaItem> _mediaItems = [];

  @override
  void initState() {
    super.initState();
    debugPrint('ImmersiveMediaViewerPage initState: username=${widget.username}, initialIndex=${widget.initialIndex}');
    _loadPosts();
  }

  void _loadPosts() {
    // 模拟加载用户帖子数据
    setState(() {
      _posts = [
        {
          'id': 'post_1',
          'username': widget.username,
          'displayName': '用户${widget.username}',
          'avatar': null,
          'likesCount': 42,
          'savesCount': 8,
          'commentsCount': 15,
          'mediaUrls': ['https://images.unsplash.com/photo-1506905925346-21bda4d32df1?w=400&h=600&fit=crop'],
        },
        {
          'id': 'post_2',
          'username': widget.username,
          'displayName': '用户${widget.username}',
          'avatar': null,
          'likesCount': 28,
          'savesCount': 5,
          'commentsCount': 8,
          'mediaUrls': ['https://images.unsplash.com/photo-1506905925346-21bda4d32df2?w=400&h=800&fit=crop'],
        },
        {
          'id': 'post_3',
          'username': widget.username,
          'displayName': '用户${widget.username}',
          'avatar': null,
          'likesCount': 67,
          'savesCount': 12,
          'commentsCount': 23,
          'mediaUrls': ['https://images.unsplash.com/photo-1506905925346-21bda4d32df3?w=400&h=500&fit=crop'],
        },
      ];
      
      _mediaItems = _posts.map((post) => viewer.MediaItem(
        type: 'image',
        url: post['mediaUrls'][0],
      )).toList();
    });
  }

  void _handleClose() {
    setState(() {
      _isOpen = false;
    });
    // 安全地返回到上一级页面，从哪个页面进入就返回到哪个页面
    if (context.canPop()) {
      context.pop();
    } else {
      // 如果导航栈为空，说明是直接访问的URL，此时应该回到应用根路径
      context.go('/');
    }
  }

  void _handleUserClick(String username) {
    context.go('/profile/$username');
  }

  void _handleFollowClick(String username, bool isFollowing) {
    debugPrint('Follow $username: $isFollowing');
  }

  void _handleCommentsClick(dynamic post) {
    debugPrint('Comments for post: ${post['id']}');
  }

  void _handleMoreClick(dynamic post) {
    debugPrint('More actions for post: ${post['id']}');
  }

  void _handleLikeClick(dynamic post) {
    debugPrint('Like post: ${post['id']}');
  }

  void _handleSaveClick(dynamic post) {
    debugPrint('Save post: ${post['id']}');
  }

  void _handleShareClick(dynamic post) {
    debugPrint('Share post: ${post['id']}');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: viewer.ImmersiveMediaViewer(
        isOpen: _isOpen,
        onClose: _handleClose,
        mediaItems: _mediaItems,
        initialIndex: widget.initialIndex,
        posts: _posts,
        initialPostIndex: widget.initialIndex,
        onUserClick: _handleUserClick,
        onFollowClick: _handleFollowClick,
        onCommentsClick: _handleCommentsClick,
        onMoreClick: _handleMoreClick,
        onLikeClick: _handleLikeClick,
        onSaveClick: _handleSaveClick,
        onShareClick: _handleShareClick,
        followingUsers: const {},
        savedPosts: const {},
        likedPosts: const {},
        getPostLikesCount: (post) => post['likesCount'] ?? 0,
        getPostBookmarksCount: (post) => post['savesCount'] ?? 0,
        source: 'userProfile',
        userProfileData: null,
      ),
    );
  }
}