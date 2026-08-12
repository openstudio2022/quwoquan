import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageStatusReportView;

/// HomepageStatusReport 对象的本人待审权威读面。
abstract interface class HomepageStatusReportQueryReader {
  Future<HomepageStatusReportView> getMyPendingStatusReport({
    required String homepageId,
    required String reason,
  });
}
