import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageClaimRequestView;

/// HomepageClaimRequest 对象的本人待审权威读面。
abstract interface class HomepageClaimRequestQueryReader {
  Future<HomepageClaimRequestView> getMyPendingClaimRequest({
    required String homepageId,
  });
}
