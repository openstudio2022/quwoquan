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

final videoForceDarkProvider = NotifierProvider<VideoForceDarkNotifier, VideoForceDarkState>(() {
  return VideoForceDarkNotifier();
});

/// 视频全屏沉浸时隐藏底部导航栏
class BottomNavHiddenState {
  final bool hidden;

  const BottomNavHiddenState({this.hidden = false});
}

class BottomNavHiddenNotifier extends Notifier<BottomNavHiddenState> {
  @override
  BottomNavHiddenState build() => const BottomNavHiddenState();

  void setHidden(bool hidden) {
    state = BottomNavHiddenState(hidden: hidden);
  }
}

final bottomNavHiddenProvider =
    NotifierProvider<BottomNavHiddenNotifier, BottomNavHiddenState>(() {
  return BottomNavHiddenNotifier();
});
