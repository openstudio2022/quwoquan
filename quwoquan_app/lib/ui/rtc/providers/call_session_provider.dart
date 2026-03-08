import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:quwoquan_app/cloud/rtc/livekit_room_service.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';

class CallSessionState {
  final CallSessionDto? session;
  final CallStatus status;
  final CallType callType;
  final bool isMuted;
  final bool isCameraOn;
  final bool isRecording;
  final bool isScreenSharing;
  final bool isLoading;
  final String? error;

  const CallSessionState({
    this.session,
    this.status = CallStatus.initiated,
    this.callType = CallType.audio,
    this.isMuted = false,
    this.isCameraOn = false,
    this.isRecording = false,
    this.isScreenSharing = false,
    this.isLoading = false,
    this.error,
  });

  CallSessionState copyWith({
    CallSessionDto? session,
    CallStatus? status,
    CallType? callType,
    bool? isMuted,
    bool? isCameraOn,
    bool? isRecording,
    bool? isScreenSharing,
    bool? isLoading,
    String? error,
  }) {
    return CallSessionState(
      session: session ?? this.session,
      status: status ?? this.status,
      callType: callType ?? this.callType,
      isMuted: isMuted ?? this.isMuted,
      isCameraOn: isCameraOn ?? this.isCameraOn,
      isRecording: isRecording ?? this.isRecording,
      isScreenSharing: isScreenSharing ?? this.isScreenSharing,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallSessionState &&
          runtimeType == other.runtimeType &&
          session?.id == other.session?.id &&
          status == other.status &&
          isMuted == other.isMuted &&
          isCameraOn == other.isCameraOn &&
          isRecording == other.isRecording &&
          isScreenSharing == other.isScreenSharing &&
          isLoading == other.isLoading &&
          error == other.error;

  @override
  int get hashCode => Object.hash(
        session?.id,
        status,
        isMuted,
        isCameraOn,
        isRecording,
        isScreenSharing,
        isLoading,
        error,
      );
}

final liveKitRoomServiceProvider = Provider<LiveKitRoomService>((ref) {
  final service = LiveKitRoomService();
  ref.onDispose(() => service.dispose());
  return service;
});

class CallSessionNotifier extends Notifier<CallSessionState> {
  Timer? _timeoutTimer;
  StreamSubscription<void>? _participantsSub;
  StreamSubscription<lk.DisconnectReason?>? _disconnectSub;

  @override
  CallSessionState build() => const CallSessionState();

  RtcRepository get _repo => ref.read(rtcRepositoryProvider);
  LiveKitRoomService get _lkRoom => ref.read(liveKitRoomServiceProvider);

  String get _livekitUrl {
    final base = CloudRuntimeConfig.gatewayBaseUrl;
    return base.replaceFirst(RegExp(r'/v\d+.*$'), '').replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://') + ':7880';
  }

  Future<String?> initiateCall({
    required String callTypeStr,
    required List<String> targetUserIds,
    String? conversationId,
  }) async {
    if (state.isLoading) return null;
    try {
      state = state.copyWith(
        isLoading: true,
        error: null,
        callType: CallType.fromString(callTypeStr),
        isCameraOn: callTypeStr == 'video',
        status: CallStatus.initiated,
      );

      final map = await _repo.initiateCall(
        callType: callTypeStr,
        inviteeIds: targetUserIds,
        conversationId: conversationId,
      );
      final session = CallSessionDto.fromMap(map);

      state = state.copyWith(
        session: session,
        status: CallStatus.ringing,
        isLoading: false,
      );

      ref.read(activeCallProvider.notifier).startCall(
            callId: session.id,
            callType: callTypeStr,
            participants: session.participants,
          );

      final token = map['token'] as String? ?? '';
      if (token.isNotEmpty) {
        await _connectToLiveKit(token, enableVideo: callTypeStr == 'video');
      }

      _startTimeoutTimer();
      return session.id;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      return null;
    }
  }

  Future<void> answerCall(String callId) async {
    if (state.isLoading) return;
    try {
      state = state.copyWith(isLoading: true, error: null);
      _cancelTimeoutTimer();

      final map = await _repo.answerCall(callId);
      final session = CallSessionDto.fromMap(map);
      final type = CallType.fromString(session.callType);
      final token = map['token'] as String? ?? '';
      final roomId = map['roomId'] as String? ?? '';

      state = state.copyWith(
        session: session,
        status: CallStatus.inCall,
        callType: type,
        isCameraOn: type.isVideo,
        isLoading: false,
      );

      ref.read(activeCallProvider.notifier).startCall(
            callId: session.id,
            callType: session.callType,
            participants: session.participants,
          );

      if (token.isNotEmpty) {
        await _connectToLiveKit(token, enableVideo: type.isVideo);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> rejectCall(String callId) async {
    try {
      _cancelTimeoutTimer();
      await _repo.rejectCall(callId);
      _endCallState();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      _endCallState();
    }
  }

  Future<void> cancelCall() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      _cancelTimeoutTimer();
      await _repo.hangUp(callId);
      _endCallState();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      _endCallState();
    }
  }

  Future<void> hangupCall() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      _cancelTimeoutTimer();
      await _repo.hangUp(callId);
      _endCallState();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      _endCallState();
    }
  }

  Future<void> joinCall(String callId) async {
    if (state.isLoading) return;
    try {
      state = state.copyWith(isLoading: true, error: null);

      final tokenMap = await _repo.joinRtcToken(callId);
      final token = tokenMap['token'] as String? ?? '';
      final sessionMap = await _repo.getCallSession(callId);
      final session = CallSessionDto.fromMap(sessionMap);
      final type = CallType.fromString(session.callType);

      state = state.copyWith(
        session: session,
        status: CallStatus.inCall,
        callType: type,
        isCameraOn: type.isVideo,
        isLoading: false,
      );

      ref.read(activeCallProvider.notifier).startCall(
            callId: session.id,
            callType: session.callType,
            participants: session.participants,
          );

      if (token.isNotEmpty) {
        await _connectToLiveKit(token, enableVideo: type.isVideo);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> leaveCall() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      await _repo.hangUp(callId);
      _endCallState();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      _endCallState();
    }
  }

  Future<void> inviteToCall(List<String> userIds) async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      final sessionMap = await _repo.getCallSession(callId);
      final session = CallSessionDto.fromMap(sessionMap);
      state = state.copyWith(session: session);
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> toggleMute() async {
    final callId = state.session?.id;
    if (callId == null) return;
    final newMuted = !state.isMuted;
    state = state.copyWith(isMuted: newMuted);
    try {
      await _lkRoom.setMicrophoneEnabled(!newMuted);
      await _repo.muteToggle(callId: callId, muted: newMuted);
    } catch (e) {
      state = state.copyWith(isMuted: !newMuted, error: e.toString());
    }
  }

  Future<void> toggleCamera() async {
    final callId = state.session?.id;
    if (callId == null) return;
    final newCameraOn = !state.isCameraOn;
    state = state.copyWith(isCameraOn: newCameraOn);
    try {
      await _lkRoom.setCameraEnabled(newCameraOn);
      await _repo.cameraToggle(callId: callId, cameraOn: newCameraOn);
    } catch (e) {
      state = state.copyWith(isCameraOn: !newCameraOn, error: e.toString());
    }
  }

  Future<void> startRecording() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      await _repo.startRecording(callId);
      state = state.copyWith(isRecording: true);
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> stopRecording() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      await _repo.stopRecording(callId);
      state = state.copyWith(isRecording: false);
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> startScreenShare() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      await _lkRoom.startScreenShare();
      await _repo.startScreenShare(callId);
      state = state.copyWith(isScreenSharing: true);
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> stopScreenShare() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      await _lkRoom.stopScreenShare();
      await _repo.stopScreenShare(callId);
      state = state.copyWith(isScreenSharing: false);
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  void loadFromSession(CallSessionDto session) {
    final type = CallType.fromString(session.callType);
    state = CallSessionState(
      session: session,
      status: CallStatus.fromString(session.status),
      callType: type,
      isCameraOn: type.isVideo,
      isMuted: false,
      isRecording: session.isRecording,
      isScreenSharing: session.isScreenSharing,
    );
  }

  Future<void> _connectToLiveKit(String token, {bool enableVideo = false}) async {
    try {
      await _lkRoom.connect(
        url: _livekitUrl,
        token: token,
        enableVideo: enableVideo,
        enableAudio: true,
      );

      _lkRoom.connectionQuality.addListener(_onQualityChanged);

      _participantsSub = _lkRoom.onParticipantsChanged.listen((_) {
        // Trigger UI rebuild by notifying participant providers
      });

      _disconnectSub = _lkRoom.onDisconnected.listen((reason) {
        if (reason != null) {
          _endCallState();
        }
      });
    } catch (e) {
      state = state.copyWith(error: 'LiveKit 连接失败: $e');
    }
  }

  void _onQualityChanged() {
    final q = _lkRoom.connectionQuality.value;
    ref.read(callQualityProvider.notifier).update(q.toNetworkQuality());
  }

  void _endCallState() {
    _cancelTimeoutTimer();
    _participantsSub?.cancel();
    _disconnectSub?.cancel();
    _lkRoom.connectionQuality.removeListener(_onQualityChanged);
    _lkRoom.disconnect();
    ref.read(activeCallProvider.notifier).endCall();
    state = state.copyWith(status: CallStatus.ended, isLoading: false);
  }

  void _startTimeoutTimer() {
    _cancelTimeoutTimer();
    _timeoutTimer = Timer(const Duration(seconds: 30), () {
      if (state.status == CallStatus.ringing ||
          state.status == CallStatus.initiated) {
        cancelCall();
      }
    });
  }

  void _cancelTimeoutTimer() {
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
  }
}

final callSessionProvider =
    NotifierProvider<CallSessionNotifier, CallSessionState>(
  CallSessionNotifier.new,
);
