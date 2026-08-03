import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前 Persona 自有 Trip 的稳定 keyset 分页读面。
abstract interface class TripPlanDirectory {
  Future<TripPlanListSlice> list({
    TripPlanStatus? status,
    String? cursor,
    int limit = 20,
  });
}
