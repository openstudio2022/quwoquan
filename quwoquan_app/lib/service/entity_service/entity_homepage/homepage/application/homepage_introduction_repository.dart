import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class HomepageIntroductionRepository {
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  });
}
