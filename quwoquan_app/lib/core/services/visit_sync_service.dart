// 云端同步预留：接口与数据契约与 [VisitRecord] 一致，不实现具体网络与鉴权。
// 见 assistant-baseline spec。

import 'package:quwoquan_app/core/models/visit_models.dart';

/// 浏览记录云端同步服务（抽象）。
/// 数据契约：与 [VisitRecord] 结构一致（targetKey、firstSeenAt、lastSeenAt、
/// visitCount、count7d、count30d、lastSeenTimestamps 等），便于序列化上传/拉取。
/// 本基线内不实现具体网络请求、鉴权与冲突策略。
abstract class VisitSyncService {
  /// 将本地增量或全量 [VisitRecord] 上传至云端。
  Future<void> uploadLocalVisits();

  /// 从云端拉取数据并与本地按 lastSeenAt 等策略合并。
  Future<void> pullAndMergeRemoteVisits();
}
