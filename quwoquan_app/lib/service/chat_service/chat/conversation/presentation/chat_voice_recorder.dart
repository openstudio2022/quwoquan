import 'dart:async';

import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_recording.dart';
import 'package:record/record.dart';

/// Recording state machine: idle → recording → paused → stopped.
enum VoiceRecordState { idle, recording, paused, stopped }

/// Minimum valid recording duration in milliseconds.
const int kMinRecordDurationMs = 1000;

/// Maximum recording duration in milliseconds (configurable, default 120s).
const int kMaxRecordDurationMs = 120000;

/// Encapsulates AAC recording with waveform amplitude collection.
class VoiceRecorder {
  VoiceRecorder({
    int maxDurationMs = kMaxRecordDurationMs,
    FileStorageGateway? fileStorageGateway,
  }) : this._(maxDurationMs, fileStorageGateway ?? createFileStorageGateway());

  VoiceRecorder._(this._maxDurationMs, this._fileStorageGateway);

  final int _maxDurationMs;
  final FileStorageGateway _fileStorageGateway;
  final AudioRecorder _recorder = AudioRecorder();

  VoiceRecordState _state = VoiceRecordState.idle;
  VoiceRecordState get state => _state;

  String? _filePath;
  String? get filePath => _filePath;

  DateTime? _startTime;
  int get elapsedMs => _startTime == null
      ? 0
      : DateTime.now().difference(_startTime!).inMilliseconds;

  final List<double> _amplitudes = [];
  List<double> get amplitudes => List.unmodifiable(_amplitudes);

  Timer? _amplitudeTimer;
  Timer? _maxDurationTimer;
  bool _amplitudeFailureReported = false;
  bool _cleanupFailureReported = false;

  final _stateController = StreamController<VoiceRecordState>.broadcast();
  Stream<VoiceRecordState> get onStateChange => _stateController.stream;

  final _amplitudeController = StreamController<List<double>>.broadcast();
  Stream<List<double>> get onAmplitude => _amplitudeController.stream;

  /// Starts recording AAC audio at 16kHz, mono.
  Future<bool> start() async {
    if (_state == VoiceRecordState.recording) return false;

    final hasPermission = await _recorder.hasPermission(request: false);
    if (!hasPermission) return false;

    final temporaryPath = await _fileStorageGateway.temporaryPath();
    _filePath =
        '$temporaryPath/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 64000,
      ),
      path: _filePath!,
    );

    _state = VoiceRecordState.recording;
    _startTime = DateTime.now();
    _amplitudes.clear();
    _amplitudeFailureReported = false;
    _cleanupFailureReported = false;
    _stateController.add(_state);

    _amplitudeTimer = Timer.periodic(
      const Duration(milliseconds: 100),
      (_) => _collectAmplitude(),
    );

    _maxDurationTimer = Timer(
      Duration(milliseconds: _maxDurationMs),
      () => stop(),
    );

    return true;
  }

  /// Stops recording and returns the result, or null if too short.
  Future<VoiceRecordResult?> stop() async {
    if (_state != VoiceRecordState.recording) return null;

    _amplitudeTimer?.cancel();
    _maxDurationTimer?.cancel();

    final path = await _recorder.stop();
    final duration = elapsedMs;

    _state = VoiceRecordState.stopped;
    _stateController.add(_state);

    if (duration < kMinRecordDurationMs || path == null) {
      await _cleanup();
      return null;
    }

    final fileSize = (await readLocalFileStat(path)).length;

    return VoiceRecordResult(
      filePath: path,
      durationMs: duration,
      fileSize: fileSize,
      waveform: _normalizeWaveform(_amplitudes),
    );
  }

  /// Cancels and deletes the recording.
  Future<void> cancel() async {
    _amplitudeTimer?.cancel();
    _maxDurationTimer?.cancel();

    if (_state == VoiceRecordState.recording) {
      await _recorder.stop();
    }

    _state = VoiceRecordState.idle;
    _stateController.add(_state);
    await _cleanup();
  }

  Future<void> _collectAmplitude() async {
    try {
      final amplitude = await _recorder.getAmplitude();
      _amplitudes.add(amplitude.current);
      _amplitudeController.add(List.unmodifiable(_amplitudes));
    } catch (error, stackTrace) {
      // 单帧采样失败不影响录音；一轮录音只上报一次，避免 100ms 定时器放大故障。
      if (!_amplitudeFailureReported) {
        _amplitudeFailureReported = true;
        unawaited(
          AppExceptionTelemetryService.instance.recordHandledException(
            source: 'chat.voice_recorder.collect_amplitude',
            error: error,
            stackTrace: stackTrace,
          ),
        );
      }
    }
  }

  Future<void> _cleanup() async {
    final path = _filePath;
    if (path != null) {
      try {
        await _fileStorageGateway.delete(path);
      } catch (error, stackTrace) {
        // 删除失败由系统临时目录最终回收；当前录音生命周期只上报一次。
        if (!_cleanupFailureReported) {
          _cleanupFailureReported = true;
          unawaited(
            AppExceptionTelemetryService.instance.recordHandledException(
              source: 'chat.voice_recorder.cleanup_temp_file',
              error: error,
              stackTrace: stackTrace,
            ),
          );
        }
      }
    }
    _filePath = null;
    _startTime = null;
    _amplitudes.clear();
    _amplitudeFailureReported = false;
  }

  /// Normalizes raw dBFS amplitudes to 0.0–1.0 range.
  static List<double> _normalizeWaveform(List<double> rawAmplitudes) {
    if (rawAmplitudes.isEmpty) return [];
    const minDb = -60.0;
    return rawAmplitudes.map((db) {
      if (db <= minDb) return 0.0;
      if (db >= 0) return 1.0;
      return (db - minDb) / (0 - minDb);
    }).toList();
  }

  Future<void> dispose() async {
    _amplitudeTimer?.cancel();
    _maxDurationTimer?.cancel();
    await _stateController.close();
    await _amplitudeController.close();
    _recorder.dispose();
  }
}
