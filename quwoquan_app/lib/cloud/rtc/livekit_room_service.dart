import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';

enum RtcConnectionState { disconnected, connecting, connected, reconnecting }

extension LiveKitQualityMapping on ConnectionQuality {
  NetworkQuality toNetworkQuality() => switch (this) {
    ConnectionQuality.excellent => NetworkQuality.good,
    ConnectionQuality.good => NetworkQuality.slight,
    ConnectionQuality.poor => NetworkQuality.poor,
    _ => NetworkQuality.weak,
  };
}

class LiveKitRoomService {
  Room? _room;
  EventsListener<RoomEvent>? _listener;
  bool _cameraPausedForWeakNetwork = false;

  final _connectionState = ValueNotifier(RtcConnectionState.disconnected);
  final _activeSpeaker = ValueNotifier<String?>(null);
  final _connectionQuality = ValueNotifier<ConnectionQuality>(
    ConnectionQuality.excellent,
  );

  ValueListenable<RtcConnectionState> get connectionState => _connectionState;
  ValueListenable<String?> get activeSpeaker => _activeSpeaker;
  ValueListenable<ConnectionQuality> get connectionQuality =>
      _connectionQuality;

  Room? get room => _room;
  LocalParticipant? get localParticipant => _room?.localParticipant;
  List<RemoteParticipant> get remoteParticipants =>
      _room?.remoteParticipants.values.toList() ?? [];

  final _participantsChanged = StreamController<void>.broadcast();
  Stream<void> get onParticipantsChanged => _participantsChanged.stream;

  final _disconnected = StreamController<DisconnectReason?>.broadcast();
  Stream<DisconnectReason?> get onDisconnected => _disconnected.stream;

  Future<void> connect({
    required String url,
    required String token,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {
    if (_room != null) {
      await disconnect();
    }
    _connectionState.value = RtcConnectionState.connecting;

    try {
      _room = Room(
        roomOptions: RoomOptions(
          adaptiveStream: true,
          dynacast: true,
          defaultAudioPublishOptions: const AudioPublishOptions(dtx: true),
          defaultVideoPublishOptions: const VideoPublishOptions(
            simulcast: true,
            videoCodec: 'VP8',
          ),
          defaultScreenShareCaptureOptions: const ScreenShareCaptureOptions(
            useiOSBroadcastExtension: true,
          ),
        ),
      );

      _setupListeners();

      await _room!.connect(url, token);
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
          name: 'LiveKitRoomService',
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
      ..on<ParticipantConnectedEvent>((_) => _notifyParticipantsChanged())
      ..on<ParticipantDisconnectedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackPublishedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackUnpublishedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackSubscribedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackUnsubscribedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackMutedEvent>((_) => _notifyParticipantsChanged())
      ..on<TrackUnmutedEvent>((_) => _notifyParticipantsChanged())
      ..on<ActiveSpeakersChangedEvent>((event) {
        if (event.speakers.isNotEmpty) {
          _activeSpeaker.value = event.speakers.first.identity;
        }
      })
      ..on<ParticipantConnectionQualityUpdatedEvent>((event) {
        if (event.participant == _room!.localParticipant) {
          _connectionQuality.value = event.connectionQuality;
          _applyWeakNetworkAdaptation(event.connectionQuality);
        }
      })
      ..on<RoomDisconnectedEvent>((event) {
        _connectionState.value = RtcConnectionState.disconnected;
        _disconnected.add(event.reason);
      })
      ..on<RoomReconnectingEvent>((_) {
        _connectionState.value = RtcConnectionState.reconnecting;
      })
      ..on<RoomReconnectedEvent>((_) {
        _connectionState.value = RtcConnectionState.connected;
      });
  }

  void _applyWeakNetworkAdaptation(ConnectionQuality quality) {
    final lp = _room?.localParticipant;
    if (lp == null) return;

    switch (quality) {
      case ConnectionQuality.excellent:
      case ConnectionQuality.good:
        if (_cameraPausedForWeakNetwork) {
          for (final pub in lp.videoTrackPublications) {
            if (pub.source != TrackSource.camera || pub.muted) continue;
            final track = pub.track;
            if (track != null) {
              track.mediaStreamTrack.enabled = true;
            }
          }
          _cameraPausedForWeakNetwork = false;
        }
        break;
      case ConnectionQuality.poor:
        for (final pub in lp.videoTrackPublications) {
          if (pub.source != TrackSource.camera || pub.muted) continue;
          final track = pub.track;
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
    } else if (_connectionQuality.value == ConnectionQuality.poor) {
      _applyWeakNetworkAdaptation(ConnectionQuality.poor);
    }
  }

  Future<void> switchCamera() async {
    final publication = _requireLocalParticipant().videoTrackPublications
        .where((pub) => pub.source == TrackSource.camera)
        .firstOrNull;
    final track = publication?.track;
    if (track != null) {
      final opts = track.currentOptions;
      final current = opts is CameraCaptureOptions
          ? opts.cameraPosition
          : CameraPosition.front;
      final next = current == CameraPosition.front
          ? CameraPosition.back
          : CameraPosition.front;
      await track.setCameraPosition(next);
      return;
    }
    throw StateError('rtc camera track is unavailable');
  }

  Future<void> setSpeakerOn(bool speakerOn) async {
    await Hardware.instance.setSpeakerphoneOn(speakerOn);
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

  LocalParticipant _requireLocalParticipant() {
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
        name: 'LiveKitRoomService',
        error: error.runtimeType,
        stackTrace: stackTrace,
      );
    }
  }
}
