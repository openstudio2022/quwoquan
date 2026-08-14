// ASSISTANT_WEAK_TYPE: JSON_BOUNDARY — presentation node `data` 开放 JSON 在此
// 一次性校验并投影为 typed 模型；presentation 层只消费本文件的强类型结果。

final RegExp _digestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
final RegExp _identifierPattern = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$');
final RegExp _unsafeValuePattern = RegExp(
  r'(?:javascript|data|file):',
  caseSensitive: false,
);

const Set<String> _routeMapModeTokens = {
  'walk',
  'bicycle',
  'transit',
  'drive',
  'rail',
  'flight',
  'ferry',
};

/// route_map 节点 `data` 的 canonical typed 投影。
///
/// [tryParse] 承载与渲染同源的全部结构校验（exact keys、identifier、digest、
/// 去重与数量上限），任何违例返回 null，由调用方走确定性 fallback。
class AssistantRouteMapData {
  const AssistantRouteMapData._({
    required this.tripId,
    required this.revisionId,
    required this.sourceDigest,
    required this.stops,
    required this.segments,
    required this.markers,
  });

  final String tripId;
  final String revisionId;
  final String sourceDigest;
  final List<AssistantRouteMapStop> stops;
  final List<AssistantRouteMapSegment> segments;
  final List<AssistantRouteMapMarker> markers;

  static AssistantRouteMapData? tryParse(Map<String, dynamic> data) {
    if (!_exactKeys(
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
        !_validIdentifier(data['tripId']) ||
        !_validIdentifier(data['revisionId']) ||
        !_digestPattern.hasMatch((data['sourceDigest'] as String?) ?? '')) {
      return null;
    }

    final stopObjects = _objectList(data['stops']);
    if (stopObjects.isEmpty || stopObjects.length > 128) return null;
    final placeKeys = <String>{};
    final stopOrders = <String>{};
    final stops = <AssistantRouteMapStop>[];
    for (final stop in stopObjects) {
      if (!_exactKeys(
            stop,
            const {'placeRef', 'dayIndex', 'order'},
            const {'placeRef', 'dayIndex', 'order', 'itemId', 'title'},
          ) ||
          !_validInteger(stop['dayIndex'], 0, 366) ||
          !_validInteger(stop['order'], 0, 127) ||
          !_validOptionalIdentifier(stop['itemId']) ||
          !_validOptionalText(stop['title'], 512)) {
        return null;
      }
      final placeRef = AssistantRouteMapPlaceRef._tryParse(stop['placeRef']);
      if (placeRef == null) return null;
      final dayIndex = (stop['dayIndex'] as num).toInt();
      final order = (stop['order'] as num).toInt();
      if (!placeKeys.add(placeRef.placeKey) ||
          !stopOrders.add('$dayIndex:$order')) {
        return null;
      }
      stops.add(
        AssistantRouteMapStop._(
          placeRef: placeRef,
          dayIndex: dayIndex,
          order: order,
          itemId: (stop['itemId'] as String?) ?? '',
          title: (stop['title'] as String?)?.trim() ?? '',
        ),
      );
    }

    final segmentObjects = _objectList(data['segments']);
    if (segmentObjects.length > stops.length - 1 ||
        segmentObjects.length > 127) {
      return null;
    }
    final segmentOrders = <int>{};
    final segments = <AssistantRouteMapSegment>[];
    for (final segment in segmentObjects) {
      if (!_exactKeys(
            segment,
            const {'fromPlaceRef', 'toPlaceRef', 'modeToken', 'order'},
            const {'fromPlaceRef', 'toPlaceRef', 'modeToken', 'order'},
          ) ||
          !_validInteger(segment['order'], 0, 126)) {
        return null;
      }
      final from = AssistantRouteMapPlaceRef._tryParse(segment['fromPlaceRef']);
      final to = AssistantRouteMapPlaceRef._tryParse(segment['toPlaceRef']);
      if (from == null || to == null) return null;
      final order = (segment['order'] as num).toInt();
      if (from.placeKey == to.placeKey ||
          !placeKeys.contains(from.placeKey) ||
          !placeKeys.contains(to.placeKey) ||
          !segmentOrders.add(order) ||
          !_routeMapModeTokens.contains(segment['modeToken'])) {
        return null;
      }
      segments.add(
        AssistantRouteMapSegment._(
          fromPlaceRef: from,
          toPlaceRef: to,
          modeToken: segment['modeToken'] as String,
          order: order,
        ),
      );
    }

    final markerObjects = _objectList(data['markers']);
    if (markerObjects.length > 128) return null;
    final markerIds = <String>{};
    final markers = <AssistantRouteMapMarker>[];
    for (final marker in markerObjects) {
      if (!_exactKeys(
            marker,
            const {'momentId', 'placeRef', 'dayIndex'},
            const {'momentId', 'placeRef', 'dayIndex', 'itemId'},
          ) ||
          !_validIdentifier(marker['momentId']) ||
          !markerIds.add(marker['momentId'] as String) ||
          !_validInteger(marker['dayIndex'], 0, 366) ||
          !_validOptionalIdentifier(marker['itemId'])) {
        return null;
      }
      final placeRef = AssistantRouteMapPlaceRef._tryParse(marker['placeRef']);
      if (placeRef == null) return null;
      markers.add(
        AssistantRouteMapMarker._(
          momentId: marker['momentId'] as String,
          placeRef: placeRef,
          dayIndex: (marker['dayIndex'] as num).toInt(),
          itemId: (marker['itemId'] as String?) ?? '',
        ),
      );
    }

    return AssistantRouteMapData._(
      tripId: data['tripId'] as String,
      revisionId: data['revisionId'] as String,
      sourceDigest: data['sourceDigest'] as String,
      stops: List.unmodifiable(stops),
      segments: List.unmodifiable(segments),
      markers: List.unmodifiable(markers),
    );
  }
}

/// canonical 地点引用（`objectTypeRef` 必须带 `.` 领域前缀）。
class AssistantRouteMapPlaceRef {
  const AssistantRouteMapPlaceRef._({
    required this.objectTypeRef,
    required this.objectId,
  });

