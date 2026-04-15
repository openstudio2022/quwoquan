import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

const String localContextToolVersion = 'local_context_v1';

enum LocalContextRequestedField {
  location,
  permissions,
  device,
  time,
  unknown;

  String get wireName {
    switch (this) {
      case LocalContextRequestedField.location:
        return 'location';
      case LocalContextRequestedField.permissions:
        return 'permissions';
      case LocalContextRequestedField.device:
        return 'device';
      case LocalContextRequestedField.time:
        return 'time';
      case LocalContextRequestedField.unknown:
        return '';
    }
  }
}

LocalContextRequestedField parseLocalContextRequestedField(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'location':
      return LocalContextRequestedField.location;
    case 'permissions':
      return LocalContextRequestedField.permissions;
    case 'device':
      return LocalContextRequestedField.device;
    case 'time':
      return LocalContextRequestedField.time;
    default:
      return LocalContextRequestedField.unknown;
  }
}

class LocalContextToolArgumentsContract {
  const LocalContextToolArgumentsContract({
    this.requestedFields = const <LocalContextRequestedField>[],
    this.needPreciseLocation,
    this.maxAgeSeconds,
  });

  final List<LocalContextRequestedField> requestedFields;
  final bool? needPreciseLocation;
  final int? maxAgeSeconds;

  factory LocalContextToolArgumentsContract.fromAssistantArguments(
    AssistantToolArguments arguments,
  ) {
    final requestedFields = arguments
        .stringListField('requestedFields')
        .map(parseLocalContextRequestedField)
        .where((item) => item != LocalContextRequestedField.unknown)
        .toSet()
        .toList(growable: false);
    return LocalContextToolArgumentsContract(
      requestedFields: requestedFields,
      needPreciseLocation: arguments.boolField('needPreciseLocation'),
      maxAgeSeconds: arguments.intField('maxAgeSeconds'),
    );
  }

  AssistantToolArguments toAssistantArguments() {
    return AssistantToolArguments(<String, Object?>{
      if (requestedFields.isNotEmpty)
        'requestedFields': requestedFields
            .map((item) => item.wireName)
            .where((item) => item.isNotEmpty)
            .toList(growable: false),
      if (needPreciseLocation != null)
        'needPreciseLocation': needPreciseLocation,
      if (maxAgeSeconds != null) 'maxAgeSeconds': maxAgeSeconds,
    });
  }
}

class LocalContextLocationSnapshot {
  const LocalContextLocationSnapshot({
    this.city = '',
    this.latitude,
    this.longitude,
    this.accuracyM,
    this.source = '',
  });

  final String city;
  final double? latitude;
  final double? longitude;
  final double? accuracyM;
  final String source;
}

class LocalContextPermissionSnapshot {
  const LocalContextPermissionSnapshot({
    this.location,
    this.photos,
    this.camera,
    this.notification,
  });

  final bool? location;
  final bool? photos;
  final bool? camera;
  final bool? notification;
}

class LocalContextDeviceSnapshot {
  const LocalContextDeviceSnapshot({
    this.os = '',
    this.model = '',
    this.locale = '',
    this.timezone = '',
  });

  final String os;
  final String model;
  final String locale;
  final String timezone;
}

class LocalContextMediaBoundary {
  const LocalContextMediaBoundary({this.included = false});

  final bool included;
}

class LocalContextToolSuccessData {
  const LocalContextToolSuccessData({
    this.contextVersion = localContextToolVersion,
    this.city = '',
    this.location = const LocalContextLocationSnapshot(),
    this.permissions = const LocalContextPermissionSnapshot(),
    this.device = const LocalContextDeviceSnapshot(),
    this.media = const LocalContextMediaBoundary(),
  });

  final String contextVersion;
  final String city;
  final LocalContextLocationSnapshot location;
  final LocalContextPermissionSnapshot permissions;
  final LocalContextDeviceSnapshot device;
  final LocalContextMediaBoundary media;

  AssistantToolResultData toResultData() {
    return AssistantToolResultData(<String, Object?>{
      'contextVersion': contextVersion,
      'city': city,
      'location': _locationPayload(location),
      'permissions': _permissionPayload(permissions),
      'device': _devicePayload(device),
      'media': _mediaPayload(media),
    });
  }
}

class LocalContextToolFailureData {
  const LocalContextToolFailureData({
    required this.userMessage,
    this.internalError = '',
  });

  final String userMessage;
  final String internalError;

  AssistantToolResultData toResultData() {
    return AssistantToolResultData(<String, Object?>{
      'userMessage': userMessage,
      if (internalError.trim().isNotEmpty) 'internalError': internalError.trim(),
    });
  }
}

Map<String, Object?> _locationPayload(LocalContextLocationSnapshot value) {
  return <String, Object?>{
    'city': value.city,
    'latitude': value.latitude,
    'longitude': value.longitude,
    'accuracyM': value.accuracyM,
    'source': value.source,
  };
}

Map<String, Object?> _permissionPayload(LocalContextPermissionSnapshot value) {
  return <String, Object?>{
    'location': value.location,
    'photos': value.photos,
    'camera': value.camera,
    'notification': value.notification,
  };
}

Map<String, Object?> _devicePayload(LocalContextDeviceSnapshot value) {
  return <String, Object?>{
    'os': value.os,
    'model': value.model,
    'locale': value.locale,
    'timezone': value.timezone,
  };
}

Map<String, Object?> _mediaPayload(LocalContextMediaBoundary value) {
  return <String, Object?>{'included': value.included};
}
