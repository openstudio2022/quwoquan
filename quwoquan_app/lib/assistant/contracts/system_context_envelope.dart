enum ContextGranularity {
  hidden('hidden'),
  coarse('coarse'),
  precise('precise');

  const ContextGranularity(this.wireName);

  final String wireName;
}

ContextGranularity parseContextGranularity(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'precise':
      return ContextGranularity.precise;
    case 'coarse':
      return ContextGranularity.coarse;
    default:
      return ContextGranularity.hidden;
  }
}

enum LocationGranularity {
  none('none'),
  city('city'),
  region('region'),
  precise('precise');

  const LocationGranularity(this.wireName);

  final String wireName;
}

LocationGranularity parseLocationGranularity(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'city':
      return LocationGranularity.city;
    case 'region':
      return LocationGranularity.region;
    case 'precise':
      return LocationGranularity.precise;
    default:
      return LocationGranularity.none;
  }
}

class SystemTimeContext {
  const SystemTimeContext({
    this.referenceNowIso = '',
    this.timezone = '',
    this.locale = '',
    this.granularity = ContextGranularity.coarse,
  });

  final String referenceNowIso;
  final String timezone;
  final String locale;
  final ContextGranularity granularity;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'referenceNowIso': referenceNowIso,
        'timezone': timezone,
        'locale': locale,
        'granularity': granularity.wireName,
      };

  factory SystemTimeContext.fromJson(Map<String, dynamic> json) {
    return SystemTimeContext(
      referenceNowIso: (json['referenceNowIso'] as String?)?.trim() ?? '',
      timezone: (json['timezone'] as String?)?.trim() ?? '',
      locale: (json['locale'] as String?)?.trim() ?? '',
      granularity: parseContextGranularity(
        (json['granularity'] as String?)?.trim() ?? '',
      ),
    );
  }
}

class DeviceSummary {
  const DeviceSummary({
    this.os = '',
    this.model = '',
    this.appVersion = '',
    this.granularity = ContextGranularity.coarse,
  });

  final String os;
  final String model;
  final String appVersion;
  final ContextGranularity granularity;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'os': os,
        'model': model,
        'appVersion': appVersion,
        'granularity': granularity.wireName,
      };

  factory DeviceSummary.fromJson(Map<String, dynamic> json) {
    return DeviceSummary(
      os: (json['os'] as String?)?.trim() ?? '',
      model: (json['model'] as String?)?.trim() ?? '',
      appVersion: (json['appVersion'] as String?)?.trim() ?? '',
      granularity: parseContextGranularity(
        (json['granularity'] as String?)?.trim() ?? '',
      ),
    );
  }
}

class PermissionSummary {
  const PermissionSummary({
    this.locationGranted = false,
    this.contactsGranted = false,
    this.photosGranted = false,
    this.cameraGranted = false,
    this.notificationsGranted = false,
    this.granularity = ContextGranularity.coarse,
  });

  final bool locationGranted;
  final bool contactsGranted;
  final bool photosGranted;
  final bool cameraGranted;
  final bool notificationsGranted;
  final ContextGranularity granularity;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'locationGranted': locationGranted,
        'contactsGranted': contactsGranted,
        'photosGranted': photosGranted,
        'cameraGranted': cameraGranted,
        'notificationsGranted': notificationsGranted,
        'granularity': granularity.wireName,
      };

  factory PermissionSummary.fromJson(Map<String, dynamic> json) {
    return PermissionSummary(
      locationGranted: json['locationGranted'] == true,
      contactsGranted: json['contactsGranted'] == true,
      photosGranted: json['photosGranted'] == true,
      cameraGranted: json['cameraGranted'] == true,
      notificationsGranted: json['notificationsGranted'] == true,
      granularity: parseContextGranularity(
        (json['granularity'] as String?)?.trim() ?? '',
      ),
    );
  }
}

