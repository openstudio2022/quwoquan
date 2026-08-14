import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

/// `task_card` / `image` / `audio` 时间轴行的 typed 展示模型（S-UI）。
///
/// 从强类型时间轴行一次性解析扩展负载，presentation 只消费本类的 typed 字段。
class AssistantTranscriptBubbleEnvelope {
  const AssistantTranscriptBubbleEnvelope._({
    required this.taskItems,
    required this.imageUrl,
    required this.audioMediaUrl,
    required this.audioDurationMs,
    required this.audioWaveform,
    required this.audioMessageId,
    required this.audioMessageStatus,
    required this.audioIsRead,
  });

  final List<AssistantTranscriptTaskItem> taskItems;
  final String imageUrl;
  final String audioMediaUrl;
  final int audioDurationMs;
  final List<double> audioWaveform;
  final String audioMessageId;
  final String audioMessageStatus;
  final bool audioIsRead;

  factory AssistantTranscriptBubbleEnvelope.fromTimelineRow(
    AssistantTranscriptTimelineRow row,
  ) {
    final extra = switch (row) {
      UserTranscriptTimelineRow r => r.extra,
      AssistantAnswerTranscriptRow r => r.extra,
      ErrorTranscriptTimelineRow r => r.extra,
    };
    final isRead = switch (row) {
      UserTranscriptTimelineRow r => r.isRead,
      AssistantAnswerTranscriptRow r => r.isRead,
      ErrorTranscriptTimelineRow _ => true,
    };
    final media = extra['media'];
    return AssistantTranscriptBubbleEnvelope._(
      taskItems: _parseTaskItems(extra['tasks']),
      imageUrl: _resolveImageUrl(extra),
      audioMediaUrl: media is Map ? (media['url'] as String?) ?? '' : '',
      audioDurationMs: media is Map
          ? (media['durationMs'] as num?)?.toInt() ?? 0
          : 0,
      audioWaveform: media is Map
          ? _parseWaveform(media['waveform'])
          : const <double>[],
      audioMessageId: row.id.trim(),
      audioMessageStatus: (extra['messageStatus'] ?? 'sent').toString(),
      audioIsRead: isRead,
    );
  }

  static List<AssistantTranscriptTaskItem> _parseTaskItems(Object? tasks) {
    if (tasks is! List) return const <AssistantTranscriptTaskItem>[];
    return tasks
        .whereType<Map>()
        .map(
          (task) => AssistantTranscriptTaskItem._(
            title: (task['title'] as String?) ?? '',
            time: (task['time'] as String?) ?? '',
            status: (task['status'] as String?) ?? 'pending',
          ),
        )
        .toList(growable: false);
  }

  static String _resolveImageUrl(Object? extra) {
    if (extra is! Map) return '';
    final primary = (extra['imageUrl'] as String?)?.trim() ?? '';
    if (primary.isNotEmpty) {
      return primary;
    }
    return (extra['thumbnailUrl'] as String?)?.trim() ?? '';
  }

  static List<double> _parseWaveform(Object? waveform) {
    if (waveform is! List) return const <double>[];
    return waveform
        .map((value) => (value as num).toDouble())
        .toList(growable: false);
  }
}

/// 任务提醒卡片中的单个任务条目。
class AssistantTranscriptTaskItem {
  const AssistantTranscriptTaskItem._({
    required this.title,
    required this.time,
    required this.status,
  });

  final String title;
  final String time;
  final String status;

  bool get isCompleted => status == 'completed';
}
