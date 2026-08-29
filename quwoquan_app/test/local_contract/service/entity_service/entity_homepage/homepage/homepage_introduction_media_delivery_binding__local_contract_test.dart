// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// DEC-033 四路投影媒体交付绑定薄改（entity homepage introduction 路）：
// App 直接消费契约 `HomepageIntroduction`，`homepageIntroductionFromContract`
// 必须恒等保留 coverAssetId/coverAccessMode 与逐资产 assetId/accessMode，
// 缺席时为 null，不以 homepageId 冒充。本测试锁定该透传不被回退为
// 丢字段的中间 DTO。

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_contract_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

HomepageIntroduction _introduction({
  String? coverAssetId,
  MediaDeliveryAccessMode? coverAccessMode,
  MediaDeliveryAccessMode? assetAccessMode,
}) {
  return HomepageIntroduction(
    homepageId: 'homepage-1',
    displayName: '对象主页',
    homepageType: 'scenic_spot',
    coverUrl: 'media/image/s/fixture/homepage-1/v1/cover.jpg',
    coverAssetId: coverAssetId,
    coverAccessMode: coverAccessMode,
    summary: '简介',
    sections: <HomepageIntroductionSection>[
      HomepageIntroductionSection(
        kind: 'gallery',
        title: '图集',
        assets: <HomepageIntroductionAsset>[
          HomepageIntroductionAsset(
            assetId: 'asset-intro-1',
            url: 'media/image/s/fixture/homepage-1/v1/intro.jpg',
            accessMode: assetAccessMode,
            role: 'gallery',
          ),
        ],
        timelineItems: const <HomepageIntroductionTimelineItem>[],
      ),
    ],
    relatedObjects: const <HomepageRelatedGroupSummary>[],
    sourceUrls: const <String>[],
    updatedAt: '2026-08-01T00:00:00Z',
  );
}

void main() {
  group('homepageIntroductionFromContract — 介绍页交付绑定保留', () {
    test('signed_grant 绑定在场时 cover 与逐资产绑定完整透传', () {
      final introduction = homepageIntroductionFromContract(
        _introduction(
          coverAssetId: 'asset-cover-1',
          coverAccessMode: MediaDeliveryAccessMode.signedGrant,
          assetAccessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      );

      expect(introduction.coverAssetId, 'asset-cover-1');
      expect(
        introduction.coverAccessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
      final asset = introduction.sections.single.assets.single;
      expect(asset.assetId, 'asset-intro-1');
      expect(asset.accessMode, MediaDeliveryAccessMode.signedGrant);
      // 不以 homepageId 冒充媒体资产标识。
      expect(introduction.coverAssetId, isNot(introduction.homepageId));
    });

    test('存量 public 投影未携带绑定字段时缺席为 null', () {
      final introduction = homepageIntroductionFromContract(_introduction());

      expect(introduction.coverAssetId, isNull);
      expect(introduction.coverAccessMode, isNull);
      expect(introduction.sections.single.assets.single.accessMode, isNull);
      // 逐资产 assetId 是契约必填字段，始终在场。
      expect(
        introduction.sections.single.assets.single.assetId,
        'asset-intro-1',
      );
    });
  });
}