  final String objectTypeRef;
  final String objectId;

  /// stop / segment / marker 之间对齐地点的唯一 key。
  String get placeKey => '$objectTypeRef:$objectId';

  static AssistantRouteMapPlaceRef? _tryParse(Object? value) {
    if (value is! Map) return null;
    final ref = value.cast<String, dynamic>();
    if (!_exactKeys(
          ref,
          const {'objectTypeRef', 'objectId'},
          const {'objectTypeRef', 'objectId'},
        ) ||
        !_validIdentifier(ref['objectTypeRef']) ||
        !(ref['objectTypeRef'] as String).contains('.') ||
        !_validIdentifier(ref['objectId'])) {
      return null;
    }
    return AssistantRouteMapPlaceRef._(
      objectTypeRef: ref['objectTypeRef'] as String,
      objectId: ref['objectId'] as String,
    );
  }
}

class AssistantRouteMapStop {
  const AssistantRouteMapStop._({
    required this.placeRef,
    required this.dayIndex,
    required this.order,
    required this.itemId,
    required this.title,
  });

  final AssistantRouteMapPlaceRef placeRef;
  final int dayIndex;
  final int order;
  final String itemId;
  final String title;
}

class AssistantRouteMapSegment {
  const AssistantRouteMapSegment._({
    required this.fromPlaceRef,
    required this.toPlaceRef,
    required this.modeToken,
    required this.order,
  });

  final AssistantRouteMapPlaceRef fromPlaceRef;
  final AssistantRouteMapPlaceRef toPlaceRef;
  final String modeToken;
  final int order;
}

class AssistantRouteMapMarker {
  const AssistantRouteMapMarker._({
    required this.momentId,
    required this.placeRef,
    required this.dayIndex,
    required this.itemId,
  });

  final String momentId;
  final AssistantRouteMapPlaceRef placeRef;
  final int dayIndex;
  final String itemId;
}

/// comparison_table 节点 `data` 的 typed 投影。
///
/// columns 上限 16、rows 上限 64 与既有渲染语义一致；任一为空返回 null，
/// 由调用方降级为纯文本节点。
class AssistantComparisonTableData {
  const AssistantComparisonTableData._({
    required this.columns,
    required this.rows,
  });

  final List<String> columns;
  final List<AssistantComparisonTableRow> rows;

  static AssistantComparisonTableData? tryParse(Map<String, dynamic> data) {
    final columnsRaw = data['columns'];
    final columns = columnsRaw is List
        ? columnsRaw
              .whereType<String>()
              .map((column) => column.trim())
              .where((column) => column.isNotEmpty)
              .take(16)
              .toList(growable: false)
        : const <String>[];
    final rowsRaw = data['rows'];
    final rows = rowsRaw is List
        ? rowsRaw
              .whereType<Map>()
              .take(64)
              .map(AssistantComparisonTableRow._fromObjectMap)
              .toList(growable: false)
        : const <AssistantComparisonTableRow>[];
    if (columns.isEmpty || rows.isEmpty) return null;
    return AssistantComparisonTableData._(
      columns: List.unmodifiable(columns),
      rows: rows,
    );
  }
}

class AssistantComparisonTableRow {
  const AssistantComparisonTableRow._(this._cells);

  final Map<String, String> _cells;

  factory AssistantComparisonTableRow._fromObjectMap(Map<Object?, Object?> row) {
    final cells = <String, String>{};
    for (final entry in row.entries) {
      final key = entry.key;
      if (key is! String) continue;
      cells[key] = entry.value?.toString() ?? '';
    }
    return AssistantComparisonTableRow._(Map.unmodifiable(cells));
  }

  String cellText(String column) => _cells[column] ?? '';
}

bool _exactKeys(
  Map<String, dynamic> value,
  Set<String> required,
  Set<String> allowed,
) => value.keys.every(allowed.contains) && required.every(value.containsKey);

List<Map<String, dynamic>> _objectList(Object? value) {
  if (value == null) return const [];
  if (value is! List) return const [];
  final result = <Map<String, dynamic>>[];
  for (final item in value) {
    if (item is! Map) return const [];
    result.add(item.cast<String, dynamic>());
  }
  return result;
}

bool _validIdentifier(Object? value) =>
    value is String &&
    _identifierPattern.hasMatch(value.trim()) &&
    !_unsafeValuePattern.hasMatch(value);

bool _validOptionalIdentifier(Object? value) =>
    value == null || value == '' || _validIdentifier(value);

bool _validOptionalText(Object? value, int maximum) =>
    value == null ||
    (value is String &&
        value.runes.length <= maximum &&
        !_unsafeValuePattern.hasMatch(value) &&
        !RegExp(r'<[^>]+>').hasMatch(value));

bool _validInteger(Object? value, int minimum, int maximum) =>
    value is num &&
    value.isFinite &&
    value == value.roundToDouble() &&
    value >= minimum &&
    value <= maximum;
