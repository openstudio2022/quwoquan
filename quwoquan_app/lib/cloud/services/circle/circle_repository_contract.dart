import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';

const int kHomeCircleDiscoveryFeedDefaultLimit = 200;

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

  Future<Map<String, CircleCategoryTabConfigDto>> getCircleCategoryConfig();

  List<CircleDto> publishFlowRecommendedCircles();
}

abstract interface class CircleWriteRepository {
  Future<CircleDto> createCircle(CircleCreateWireDto data);

  Future<CircleDto> updateCircle(String circleId, CircleUpdateWireDto data);

  Future<void> archiveCircle(String circleId);

  Future<void> updateSections(
    String circleId,
    List<CircleSectionConfigDto> sections,
  );
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
    implements
        CircleReadRepository,
        CircleWriteRepository,
        CircleFeedRepository {}
