import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_feed_object_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 统一列表里的实体主页项测试构造器。
///
/// 只复用 canonical [HomepageSearchItemView]，不在测试里复制第二份对象事实。
ContentFeedObjectCard buildContentFeedObjectCard({
  String homepageId = 'homepage_sight_west_lake',
  String canonicalEntityId = 'entity_sight_west_lake',
  String title = '西湖',
  String? subtitle = '杭州 · 风景名胜',
  HomepageType homepageType = HomepageType.sight,
  HomepageStatus status = HomepageStatus.published,
  String? coverUrl,
  String? city,
  int ratingCount = 0,
  ContentUiSurface openSurface = ContentUiSurface.homepageDetail,
  required int anchorIndex,
}) => ContentFeedObjectCard(
  homepage: HomepageSearchItemView(
    homepageId: homepageId,
    canonicalEntityId: canonicalEntityId,
    title: title,
    subtitle: subtitle,
    homepageType: homepageType,
    coverUrl: coverUrl,
    city: city,
    status: status,
    ratingCount: ratingCount,
  ),
  openSurface: openSurface,
  anchorIndex: anchorIndex,
);
