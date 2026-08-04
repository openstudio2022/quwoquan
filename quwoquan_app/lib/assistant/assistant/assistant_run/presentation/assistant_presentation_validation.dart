// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — typed action payload 允许受限扩展键并递归拒绝危险键。
part of 'assistant_presentation_renderer.dart';

bool _validStyle(AssistantPresentationStyleWire style) =>
    const {'normal', 'subtle', 'strong'}.contains(style.emphasis) &&
    const {'standard', 'outlined', 'filled', 'hero'}.contains(style.variant) &&
    const {
      'start',
      'center',
      'end',
      'space_between',
    }.contains(style.alignment) &&
    const {
      'none',
      'related',
      'section',
      'screen',
    }.contains(style.spacingRole) &&
    style.aspectRatio >= 0 &&
    style.aspectRatio <= 10 &&
    style.responsiveSpan >= 1 &&
    style.responsiveSpan <= 12;

bool _validAction(AssistantActionIntentWire action) {
  if (action.intentId.isEmpty || action.operation.isEmpty) return false;
  return !_containsUnsafeActionKey(action.payload);
}

bool _containsUnsafeActionKey(Map<String, dynamic> payload) {
  for (final entry in payload.entries) {
    final key = entry.key.toLowerCase().replaceAll('_', '');
    if (const {
      'url',
      'route',
      'callback',
      'callbackurl',
      'javascript',
      'script',
      'authorization',
      'cookie',
    }.contains(key)) {
      return true;
    }
    final value = entry.value;
    if (value is Map &&
        _containsUnsafeActionKey(value.cast<String, dynamic>())) {
      return true;
    }
  }
  return false;
}

List<String> _stringList(Object? value) => value is List
    ? value
          .whereType<String>()
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .take(16)
          .toList(growable: false)
    : const [];

List<Map<String, dynamic>> _mapList(Object? value) => value is List
    ? value
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .take(64)
          .toList(growable: false)
    : const [];

IconData _iconData(String token) => switch (token) {
  'calendar' => CupertinoIcons.calendar,
  'clock' => CupertinoIcons.clock,
  'location' => CupertinoIcons.location,
  'weather' => CupertinoIcons.cloud_sun,
  'warning' => CupertinoIcons.exclamationmark_triangle,
  'check' => CupertinoIcons.check_mark_circled,
  'info' => CupertinoIcons.info_circle,
  'travel' => CupertinoIcons.airplane,
  'source' => CupertinoIcons.link,
  'image' => CupertinoIcons.photo,
  _ => CupertinoIcons.sparkles,
};

final RegExp _digestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
final RegExp _presentationIdentifierPattern = RegExp(
  r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$',
);
final RegExp _unsafePresentationValuePattern = RegExp(
  r'(?:javascript|data|file):',
  caseSensitive: false,
);

