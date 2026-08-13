import 'dart:async';

import 'package:audio_session/audio_session.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';

/// RTC 通话音频会话事件（平台中断事实的类型化投影）。
enum CallAudioSessionEvent {
  /// 系统中断开始（来电、闹钟、其他 App 抢占）：应本地静音采集。
  interruptionBegan,

  /// 中断结束且系统建议恢复：可恢复采集（尊重用户主动静音）。
  interruptionEndedShouldResume,

  /// 中断结束但不建议自动恢复：保持当前状态，等待用户动作。
  interruptionEnded,

  /// 音频输出即将外放（如耳机拔出）：应切回听筒防止外放泄露。
  becameNoisy,
}

/// RTC 通话音频会话防腐层。
///
/// 业务只表达「为通话激活 / 释放 / 订阅中断事实」；playAndRecord 配置、
/// AVAudioSession/AudioFocus 差异与失败降级在此收口。音频会话失败不得
/// 打断通话主流程（LiveKit 自身有媒体兜底），因此失败静默降级并留观测。
abstract interface class CallAudioSessionGateway {
  /// 以通话配置（playAndRecord + voiceChat + 蓝牙路由）激活音频会话。
  ///
  /// 返回是否激活成功；失败/能力缺失返回 false，调用方不因此失败。
  Future<bool> activateForCall();

  /// 通话收尾释放音频会话（幂等）。
  Future<void> deactivate();

  /// 平台中断/路由事实流。
  Stream<CallAudioSessionEvent> get events;
}

/// audio_session 实现（Android/iOS）。
///
/// 蓝牙路由裁决（v1 最小集）：配置层允许蓝牙（allowBluetooth），系统自动
/// 跟随已连接的蓝牙设备路由；App 内 `AudioOutput` 仍只暴露听筒/扬声器，
/// 蓝牙设备选择 UI 留给系统层（扩展入口见 call-experience OPEN）。
final class AudioSessionCallAudioSessionGateway
    implements CallAudioSessionGateway {
  AudioSessionCallAudioSessionGateway();

  final StreamController<CallAudioSessionEvent> _events =
      StreamController<CallAudioSessionEvent>.broadcast();
  StreamSubscription<AudioInterruptionEvent>? _interruptionSub;
  StreamSubscription<void>? _noisySub;

  @override
  Stream<CallAudioSessionEvent> get events => _events.stream;

  @override
  Future<bool> activateForCall() async {
    try {
      final session = await AudioSession.instance;
      await session.configure(
        const AudioSessionConfiguration(
          avAudioSessionCategory: AVAudioSessionCategory.playAndRecord,
          avAudioSessionCategoryOptions:
              AVAudioSessionCategoryOptions.allowBluetooth,
          avAudioSessionMode: AVAudioSessionMode.voiceChat,
          androidAudioAttributes: AndroidAudioAttributes(
            contentType: AndroidAudioContentType.speech,
            usage: AndroidAudioUsage.voiceCommunication,
          ),
          androidAudioFocusGainType: AndroidAudioFocusGainType.gain,
          androidWillPauseWhenDucked: false,
        ),
      );
      final active = await session.setActive(true);
      if (active) {
        await _interruptionSub?.cancel();
        _interruptionSub = session.interruptionEventStream.listen((event) {
          if (event.begin) {
            _events.add(CallAudioSessionEvent.interruptionBegan);
            return;
          }
          _events.add(
            event.type == AudioInterruptionType.pause
                ? CallAudioSessionEvent.interruptionEndedShouldResume
                : CallAudioSessionEvent.interruptionEnded,
          );
        });
        await _noisySub?.cancel();
        _noisySub = session.becomingNoisyEventStream.listen((_) {
          _events.add(CallAudioSessionEvent.becameNoisy);
        });
      }
      return active;
    } catch (error, stackTrace) {
      // 音频会话激活失败=通话可能无声，用户可感知；降级为 false 的同时
      // 必须结构化上报。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'platform.call_audio_session.activate',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      return false;
    }
  }

  @override
  Future<void> deactivate() async {
    await _interruptionSub?.cancel();
    _interruptionSub = null;
    await _noisySub?.cancel();
    _noisySub = null;
    try {
      final session = await AudioSession.instance;
      await session.setActive(false);
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'platform.call_audio_session.deactivate',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }
}

/// 能力缺失平台（web/ohos/desktop）的一致降级实现：结构化 no-op。
final class UnsupportedCallAudioSessionGateway
    implements CallAudioSessionGateway {
  const UnsupportedCallAudioSessionGateway();

  @override
  Future<bool> activateForCall() async => false;

  @override
  Future<void> deactivate() async {}

  @override
  Stream<CallAudioSessionEvent> get events => const Stream.empty();
}
