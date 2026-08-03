import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';

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

  factory FootprintEntry.fromMap(Map<String, dynamic> map) {
    ContentPostViewData? post;
    final rawPost = map['post'];
    if (rawPost is Map) {
      post = contentPostViewDataFromReadModelMap(Map<String, dynamic>.from(rawPost));
    }
    return FootprintEntry(
      postId: (map['postId'] ?? '').toString(),
      action: (map['action'] ?? '').toString(),
      occurredAt: (map['occurredAt'] ?? '').toString(),
      post: post,
    );
  }
}

/// 我的足迹只读 Repository（WP1·T5）。
///
/// 足迹是自动形成的私有消费轨迹（viewed/liked/commented/shared），
/// 仅本人可见、只读、不产生交集与影响事实；没有写接口。
abstract class FootprintRepository {
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  });
}

// Test double 仅位于 test/support/cloud_services/content/；
// 四环境 production lib 只保留接口与 Remote adapter。
