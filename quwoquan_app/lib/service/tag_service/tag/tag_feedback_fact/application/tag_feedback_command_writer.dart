import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TagFeedbackFact 的 App append port。
abstract interface class TagFeedbackCommandWriter {
  Future<TagFeedbackResultView> reportTagFeedback(
    ReportTagFeedbackCommand command,
  );
}
