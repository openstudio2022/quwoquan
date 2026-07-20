import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';

const int kHomeCircleDiscoveryFeedDefaultLimit = 200;

/// Circle 聚合的读投影仓库。
/// 生命周期/板块命令唯一入口是 pure contracts 的
/// `CircleLifecycleCommandWriter` / `CircleConfigurationCommandWriter`
/// （generated client 装配），仓库不再承载写方法。
abstract interface class CircleReadRepository {
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

  Future<CircleImpactSummary> getCircleImpact(String circleId);

  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  });
}

abstract interface class CircleFeedRepository {
  Future<List<PostBaseDto>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  });
}

abstract class CircleRepository
    implements CircleReadRepository, CircleFeedRepository {}
