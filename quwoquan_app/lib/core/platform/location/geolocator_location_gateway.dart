import 'package:geolocator/geolocator.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/platform/startup_deferred_plugins.dart';

final class GeolocatorLocationGateway implements LocationGateway {
  const GeolocatorLocationGateway();

  @override
  Future<LocationAccessResult> ensureAccess() async {
    await StartupDeferredPlugins.ensureLocationPlugins();
    final enabled = await Geolocator.isLocationServiceEnabled();
    if (!enabled) {
      return const LocationAccessResult(
        permission: LocationPermissionResult.needApproval,
      );
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.deniedForever) {
      return const LocationAccessResult(
        permission: LocationPermissionResult.permanentlyDenied,
      );
    }
    if (permission == LocationPermission.denied) {
      return const LocationAccessResult(
        permission: LocationPermissionResult.needApproval,
      );
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
        ),
      );
      return LocationAccessResult(
        permission: LocationPermissionResult.granted,
        position: AppGeoPosition(
          latitude: position.latitude,
          longitude: position.longitude,
        ),
      );
    } catch (_) {
      return const LocationAccessResult(
        permission: LocationPermissionResult.granted,
      );
    }
  }
}
