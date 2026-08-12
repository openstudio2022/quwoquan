import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

/// App 搜索正式结果页的唯一云读端口。
///
/// 实现只能消费签名 persisted GraphQL client；这里不接收 query text，也不提供
/// REST 或旧 SearchResponseView fallback。
abstract interface class SearchPageQueryFacet {
  Future<SearchPageSlice> searchPage(
    SearchPageInput input, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
