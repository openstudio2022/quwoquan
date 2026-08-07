import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// `search.search_feedback_fact`（`kind: append_only_fact`）的端侧 append port。
///
/// 事实只追加、不更新：本接口刻意与聚合的 `*CommandWriter` 类型不同名，调用方无法
/// 把事实当可变对象写。禁止在此声明 update/mutate/patch/delete 语义方法。
abstract interface class SearchFeedbackFactAppender {
  Future<SearchFeedbackAck> reportSearchFeedback(
    ReportSearchFeedbackCommand command,
  );
}
