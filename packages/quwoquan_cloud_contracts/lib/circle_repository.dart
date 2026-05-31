import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';

/// 首页圈子发现流单次拉取上限（与实现侧一致）。
const int kHomeCircleDiscoveryFeedDefaultLimit = 200;

/// 圈子读取 / 检索 / 发现 / 统计 / 分类配置。
///
/// R02：单接口 ≤10 方法。
abstract class CircleReadRepository {
  Future<List<CircleDto>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  });

  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<CircleDetailPayload> getCircle(String circleId);

  Future<CircleStatsWireDto> getCircleStats(String circleId);

  Future<List<CircleDto>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 首页圈子发现流（Mock 有数据；Remote：空列表）。
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  });

  /// 圈子分类 Tab 配置。
  Future<Map<String, CircleCategoryTabConfigDto>> getCircleCategoryConfig();

  /// 创作发布流推荐圈子。
  List<CircleDto> publishFlowRecommendedCircles();
}

/// 圈子创建 / 更新 / 归档 / 版面配置 / 行为上报。
///
/// R02：单接口 ≤10 方法。
abstract class CircleWriteRepository {
  Future<CircleDto> createCircle(CircleCreateWireDto data);

  Future<CircleDto> updateCircle(String circleId, CircleUpdateWireDto data);

  Future<void> archiveCircle(String circleId);

  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  );

  Future<void> reportBehavior(CircleBehaviorReportWireDto report);
}

/// 圈子成员加入 / 离开 / 角色 / 名册。
///
/// R02：单接口 ≤10 方法。
abstract class CircleMembershipRepository {
  Future<void> joinCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  });

  Future<void> leaveCircle(
    String circleId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  });

  Future<List<CircleMemberRosterItemDto>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> updateMemberRole(String circleId, String userId, String role);
}

/// 圈内分组与分组成员管理。
///
/// R02：单接口 ≤10 方法。
abstract class CircleGroupRepository {
  Future<List<CircleGroupDto>> listCircleGroups(
    String circleId, {
    String? groupType,
    String? visibility,
    String? parentGroupId,
    String? nodeType,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<CircleGroupDto>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<CircleGroupDto> getCircleGroup(String circleId, String groupId);

  Future<CircleGroupDto> createCircleGroup(
    String circleId,
    CircleGroupCreateWireDto data,
  );

  Future<CircleGroupDto> updateCircleGroup(
    String circleId,
    String groupId,
    CircleGroupUpdateWireDto data,
  );

  Future<void> applyJoinCircleGroup(String circleId, String groupId);

  Future<List<CircleGroupMemberDto>> listCircleGroupMembers(
    String circleId,
    String groupId, {
    String? status,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> approveCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  );

  Future<void> rejectCircleGroupMember(
    String circleId,
    String groupId,
    String userId,
  );
}

/// 圈子内容流 / 置顶 / 精选。
///
/// R02：单接口 ≤10 方法。
abstract class CircleFeedRepository {
  Future<List<PostBaseDto>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  });

  Future<void> pinPost(String circleId, String postId, {required bool pinned});

  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  });
}

/// 圈子文件管理。
///
/// R02：单接口 ≤10 方法。
abstract class CircleFileRepository {
  Future<List<CircleFileDto>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<CircleFileDto> createFile(
    String circleId,
    CircleFileCreateWireDto data,
  );

  Future<CircleFileDto> getFile(String circleId, String fileId);

  Future<CircleFileDto> updateFile(
    String circleId,
    String fileId,
    CircleFileUpdateWireDto data,
  );

  Future<void> deleteFile(String circleId, String fileId);
}

/// Circle 域 Repository（三层模式：Abstract + Mock + Remote）。
///
/// Mock：使用内嵌 canonical 数据，不发 HTTP。
/// Remote：对接云侧 REST 契约。
///
/// 由 6 个 ≤10 方法子接口组合（R02）。既有消费方继续依赖 `CircleRepository`
/// 不变；新消费方可只依赖所需子接口。
abstract class CircleRepository
    implements
        CircleReadRepository,
        CircleWriteRepository,
        CircleMembershipRepository,
        CircleGroupRepository,
        CircleFeedRepository,
        CircleFileRepository {}
