import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_core/quwoquan_core.dart';
import '../immersive_media_viewer.dart';
import 'package:quwoquan_app/features/home/models/post_models.dart';
import '../../../features/profile/models/user_models.dart';

/// 媒体类型枚举
enum MediaType {
  image,
  video,
}

/// 媒体查看器状态
class MediaViewerState {
  final bool isOpen;
  final List<MediaItem> mediaItems;
  final List<Post> posts;
  final int currentIndex;
  final int currentPostIndex;
  final String source;
  final User? userProfileData;
  final bool isVideoMode;
  final bool isPlaying;
  final double playbackPosition;

  const MediaViewerState({
    this.isOpen = false,
    this.mediaItems = const [],
    this.posts = const [],
    this.currentIndex = 0,
    this.currentPostIndex = 0,
    this.source = 'feed',
    this.userProfileData,
    this.isVideoMode = false,
    this.isPlaying = false,
    this.playbackPosition = 0.0,
  });

  MediaViewerState copyWith({
    bool? isOpen,
    List<MediaItem>? mediaItems,
    List<Post>? posts,
    int? currentIndex,
    int? currentPostIndex,
    String? source,
    User? userProfileData,
    bool? isVideoMode,
    bool? isPlaying,
    double? playbackPosition,
  }) {
    return MediaViewerState(
      isOpen: isOpen ?? this.isOpen,
      mediaItems: mediaItems ?? this.mediaItems,
      posts: posts ?? this.posts,
      currentIndex: currentIndex ?? this.currentIndex,
      currentPostIndex: currentPostIndex ?? this.currentPostIndex,
      source: source ?? this.source,
      userProfileData: userProfileData ?? this.userProfileData,
      isVideoMode: isVideoMode ?? this.isVideoMode,
      isPlaying: isPlaying ?? this.isPlaying,
      playbackPosition: playbackPosition ?? this.playbackPosition,
    );
  }
}

/// 媒体查看器状态管理器
class MediaViewerNotifier extends StateNotifier<MediaViewerState> {
  MediaViewerNotifier() : super(const MediaViewerState());

  /// 打开媒体查看器
  void openViewer({
    required List<MediaItem> mediaItems,
    required List<Post> posts,
    required int initialIndex,
    required int initialPostIndex,
    String source = 'feed',
    User? userProfileData,
  }) {
    final currentMedia = mediaItems[initialIndex];
    final isVideoMode = currentMedia.type == MediaType.video;

    state = state.copyWith(
      isOpen: true,
      mediaItems: mediaItems,
      posts: posts,
      currentIndex: initialIndex,
      currentPostIndex: initialPostIndex,
      source: source,
      userProfileData: userProfileData,
      isVideoMode: isVideoMode,
      isPlaying: isVideoMode,
    );
  }

  /// 关闭媒体查看器
  void closeViewer() {
    state = state.copyWith(
      isOpen: false,
      isPlaying: false,
      playbackPosition: 0.0,
    );
  }

  /// 切换到下一个媒体
  void nextMedia() {
    if (state.currentIndex < state.mediaItems.length - 1) {
      final newIndex = state.currentIndex + 1;
      final currentMedia = state.mediaItems[newIndex];
      
      state = state.copyWith(
        currentIndex: newIndex,
        isVideoMode: currentMedia.type == MediaType.video,
        isPlaying: currentMedia.type == MediaType.video,
        playbackPosition: 0.0,
      );
    }
  }

  /// 切换到上一个媒体
  void previousMedia() {
    if (state.currentIndex > 0) {
      final newIndex = state.currentIndex - 1;
      final currentMedia = state.mediaItems[newIndex];
      
      state = state.copyWith(
        currentIndex: newIndex,
        isVideoMode: currentMedia.type == MediaType.video,
        isPlaying: currentMedia.type == MediaType.video,
        playbackPosition: 0.0,
      );
    }
  }

  /// 跳转到指定媒体
  void goToMedia(int index) {
    if (index >= 0 && index < state.mediaItems.length) {
      final currentMedia = state.mediaItems[index];
      
      state = state.copyWith(
        currentIndex: index,
        isVideoMode: currentMedia.type == MediaType.video,
        isPlaying: currentMedia.type == MediaType.video,
        playbackPosition: 0.0,
      );
    }
  }

  /// 切换视频播放状态
  void toggleVideoPlayback() {
    if (state.isVideoMode) {
      state = state.copyWith(
        isPlaying: !state.isPlaying,
      );
    }
  }

  /// 更新播放位置
  void updatePlaybackPosition(double position) {
    state = state.copyWith(playbackPosition: position);
  }

  /// 重置状态
  void reset() {
    state = const MediaViewerState();
  }
}

/// 媒体查看器状态提供者
final mediaViewerProvider = StateNotifierProvider<MediaViewerNotifier, MediaViewerState>((ref) {
  return MediaViewerNotifier();
});

/// 便捷访问器
final isMediaViewerOpenProvider = Provider<bool>((ref) {
  return ref.watch(mediaViewerProvider).isOpen;
});

final currentMediaItemProvider = Provider<MediaItem?>((ref) {
  final state = ref.watch(mediaViewerProvider);
  if (state.mediaItems.isNotEmpty && state.currentIndex < state.mediaItems.length) {
    return state.mediaItems[state.currentIndex];
  }
  return null;
});

final isVideoModeProvider = Provider<bool>((ref) {
  return ref.watch(mediaViewerProvider).isVideoMode;
});

final isPlayingProvider = Provider<bool>((ref) {
  return ref.watch(mediaViewerProvider).isPlaying;
});

