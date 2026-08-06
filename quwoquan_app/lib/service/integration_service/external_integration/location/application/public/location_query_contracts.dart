// Location 对象的跨对象公开查询端口。
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class NearbyLocationReader {
  Future<LocationPoiListSlice> getNearbyLocations(
    NearbyLocationQueryParams query,
  );
}

abstract interface class LocationSearchReader {
  Future<LocationPoiListSlice> searchLocations(LocationSearchQueryParams query);
}
