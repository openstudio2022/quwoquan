import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/entity_contracts.dart'
    as wire;

void main() {
  test('Homepage ViewData only enters from canonical Entity projections', () {
    final summary = HomepageSummary.fromWire(
      const wire.HomepageSearchItemView(
        homepageId: 'homepage-sight-west-lake',
        canonicalEntityId: 'entity-sight-west-lake',
        title: '西湖',
        subtitle: '杭州西湖',
        homepageType: wire.HomepageType.sight,
        status: wire.HomepageStatus.published,
        city: '杭州',
        ratingCount: 12,
      ),
    );
    expect(summary.id, 'homepage-sight-west-lake');
    expect(summary.homepageType, 'sight');
    expect(summary.status, 'published');
    expect(summary.canonicalEntityId, 'entity-sight-west-lake');

    final now = DateTime.utc(2026, 8, 4);
    final detailWire = wire.HomepageDetailView(
      homepageId: summary.id,
      title: summary.title,
      homepageType: summary.homepageType,
      status: summary.status!,
      claimStatus: 'unclaimed',
      categoryTags: const <String>['Entity/地点/景区'],
      viewerFollow: const wire.HomepageViewerFollowSlice(
        viewerFollowsHomepage: true,
        followerCount: 8,
      ),
      verified: true,
      ratingCount: 12,
      reviewSummary: const wire.HomepageReviewSummaryView(
        averageRating: 4.8,
        ratingCount: 12,
        highlightTags: <String>['日落'],
      ),
      contentPreview: const <wire.HomepageContentPreview>[],
      questionPreview: const <wire.HomepageQuestionPreview>[],
      relatedGroups: const <wire.HomepageRelatedGroupSummary>[],
      relationEdges: const <wire.ObjectRelationEdge>[],
      introductionAssets: const <wire.HomepageIntroductionAsset>[],
      sourceUrls: const <String>[],
      createdAt: now,
      updatedAt: now,
    );
    final detail = HomepageDetail.fromWire(detailWire);
    expect(detail.viewerFollowsHomepage, isTrue);
    expect(detail.followerCount, 8);
    expect(detail.reviewSummary?.highlightTags, <String>['日落']);

    final shell = HomepageShellData.fromWire(
      wire.HomepageShellView(homepage: detailWire),
    );
    expect(shell.homepage.id, detail.id);
    expect(shell.contentPreview, isEmpty);
  });
}
