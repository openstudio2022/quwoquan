import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'immersive_media_viewer.dart';

/// 视频媒体查看器
/// 直接使用ImmersiveMediaViewer，确保与图片播放器完全一致
class VideoMediaViewer extends ConsumerWidget {
  final bool isOpen;
  final VoidCallback onClose;
  final List<MediaItem> mediaItems;
  final int initialIndex;
  final List<dynamic> posts;
  final int initialPostIndex;
  final Function(String) onUserClick;
  final Function(String, bool)? onFollowClick;
  final Function(dynamic)? onCommentsClick;
  final Function(dynamic)? onMoreClick;
  final Function(dynamic)? onLikeClick;
  final Function(dynamic)? onSaveClick;
  final Function(dynamic)? onShareClick;
  final Set<String>? followingUsers;
  final Set<String>? savedPosts;
  final Set<String>? likedPosts;
  final Function(dynamic)? getPostLikesCount;
  final Function(dynamic)? getPostBookmarksCount;
  final bool isBlocked;
  final String? source;
  final Map<String, dynamic>? userProfileData;
  final bool isCommentsOpen;
  final double commentsHeight;

  const VideoMediaViewer({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.mediaItems,
    required this.initialIndex,
    required this.posts,
    required this.initialPostIndex,
    required this.onUserClick,
    this.onFollowClick,
    this.onCommentsClick,
    this.onMoreClick,
    this.onLikeClick,
    this.onSaveClick,
    this.onShareClick,
    this.followingUsers,
    this.savedPosts,
    this.likedPosts,
    this.getPostLikesCount,
    this.getPostBookmarksCount,
    this.isBlocked = false,
    this.source,
    this.userProfileData,
    this.isCommentsOpen = false,
    this.commentsHeight = 0.0,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 直接使用ImmersiveMediaViewer，确保与图片播放器完全一致
    return ImmersiveMediaViewer(
      isOpen: isOpen,
      onClose: onClose,
      mediaItems: mediaItems,
      initialIndex: initialIndex,
      posts: posts,
      initialPostIndex: initialPostIndex,
      onUserClick: onUserClick,
      onFollowClick: onFollowClick,
      onCommentsClick: onCommentsClick,
      onMoreClick: onMoreClick,
      onLikeClick: onLikeClick,
      onSaveClick: onSaveClick,
      onShareClick: onShareClick,
      followingUsers: followingUsers,
      savedPosts: savedPosts,
      likedPosts: likedPosts,
      getPostLikesCount: getPostLikesCount,
      getPostBookmarksCount: getPostBookmarksCount,
      isBlocked: isBlocked,
      source: source,
      userProfileData: userProfileData,
      isCommentsOpen: isCommentsOpen,
      commentsHeight: commentsHeight,
    );
  }
}