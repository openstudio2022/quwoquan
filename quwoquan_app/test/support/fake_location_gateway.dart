import 'package:quwoquan_app/core/platform/location/location_gateway.dart';

final class FakeLocationGateway implements LocationGateway {
  FakeLocationGateway({
    this.permission = LocationPermissionResult.granted,
    this.position,
  });

  final LocationPermissionResult permission;
  final AppGeoPosition? position;

  @override
  Future<LocationAccessResult> ensureAccess() async {
    return LocationAccessResult(permission: permission, position: position);
  }
}