class SystemLocationContext {
  const SystemLocationContext({
    this.countryCode = '',
    this.countryName = '',
    this.adminAreaLevel1 = '',
    this.adminAreaLevel2 = '',
    this.adminAreaLevel3 = '',
    this.adminAreaLevel4 = '',
    this.formattedAddress = '',
    this.timezone = '',
    this.granularity = LocationGranularity.city,
  });

  final String countryCode;
  final String countryName;
  final String adminAreaLevel1;
  final String adminAreaLevel2;
  final String adminAreaLevel3;
  final String adminAreaLevel4;
  final String formattedAddress;
  final String timezone;
  final LocationGranularity granularity;

  bool get hasAdministrativeArea => adminAreaLevel1.trim().isNotEmpty;

  bool get hasLocality =>
      adminAreaLevel2.trim().isNotEmpty ||
      adminAreaLevel3.trim().isNotEmpty ||
      adminAreaLevel4.trim().isNotEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'countryCode': countryCode,
        'countryName': countryName,
        'adminAreaLevel1': adminAreaLevel1,
        'adminAreaLevel2': adminAreaLevel2,
        'adminAreaLevel3': adminAreaLevel3,
        'adminAreaLevel4': adminAreaLevel4,
        'formattedAddress': formattedAddress,
        'timezone': timezone,
        'granularity': granularity.wireName,
      };

  factory SystemLocationContext.fromJson(Map<String, dynamic> json) {
    return SystemLocationContext(
      countryCode: (json['countryCode'] as String?)?.trim().isNotEmpty == true
          ? (json['countryCode'] as String).trim()
          : (json['country'] as String?)?.trim() ?? '',
      countryName: (json['countryName'] as String?)?.trim() ?? '',
      adminAreaLevel1: (json['adminAreaLevel1'] as String?)?.trim().isNotEmpty ==
              true
          ? (json['adminAreaLevel1'] as String).trim()
          : (json['region'] as String?)?.trim() ?? '',
      adminAreaLevel2: (json['adminAreaLevel2'] as String?)?.trim().isNotEmpty ==
              true
          ? (json['adminAreaLevel2'] as String).trim()
          : (json['city'] as String?)?.trim() ?? '',
      adminAreaLevel3: (json['adminAreaLevel3'] as String?)?.trim() ?? '',
      adminAreaLevel4: (json['adminAreaLevel4'] as String?)?.trim() ?? '',
      formattedAddress: (json['formattedAddress'] as String?)?.trim() ?? '',
      timezone: (json['timezone'] as String?)?.trim() ?? '',
      granularity: parseLocationGranularity(
        (json['granularity'] as String?)?.trim() ?? '',
      ),
    );
  }
}

class SystemContextEnvelope {
  const SystemContextEnvelope({
    this.contractId = 'system_context_envelope',
    this.time = const SystemTimeContext(),
    this.device = const DeviceSummary(),
    this.permissions = const PermissionSummary(),
    this.location = const SystemLocationContext(),
  });

  final String contractId;
  final SystemTimeContext time;
  final DeviceSummary device;
  final PermissionSummary permissions;
  final SystemLocationContext location;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'contractId': contractId,
        'time': time.toJson(),
        'device': device.toJson(),
        'permissions': permissions.toJson(),
        'location': location.toJson(),
      };

  factory SystemContextEnvelope.fromJson(Map<String, dynamic> json) {
    return SystemContextEnvelope(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'system_context_envelope',
      time: json['time'] is Map
          ? SystemTimeContext.fromJson(
              (json['time'] as Map).cast<String, dynamic>(),
            )
          : const SystemTimeContext(),
      device: json['device'] is Map
          ? DeviceSummary.fromJson((json['device'] as Map).cast<String, dynamic>())
          : const DeviceSummary(),
      permissions: json['permissions'] is Map
          ? PermissionSummary.fromJson(
              (json['permissions'] as Map).cast<String, dynamic>(),
            )
          : const PermissionSummary(),
      location: json['location'] is Map
          ? SystemLocationContext.fromJson(
              (json['location'] as Map).cast<String, dynamic>(),
            )
          : const SystemLocationContext(),
    );
  }
}
