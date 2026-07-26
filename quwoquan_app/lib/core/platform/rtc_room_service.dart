import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:livekit_client/livekit_client.dart' as livekit;

enum RtcConnectionState { disconnected, connecting, connected, reconnecting }

/// 与 RTC 厂商无关的网络质量语义。
enum RtcNetworkQuality { excellent, good, poor, weak }

/// 不向 UI 泄漏厂商视频轨道类型的媒体句柄。
final class RtcVideoTrack {
  const RtcVideoTrack._(this._delegate);

  final livekit.VideoTrack _delegate;
}

/// 不向业务/UI 泄漏厂商 Participant 的参与者运行态快照。
final class RtcParticipantSnapshot {
  const RtcParticipantSnapshot({
    required this.identity,
    required this.name,
    required this.isMuted,
    required this.isCameraOn,
    required this.isSpeaking,
    required this.audioLevel,
    required this.cameraTrack,
    required this.screenShareTrack,
    required this.isLocal,
  });

  final String identity;
  final String name;
  final bool isMuted;
  final bool isCameraOn;
  final bool isSpeaking;
  final double audioLevel;
  final RtcVideoTrack? cameraTrack;
  final RtcVideoTrack? screenShareTrack;
  final bool isLocal;
}

/// 厂商 RTC SDK 的唯一平台防腐实现。
class RtcRoomService {
  RtcRoomService({String connectionUrl = ''})
    : _connectionUrl = connectionUrl.trim();

  final String _connectionUrl;
  livekit.Room? _room;
  livekit.EventsListener<livekit.RoomEvent>? _listener;
  bool _cameraPausedForWeakNetwork = false;

  final _connectionState = ValueNotifier(RtcConnectionState.disconnected);
  final _activeSpeaker = ValueNotifier<String?>(null);
  final _connectionQuality = ValueNotifier<RtcNetworkQuality>(
    RtcNetworkQuality.excellent,
  );

  ValueListenable<RtcConnectionState> get connectionState => _connectionState;
  ValueListenable<String?> get activeSpeaker => _activeSpeaker;
  ValueListenable<RtcNetworkQuality> get connectionQuality =>
      _connectionQuality;

  RtcParticipantSnapshot? get localParticipant {
    final participant = _room?.localParticipant;
    return participant == null
        ? null
        : _participantSnapshot(participant, isLocal: true);
  }

  List<RtcParticipantSnapshot> get remoteParticipants => _room == null
      ? const <RtcParticipantSnapshot>[]
      : _room!.remoteParticipants.values
            .map((participant) => _participantSnapshot(participant))
            .toList(growable: false);

  final _participantsChanged = StreamController<void>.broadcast();
  Stream<void> get onParticipantsChanged => _participantsChanged.stream;

