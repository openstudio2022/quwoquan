enum LocationPermissionResult { granted, needApproval, permanentlyDenied }

final class AppGeoPosition {
  const AppGeoPosition({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

final class LocationAccessResult {
  const LocationAccessResult({required this.permission, this.position});

  final LocationPermissionResult permission;
  final AppGeoPosition? position;
}

abstract interface class LocationGateway {
  Future<LocationAccessResult> ensureAccess();
}
