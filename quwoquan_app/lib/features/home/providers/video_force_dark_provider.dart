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

