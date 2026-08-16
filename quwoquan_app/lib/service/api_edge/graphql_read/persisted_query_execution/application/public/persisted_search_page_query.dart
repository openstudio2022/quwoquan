import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

/// API Edge persisted SearchPage 的对象级 App public query seam。
///
/// Search owner 只消费这个 typed port；签名 hash、GraphQL envelope 与 transport
/// generated client 均由 gateway.persisted_query_execution 的 adapter 持有。
abstract interface class PersistedSearchPageQuery {
  Future<SearchPageSlice> searchPage(
    SearchPageInput input, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
