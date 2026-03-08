import 'dart:async';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Recording state machine: idle → recording → paused → stopped.
enum VoiceRecordState { idle, recording, paused, stopped }

/// Minimum valid recording duration in milliseconds.
const int kMinRecordDurationMs = 1000;

/// Maximum recording duration in milliseconds (configurable, default 120s).
const int kMaxRecordDurationMs = 120000;

/// Encapsulates AAC recording with waveform amplitude collection.
class VoiceRecorder {
  VoiceRecorder({int maxDurationMs = kMaxRecordDurationMs})
      : _maxDurationMs = maxDurationMs;

  final int _maxDurationMs;
  final AudioRecorder _recorder = AudioRecorder();

  VoiceRecordState _state = VoiceRecordState.idle;
  VoiceRecordState get state => _state;

  String? _filePath;
  String? get filePath => _filePath;

  DateTime? _startTime;
  int get elapsedMs =>
      _startTime == null ? 0 : DateTime.now().difference(_startTime!).inMilliseconds;

  final List<double> _amplitudes = [];
  List<double> get amplitudes => List.unmodifiable(_amplitudes);

  Timer? _amplitudeTimer;
  Timer? _maxDurationTimer;

  final _stateController = StreamController<VoiceRecordState>.broadcast();
  Stream<VoiceRecordState> get onStateChange => _stateController.stream;

  final _amplitudeController = StreamController<List<double>>.broadcast();
  Stream<List<double>> get onAmplitude => _amplitudeController.stream;

  /// Starts recording AAC audio at 16kHz, mono.
  Future<bool> start() async {
    if (_state == VoiceRecordState.recording) return false;

    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) return false;

    final dir = await getTemporaryDirectory();
    _filePath =
        '${dir.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';

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
      _cleanup();
      return null;
    }

    final file = File(path);
    final fileSize = await file.length();

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
    _cleanup();
  }

  Future<void> _collectAmplitude() async {
    try {
      final amplitude = await _recorder.getAmplitude();
      _amplitudes.add(amplitude.current);
      _amplitudeController.add(List.unmodifiable(_amplitudes));
    } catch (_) {}
  }

  void _cleanup() {
    if (_filePath != null) {
      try {
        File(_filePath!).deleteSync();
      } catch (_) {}
    }
    _filePath = null;
    _startTime = null;
    _amplitudes.clear();
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

/// Result of a successful voice recording.
class VoiceRecordResult {
  final String filePath;
  final int durationMs;
  final int fileSize;
  final List<double> waveform;

  const VoiceRecordResult({
    required this.filePath,
    required this.durationMs,
    required this.fileSize,
    required this.waveform,
  });
}
