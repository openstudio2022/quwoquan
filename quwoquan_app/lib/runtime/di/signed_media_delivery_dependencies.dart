import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ContentMediaFacet 到 OriginalAccessQuotaGateway 的显式 port 委派。
///
/// App 内没有独立的 OriginalAccessQuotaGateway provider；production 实现由
/// surface 级 ContentMediaFacet 承载（其本身实现 ContentMediaOriginalAccessWriter），
/// 本类只做零逻辑委派，不产生第二套 grant 客户端。
final class _ContentMediaFacetOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  const _ContentMediaFacetOriginalAccessGateway(this._facet);

  final ContentMediaFacet _facet;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => _facet.requestOriginalAccess(command);
}

/// App 全局唯一的私有媒体 signed grant 协调器（DEC-033）。
///
/// 单实例承载全部 surface 的 grant 缓存与单飞——协调器缓存按资产身份共享，
/// 不随 surface 拆分，否则同资产会在不同页面重复兑换。invocation context
/// 沿用 workBrowser facet：私有媒体消费（作品浏览、沉浸页、查看原图）
/// 均发生在作品浏览域内。
final signedMediaDeliveryCoordinatorProvider =
    Provider<SignedMediaDeliveryCoordinator>((ref) {
      final coordinator = SignedMediaDeliveryCoordinator(
        gateway: _ContentMediaFacetOriginalAccessGateway(
          ref.watch(workBrowserContentMediaFacetProvider),
        ),
      );
      ref.onDispose(coordinator.clearAll);
      return coordinator;
    });
