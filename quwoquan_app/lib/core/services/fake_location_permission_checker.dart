import 'package:geolocator/geolocator.dart';
import 'package:quwoquan_app/core/services/location_permission_checker.dart';

/// 用于 L1b 测试的 Fake 实现，可配置返回结果。
class FakeLocationPermissionChecker implements LocationPermissionChecker {
  FakeLocationPermissionChecker({
    this.result = LocationPermissionResult.granted,
    this.position,
  });

  final LocationPermissionResult result;
  final Position? position;

  @override
  Future<({
    LocationPermissionResult result,
    Position? position,
  })> ensureLocationPermission() async =>
      (result: result, position: position);

  @override
  Future<bool> openAppSettings() async => true;
}
