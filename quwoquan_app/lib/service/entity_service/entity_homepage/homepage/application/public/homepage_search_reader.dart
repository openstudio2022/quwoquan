import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Homepage owner 的 canonical search operation port。
abstract interface class HomepageSearchReader {
  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
