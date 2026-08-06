import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

/// 在保留强类型列表的前提下，对单行做「Map 级」补丁（立即 decode 回 Row）。
AssistantTranscriptTimelineRow patchTranscriptRowWithMapMerge(
  AssistantTranscriptTimelineRow row,
  Map<String, dynamic> patch,
) {
  final base = PersistedTimelineTurnCodec.encode(row);
  final next = <String, dynamic>{...base, ...patch};
  return PersistedTimelineTurnCodec.decode(next);
}
