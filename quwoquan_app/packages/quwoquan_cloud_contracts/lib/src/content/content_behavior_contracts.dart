import 'content_operation_contracts.g.dart';

/// `content.content_behavior_fact`（`kind: append_only_fact`，
/// `access.commands: append_only_sink`）的端侧 append port。
///
/// 行为事实只追加、不更新：本接口刻意与聚合的 `*CommandWriter` 类型不同名，调用方
/// 无法把事实当可变对象写。离线补传由 adapter 侧的「待追加事实队列」承担，队列条目
/// 是不可变事实信封（一次写入、成功后删除、失败进 DLQ），不是可就地修改的状态。
abstract interface class ContentBehaviorFactAppender {
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command);
}
