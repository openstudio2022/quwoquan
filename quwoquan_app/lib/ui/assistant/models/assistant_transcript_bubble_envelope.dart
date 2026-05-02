/// Codec Map view for `task_card` / `image` / `audio` transcript rows (S-UI).
class AssistantTranscriptBubbleEnvelope {
  const AssistantTranscriptBubbleEnvelope._(this.raw);

  final Map<String, dynamic> raw;

  factory AssistantTranscriptBubbleEnvelope.fromCodecMap(
    Map<String, dynamic> encoded,
  ) {
    return AssistantTranscriptBubbleEnvelope._(
      Map<String, dynamic>.from(encoded),
    );
  }

  List<Map<String, dynamic>> get taskItems {
    final tasks = raw['tasks'];
    if (tasks is! List) return const <Map<String, dynamic>>[];
    return tasks
        .whereType<Map>()
        .map((t) => t.cast<String, dynamic>())
        .toList(growable: false);
  }

  String get imageUrl =>
      (raw['imageUrl'] as String?)?.trim() ??
      (raw['thumbnailUrl'] as String?)?.trim() ??
      '';

  Map<String, dynamic> get audioMedia =>
      raw['media'] is Map
          ? (raw['media'] as Map).cast<String, dynamic>()
          : <String, dynamic>{};

  String get audioMediaUrl =>
      (audioMedia['url'] as String?) ??
      (raw['mediaUrl'] as String?) ??
      '';

  int get audioDurationMs =>
      (audioMedia['durationMs'] as num?)?.toInt() ?? 0;

  List<double> get audioWaveform {
    final waveformRaw = audioMedia['waveform'];
    if (waveformRaw is! List) return const <double>[];
    return waveformRaw.map((e) => (e as num).toDouble()).toList(growable: false);
  }

  String get audioMessageId =>
      (raw['_id'] ?? raw['id'] ?? '').toString();

  String get audioMessageStatus =>
      (raw['messageStatus'] ?? raw['status'] ?? 'sent').toString();

  bool get audioIsRead => raw['isRead'] == true;
}
