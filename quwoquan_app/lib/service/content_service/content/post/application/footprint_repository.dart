import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentFootprintQuery;

/// 我的足迹条目（云侧只读契约 GET /content/footprint 的端侧映射）。
///
/// `action` 与 `type` 的语义映射由云侧唯一定义（footprintTypeActions），
/// 端侧只透传 type 枚举字符串并展示云端下发数据，不解析 action 语义。
class FootprintEntry {
  const FootprintEntry({
    required this.postId,
    required this.action,
    required this.occurredAt,
    this.post,
  });

  final String postId;
  final String action;
  final String occurredAt;
  final ContentPostViewData? post;
}

/// 我的足迹只读 Repository（WP1·T5）。
///
/// 足迹是自动形成的私有消费轨迹（viewed/liked/commented/shared），
/// 仅本人可见、只读、不产生交集与影响事实；没有写接口。
abstract class FootprintRepository {
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = ContentFootprintQuery.defaultLimit,
  });
}

// Test double 仅位于 test/support/cloud_services/content/；
// 四环境 production lib 只保留接口与 Remote adapter。