  final _disconnected = StreamController<livekit.DisconnectReason?>.broadcast();
  Stream<livekit.DisconnectReason?> get onDisconnected => _disconnected.stream;

  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {
    if (_connectionUrl.isEmpty) {
      throw StateError('RTC media transport configuration is unavailable');
    }
    if (_room != null) {
      await disconnect();
    }
    _connectionState.value = RtcConnectionState.connecting;

    try {
      _room = livekit.Room(
        roomOptions: const livekit.RoomOptions(
          adaptiveStream: true,
          dynacast: true,
          defaultAudioPublishOptions: livekit.AudioPublishOptions(dtx: true),
          defaultVideoPublishOptions: livekit.VideoPublishOptions(
            simulcast: true,
            videoCodec: 'VP8',
          ),
          defaultScreenShareCaptureOptions: livekit.ScreenShareCaptureOptions(
            useiOSBroadcastExtension: true,
          ),
        ),
      );

      _setupListeners();

      await _room!.connect(_connectionUrl, accessToken);
      _connectionState.value = RtcConnectionState.connected;
      final localParticipant = _requireLocalParticipant();

      if (enableAudio) {
        await localParticipant.setMicrophoneEnabled(true);
      }
      if (enableVideo) {
        await localParticipant.setCameraEnabled(true);
      }
    } catch (error, stackTrace) {
      try {
        await disconnect();
      } catch (cleanupError, cleanupStackTrace) {
        developer.log(
          'RTC room cleanup after connect failure failed',
          name: 'RtcRoomService',
          error: cleanupError.runtimeType,
          stackTrace: cleanupStackTrace,
        );
      }
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  void _setupListeners() {
    _listener = _room!.createListener();
    _listener!
      ..on<livekit.ParticipantConnectedEvent>(
        (_) => _notifyParticipantsChanged(),
      )
      ..on<livekit.ParticipantDisconnectedEvent>(
        (_) => _notifyParticipantsChanged(),
      )
      ..on<livekit.TrackPublishedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.TrackUnpublishedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.TrackSubscribedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.TrackUnsubscribedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.TrackMutedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.TrackUnmutedEvent>((_) => _notifyParticipantsChanged())
      ..on<livekit.ActiveSpeakersChangedEvent>((event) {
        if (event.speakers.isNotEmpty) {
          _activeSpeaker.value = event.speakers.first.identity;
        }
      })
      ..on<livekit.ParticipantConnectionQualityUpdatedEvent>((event) {
        if (event.participant == _room!.localParticipant) {
          _connectionQuality.value = _networkQuality(event.connectionQuality);
          _applyWeakNetworkAdaptation(event.connectionQuality);
        }
      })
      ..on<livekit.RoomDisconnectedEvent>((event) {
        _connectionState.value = RtcConnectionState.disconnected;
        _disconnected.add(event.reason);
      })
      ..on<livekit.RoomReconnectingEvent>((_) {
        _connectionState.value = RtcConnectionState.reconnecting;
      })
      ..on<livekit.RoomReconnectedEvent>((_) {
        _connectionState.value = RtcConnectionState.connected;
      });
  }

  RtcNetworkQuality _networkQuality(livekit.ConnectionQuality quality) =>
      switch (quality) {
        livekit.ConnectionQuality.excellent => RtcNetworkQuality.excellent,
        livekit.ConnectionQuality.good => RtcNetworkQuality.good,
        livekit.ConnectionQuality.poor => RtcNetworkQuality.poor,
        _ => RtcNetworkQuality.weak,
      };

  RtcParticipantSnapshot _participantSnapshot(
    livekit.Participant participant, {
    bool isLocal = false,
  }) {
    final cameraPublication = participant.videoTrackPublications
        .where(
          (publication) => publication.source == livekit.TrackSource.camera,
        )
        .firstOrNull;
    final cameraTrack = cameraPublication?.track;
    final screenSharePublication = participant.videoTrackPublications
        .where(
          (publication) =>
              publication.source == livekit.TrackSource.screenShareVideo,
        )
        .firstOrNull;
    final screenShareTrack = screenSharePublication?.track;
    return RtcParticipantSnapshot(
      identity: participant.identity,
      name: participant.name,
      isMuted: participant.isMuted,
      isCameraOn:
          cameraTrack is livekit.VideoTrack && !cameraPublication!.muted,
      isSpeaking: participant.isSpeaking,
      audioLevel: participant.audioLevel,
      cameraTrack: cameraTrack is livekit.VideoTrack
          ? RtcVideoTrack._(cameraTrack)
          : null,
      screenShareTrack:
          screenShareTrack is livekit.VideoTrack &&
              !screenSharePublication!.muted
          ? RtcVideoTrack._(screenShareTrack)
          : null,
      isLocal: isLocal,
    );
  }

  void _applyWeakNetworkAdaptation(livekit.ConnectionQuality quality) {
    final participant = _room?.localParticipant;
    if (participant == null) return;

    switch (quality) {
      case livekit.ConnectionQuality.excellent:
      case livekit.ConnectionQuality.good:
        if (_cameraPausedForWeakNetwork) {
          for (final publication in participant.videoTrackPublications) {
            if (publication.source != livekit.TrackSource.camera ||
                publication.muted) {
              continue;
            }
            final track = publication.track;
            if (track != null) {
              track.mediaStreamTrack.enabled = true;
            }
          }
          _cameraPausedForWeakNetwork = false;
        }
        break;
      case livekit.ConnectionQuality.poor:
        for (final publication in participant.videoTrackPublications) {
          if (publication.source != livekit.TrackSource.camera ||
              publication.muted) {
            continue;
          }
          final track = publication.track;
          if (track != null) {
            track.mediaStreamTrack.enabled = false;
            _cameraPausedForWeakNetwork = true;
          }
        }
        break;
      default:
        break;
    }
  }

  void _notifyParticipantsChanged() {
    _participantsChanged.add(null);
  }

  Future<void> setMicrophoneEnabled(bool enabled) async {
    await _requireLocalParticipant().setMicrophoneEnabled(enabled);
  }

  Future<void> setCameraEnabled(bool enabled) async {
    await _requireLocalParticipant().setCameraEnabled(enabled);
    if (!enabled) {
      _cameraPausedForWeakNetwork = false;
    } else if (_connectionQuality.value == RtcNetworkQuality.poor) {
      _applyWeakNetworkAdaptation(livekit.ConnectionQuality.poor);
    }
  }

  Future<void> switchCamera() async {
    final publication = _requireLocalParticipant().videoTrackPublications
        .where(
          (publication) => publication.source == livekit.TrackSource.camera,
        )
        .firstOrNull;
    final track = publication?.track;
    if (track != null) {
      final options = track.currentOptions;
      final current = options is livekit.CameraCaptureOptions
          ? options.cameraPosition
          : livekit.CameraPosition.front;
      final next = current == livekit.CameraPosition.front
          ? livekit.CameraPosition.back
          : livekit.CameraPosition.front;
      await track.setCameraPosition(next);
      return;
    }
    throw StateError('rtc camera track is unavailable');
  }

  Future<void> setSpeakerOn(bool speakerOn) async {
    await livekit.Hardware.instance.setSpeakerphoneOn(speakerOn);
  }

  Future<void> startScreenShare() async {
    await _requireLocalParticipant().setScreenShareEnabled(true);
  }

  Future<void> stopScreenShare() async {
    await _requireLocalParticipant().setScreenShareEnabled(false);
  }

  Future<void> disconnect() async {
    final room = _room;
    _room = null;
    _listener?.dispose();
    _listener = null;
    _cameraPausedForWeakNetwork = false;
    _connectionState.value = RtcConnectionState.disconnected;
    _activeSpeaker.value = null;

    Object? firstError;
    StackTrace? firstStackTrace;
    try {
      await room?.disconnect();
    } catch (error, stackTrace) {
      firstError = error;
      firstStackTrace = stackTrace;
    }
    try {
      await room?.dispose();
    } catch (error, stackTrace) {
      firstError ??= error;
      firstStackTrace ??= stackTrace;
    }
    if (firstError != null) {
      Error.throwWithStackTrace(firstError, firstStackTrace!);
    }
  }

  livekit.LocalParticipant _requireLocalParticipant() {
    final participant = _room?.localParticipant;
    if (participant == null) {
      throw StateError('rtc local participant is unavailable');
    }
    return participant;
  }

  void dispose() {
    unawaited(_disconnectForDispose());
    _participantsChanged.close();
    _disconnected.close();
    _connectionState.dispose();
    _activeSpeaker.dispose();
    _connectionQuality.dispose();
  }

  Future<void> _disconnectForDispose() async {
    try {
      await disconnect();
    } catch (error, stackTrace) {
      developer.log(
        'RTC room cleanup during dispose failed',
        name: 'RtcRoomService',
        error: error.runtimeType,
        stackTrace: stackTrace,
      );
    }
  }
}

/// 平台层唯一的视频轨道渲染器。
class RtcVideoTrackRenderer extends StatelessWidget {
  const RtcVideoTrackRenderer({
    super.key,
    required this.track,
    this.fit = RtcVideoViewFit.cover,
  });

  final RtcVideoTrack track;
  final RtcVideoViewFit fit;

  @override
  Widget build(BuildContext context) {
    return livekit.VideoTrackRenderer(
      track._delegate,
      fit: switch (fit) {
        RtcVideoViewFit.cover => livekit.VideoViewFit.cover,
        RtcVideoViewFit.contain => livekit.VideoViewFit.contain,
      },
    );
  }
}

enum RtcVideoViewFit { cover, contain }
