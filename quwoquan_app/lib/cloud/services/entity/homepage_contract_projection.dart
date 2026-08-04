import 'package:quwoquan_app/application/entity/homepage_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_entity_contracts.dart'
    as wire;

HomepageSummary homepageSummaryFromContract(
  wire.HomepageSearchItemView source,
) => HomepageSummary.fromWire(source);

HomepageDetail homepageDetailFromContract(wire.HomepageDetailView source) =>
    HomepageDetail.fromWire(source);

HomepageShellData homepageShellFromContract(wire.HomepageShellView source) =>
    HomepageShellData.fromWire(source);

HomepageIntroduction homepageIntroductionFromContract(
  wire.HomepageIntroduction source,
) => source;

ObjectPageBundle objectPageBundleFromContract(wire.ObjectPageBundle source) =>
    source;

HomepageReviewSummaryData homepageReviewSummaryFromContract(
  wire.HomepageReviewSummaryView source,
) {
  return _reviewSummaryViewFromWire(source);
}

List<HomepageRelatedGroupSummary> homepageRelatedGroupsFromContract(
  wire.HomepageRelatedGroupSummaryView source,
) {
  return source.groups ?? const <wire.HomepageRelatedGroupSummary>[];
}

EntityImpactSummary homepageImpactFromContract(
  wire.EntityImpactSummary source,
) => source;

HomepageReviewSummaryData _reviewSummaryViewFromWire(
  wire.HomepageReviewSummaryView source,
) {
  return HomepageReviewSummaryData(
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
    highlightTags: source.highlightTags ?? const <String>[],
  );
}
