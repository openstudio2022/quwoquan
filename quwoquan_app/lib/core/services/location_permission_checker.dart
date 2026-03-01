import 'package:geolocator/geolocator.dart';

/// 定位权限检查结果：已授予 / 需批准 / 已永久拒绝
enum LocationPermissionResult {
  granted,
  needApproval,
  permanentlyDenied,
}

/// 定位权限检查接口，便于测试注入 FakeChecker。
abstract class LocationPermissionChecker {
  /// 检查并请求定位权限；若已授予则返回当前位置。
  Future<({
    LocationPermissionResult result,
    Position? position,
  })> ensureLocationPermission();

  /// 打开应用权限设置页面。
  Future<bool> openAppSettings();
}

/// 默认实现：调用 Geolocator。
class GeolocatorLocationPermissionChecker implements LocationPermissionChecker {
  const GeolocatorLocationPermissionChecker();

  @override
  Future<({
    LocationPermissionResult result,
    Position? position,
  })> ensureLocationPermission() async {
    final enabled = await Geolocator.isLocationServiceEnabled();
    if (!enabled) {
      return (result: LocationPermissionResult.needApproval, position: null);
    }
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.deniedForever) {
        return (
          result: perm == LocationPermission.deniedForever
              ? LocationPermissionResult.permanentlyDenied
              : LocationPermissionResult.needApproval,
          position: null,
        );
      }
    }
    if (perm == LocationPermission.deniedForever) {
      return (
        result: LocationPermissionResult.permanentlyDenied,
        position: null,
      );
    }
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
        ),
      );
      return (result: LocationPermissionResult.granted, position: pos);
    } catch (_) {
      return (result: LocationPermissionResult.granted, position: null);
    }
  }

  @override
  Future<bool> openAppSettings() => Geolocator.openAppSettings();
}
