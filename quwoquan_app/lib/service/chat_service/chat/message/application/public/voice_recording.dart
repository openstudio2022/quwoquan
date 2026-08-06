/// Immutable recording payload accepted by the Message voice-send boundary.
final class VoiceRecordResult {
  const VoiceRecordResult({
    required this.filePath,
    required this.durationMs,
    required this.fileSize,
    required this.waveform,
  });

  final String filePath;
  final int durationMs;
  final int fileSize;
  final List<double> waveform;
}
