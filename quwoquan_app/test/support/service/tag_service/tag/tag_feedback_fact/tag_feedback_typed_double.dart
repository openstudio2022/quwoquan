import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/application/tag_feedback_fact_appender.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TagFeedbackFact 对象级替身：进程内追加 + 同 key 幂等（与服务端唯一索引同构）。
final class TagFeedbackTypedDouble implements TagFeedbackFactAppender {
  final Map<String, ReportTagFeedbackCommand> _byKey =
      <String, ReportTagFeedbackCommand>{};

  List<ReportTagFeedbackCommand> get recorded =>
      _byKey.values.toList(growable: false);

  @override
  Future<TagFeedbackResultView> reportTagFeedback(
    ReportTagFeedbackCommand command,
  ) async {
    final key =
        '${command.tagRef}\u0000${command.action.wireName}\u0000${command.context ?? ''}';
    _byKey.putIfAbsent(key, () => command);
    return const TagFeedbackResultView(accepted: true);
  }
}
