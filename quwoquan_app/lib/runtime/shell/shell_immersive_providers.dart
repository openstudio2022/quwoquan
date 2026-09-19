import 'package:flutter_riverpod/flutter_riverpod.dart';

class VideoForceDarkState {
  final bool forceDark;

  const VideoForceDarkState({this.forceDark = false});

  VideoForceDarkState copyWith({bool? forceDark}) {
    return VideoForceDarkState(forceDark: forceDark ?? this.forceDark);
  }
}

class VideoForceDarkNotifier extends Notifier<VideoForceDarkState> {
  @override
  VideoForceDarkState build() {
    return const VideoForceDarkState();
  }

  void setForceDark(bool forceDark) {
    state = state.copyWith(forceDark: forceDark);
  }
}

final videoForceDarkProvider =
    NotifierProvider<VideoForceDarkNotifier, VideoForceDarkState>(() {
      return VideoForceDarkNotifier();
    });

/// 视频全屏沉浸时隐藏底部导航栏
class BottomNavHiddenState {
  const BottomNavHiddenState({
    this.baseHidden = false,
    this.mediaHidden = false,
  });

  final bool baseHidden;

  /// 仅由媒体租约集合是否非空派生，Web chrome 不消费基础底栏隐藏。
  final bool mediaHidden;

  bool get hidden => baseHidden || mediaHidden;

  @override
  bool operator ==(Object other) =>
      other is BottomNavHiddenState &&
      other.baseHidden == baseHidden &&
      other.mediaHidden == mediaHidden;

  @override
  int get hashCode => Object.hash(baseHidden, mediaHidden);
}

class BottomNavHiddenNotifier extends Notifier<BottomNavHiddenState> {
  bool _baseHidden = false;
  final Set<Object> _mediaOwners = <Object>{};

  @override
  BottomNavHiddenState build() => const BottomNavHiddenState();

  void setHidden(bool hidden) {
    _baseHidden = hidden;
    _publish();
  }

  /// 租约只叠加沉浸隐藏，不改写主壳自己的状态。
  /// 旧 viewer 迟到释放不会覆盖新 viewer 或主壳后续命令。
  void Function() acquireMediaHidden() {
    final owner = Object();
    _mediaOwners.add(owner);
    _publish();
    return () {
      if (_mediaOwners.remove(owner)) _publish();
    };
  }

  void _publish() {
    // 查看器帧后释放租约时，整个 ProviderScope 可能已随路由一起卸载。
    if (!ref.mounted) return;
    state = BottomNavHiddenState(
      baseHidden: _baseHidden,
      mediaHidden: _mediaOwners.isNotEmpty,
    );
  }
}

final bottomNavHiddenProvider =
    NotifierProvider<BottomNavHiddenNotifier, BottomNavHiddenState>(() {
      return BottomNavHiddenNotifier();
    });