bool _validRouteMapData(Map<String, dynamic> data) {
  if (!_exactRouteMapKeys(
        data,
        const {'tripId', 'revisionId', 'sourceDigest', 'stops'},
        const {
          'tripId',
          'revisionId',
          'sourceDigest',
          'stops',
          'segments',
          'markers',
        },
      ) ||
      !_validRouteMapIdentifier(data['tripId']) ||
      !_validRouteMapIdentifier(data['revisionId']) ||
      !_digestPattern.hasMatch((data['sourceDigest'] as String?) ?? '')) {
    return false;
  }
  final stops = _routeMapObjects(data['stops']);
  if (stops.isEmpty || stops.length > 128) return false;
  final placeKeys = <String>{};
  final stopOrders = <String>{};
  for (final stop in stops) {
    if (!_exactRouteMapKeys(
          stop,
          const {'placeRef', 'dayIndex', 'order'},
          const {'placeRef', 'dayIndex', 'order', 'itemId', 'title'},
        ) ||
        !_validRouteMapPlaceRef(stop['placeRef']) ||
        !_validRouteMapInteger(stop['dayIndex'], 0, 366) ||
        !_validRouteMapInteger(stop['order'], 0, 127) ||
        !_validOptionalRouteMapIdentifier(stop['itemId']) ||
        !_validOptionalRouteMapText(stop['title'], 512)) {
      return false;
    }
    final placeKey = _routeMapPlaceKey(stop['placeRef']);
    final orderKey = '${stop['dayIndex']}:${stop['order']}';
    if (!placeKeys.add(placeKey) || !stopOrders.add(orderKey)) return false;
  }

  final segments = _routeMapObjects(data['segments']);
  if (segments.length > stops.length - 1 || segments.length > 127) return false;
  final segmentOrders = <int>{};
  for (final segment in segments) {
    if (!_exactRouteMapKeys(
          segment,
          const {'fromPlaceRef', 'toPlaceRef', 'modeToken', 'order'},
          const {'fromPlaceRef', 'toPlaceRef', 'modeToken', 'order'},
        ) ||
        !_validRouteMapPlaceRef(segment['fromPlaceRef']) ||
        !_validRouteMapPlaceRef(segment['toPlaceRef']) ||
        !_validRouteMapInteger(segment['order'], 0, 126)) {
      return false;
    }
    final from = _routeMapPlaceKey(segment['fromPlaceRef']);
    final to = _routeMapPlaceKey(segment['toPlaceRef']);
    final order = (segment['order'] as num).toInt();
    if (from == to ||
        !placeKeys.contains(from) ||
        !placeKeys.contains(to) ||
        !segmentOrders.add(order) ||
        !const {
          'walk',
          'bicycle',
          'transit',
          'drive',
          'rail',
          'flight',
          'ferry',
        }.contains(segment['modeToken'])) {
      return false;
    }
  }

  final markers = _routeMapObjects(data['markers']);
  if (markers.length > 128) return false;
  final markerIds = <String>{};
  for (final marker in markers) {
    if (!_exactRouteMapKeys(
          marker,
          const {'momentId', 'placeRef', 'dayIndex'},
          const {'momentId', 'placeRef', 'dayIndex', 'itemId'},
        ) ||
        !_validRouteMapIdentifier(marker['momentId']) ||
        !markerIds.add(marker['momentId'] as String) ||
        !_validRouteMapPlaceRef(marker['placeRef']) ||
        !_validRouteMapInteger(marker['dayIndex'], 0, 366) ||
        !_validOptionalRouteMapIdentifier(marker['itemId'])) {
      return false;
    }
  }
  return true;
}

List<Map<String, dynamic>> _routeMapObjects(Object? value) {
  if (value == null) return const [];
  if (value is! List) return const [];
  final result = <Map<String, dynamic>>[];
  for (final item in value) {
    if (item is! Map) return const [];
    result.add(item.cast<String, dynamic>());
  }
  return result;
}

bool _exactRouteMapKeys(
  Map<String, dynamic> value,
  Set<String> required,
  Set<String> allowed,
) => value.keys.every(allowed.contains) && required.every(value.containsKey);

bool _validRouteMapIdentifier(Object? value) =>
    value is String &&
    _presentationIdentifierPattern.hasMatch(value.trim()) &&
    !_unsafePresentationValuePattern.hasMatch(value);

bool _validOptionalRouteMapIdentifier(Object? value) =>
    value == null || value == '' || _validRouteMapIdentifier(value);

bool _validOptionalRouteMapText(Object? value, int maximum) =>
    value == null ||
    (value is String &&
        value.runes.length <= maximum &&
        !_unsafePresentationValuePattern.hasMatch(value) &&
        !RegExp(r'<[^>]+>').hasMatch(value));

bool _validRouteMapInteger(Object? value, int minimum, int maximum) =>
    value is num &&
    value.isFinite &&
    value == value.roundToDouble() &&
    value >= minimum &&
    value <= maximum;

bool _validRouteMapPlaceRef(Object? value) {
  if (value is! Map) return false;
  final ref = value.cast<String, dynamic>();
  return _exactRouteMapKeys(
        ref,
        const {'objectTypeRef', 'objectId'},
        const {'objectTypeRef', 'objectId'},
      ) &&
      _validRouteMapIdentifier(ref['objectTypeRef']) &&
      (ref['objectTypeRef'] as String).contains('.') &&
      _validRouteMapIdentifier(ref['objectId']);
}

String _routeMapPlaceKey(Object? value) {
  final ref = (value as Map).cast<String, dynamic>();
  return '${ref['objectTypeRef']}:${ref['objectId']}';
}
