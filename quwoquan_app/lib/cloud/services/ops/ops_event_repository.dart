import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/widgets.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

const String kOpsEventQueueBoxName = 'ops_event_queue';

class OpsEventRecordInput {
  const OpsEventRecordInput({
    required this.eventId,
    required this.eventType,
    required this.eventName,
    required this.occurredAt,
    this.eventVersion = 'v1',
    this.priority = 'P1',
    this.producer = 'app',
    this.source = '',
    this.userIdHash = '',
    this.sessionId = '',
    this.pageVisitId = '',
    this.surfaceId = '',
    this.routeId = '',
    this.operationId = '',
    this.requestId = '',
    this.traceId = '',
    this.pageName = '',
    this.targetType = '',
    this.targetKey = '',
    this.entityType = '',
    this.entityId = '',
    this.experimentBucket = '',
    this.clientSentAt = '',
    this.errorCode = '',
    this.errorModule = '',
    this.errorKind = '',
    this.errorReason = '',
    this.origin = '',
    this.nature = '',
    this.failurePoint = '',
    this.stackHash = '',
    this.businessObject = '',
    this.functionModule = '',
    this.appRuntimeEnv = '',
    this.appVersion = '',
    this.platform = '',
    this.networkClass = '',
    this.payload = const <String, dynamic>{},
    this.metrics = const <String, dynamic>{},
  });

  final String eventId;
  final String eventType;
  final String eventName;
  final String eventVersion;
  final String priority;
  final String producer;
  final String source;
  final String userIdHash;
  final String sessionId;
  final String pageVisitId;
  final String surfaceId;
  final String routeId;
  final String operationId;
  final String requestId;
  final String traceId;
  final String pageName;
  final String targetType;
  final String targetKey;
  final String entityType;
  final String entityId;
  final String experimentBucket;
  final String occurredAt;
  final String clientSentAt;
  final String errorCode;
  final String errorModule;
  final String errorKind;
  final String errorReason;
  final String origin;
  final String nature;
  final String failurePoint;
  final String stackHash;
  final String businessObject;
  final String functionModule;
  final String appRuntimeEnv;
  final String appVersion;
  final String platform;
  final String networkClass;
  final Map<String, dynamic> payload;
  final Map<String, dynamic> metrics;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'eventId': eventId,
      'eventType': eventType,
      'eventName': eventName,
      'eventVersion': eventVersion,
      'priority': priority,
      'producer': producer,
      if (source.isNotEmpty) 'source': source,
      if (userIdHash.isNotEmpty) 'userIdHash': userIdHash,
      if (sessionId.isNotEmpty) 'sessionId': sessionId,
      if (pageVisitId.isNotEmpty) 'pageVisitId': pageVisitId,
      if (surfaceId.isNotEmpty) 'surfaceId': surfaceId,
      if (routeId.isNotEmpty) 'routeId': routeId,
      if (operationId.isNotEmpty) 'operationId': operationId,
      if (requestId.isNotEmpty) 'requestId': requestId,
      if (traceId.isNotEmpty) 'traceId': traceId,
      if (pageName.isNotEmpty) 'pageName': pageName,
      if (targetType.isNotEmpty) 'targetType': targetType,
      if (targetKey.isNotEmpty) 'targetKey': targetKey,
      if (entityType.isNotEmpty) 'entityType': entityType,
      if (entityId.isNotEmpty) 'entityId': entityId,
      if (experimentBucket.isNotEmpty) 'experimentBucket': experimentBucket,
      'occurredAt': occurredAt,
      if (clientSentAt.isNotEmpty) 'clientSentAt': clientSentAt,
      if (errorCode.isNotEmpty) 'errorCode': errorCode,
      if (errorModule.isNotEmpty) 'errorModule': errorModule,
      if (errorKind.isNotEmpty) 'errorKind': errorKind,
      if (errorReason.isNotEmpty) 'errorReason': errorReason,
      if (origin.isNotEmpty) 'origin': origin,
      if (nature.isNotEmpty) 'nature': nature,
      if (failurePoint.isNotEmpty) 'failurePoint': failurePoint,
      if (stackHash.isNotEmpty) 'stackHash': stackHash,
      if (businessObject.isNotEmpty) 'businessObject': businessObject,
      if (functionModule.isNotEmpty) 'functionModule': functionModule,
      if (appRuntimeEnv.isNotEmpty) 'appRuntimeEnv': appRuntimeEnv,
      if (appVersion.isNotEmpty) 'appVersion': appVersion,
      if (platform.isNotEmpty) 'platform': platform,
      if (networkClass.isNotEmpty) 'networkClass': networkClass,
      if (payload.isNotEmpty) 'payload': payload,
      if (metrics.isNotEmpty) 'metrics': metrics,
    };
  }

  factory OpsEventRecordInput.fromJson(Map<String, dynamic> json) {
    return OpsEventRecordInput(
      eventId: (json['eventId'] ?? '').toString(),
      eventType: (json['eventType'] ?? '').toString(),
      eventName: (json['eventName'] ?? '').toString(),
      occurredAt: (json['occurredAt'] ?? '').toString(),
      eventVersion: (json['eventVersion'] ?? 'v1').toString(),
      priority: (json['priority'] ?? 'P1').toString(),
      producer: (json['producer'] ?? 'app').toString(),
      source: (json['source'] ?? '').toString(),
      userIdHash: (json['userIdHash'] ?? '').toString(),
      sessionId: (json['sessionId'] ?? '').toString(),
      pageVisitId: (json['pageVisitId'] ?? '').toString(),
      surfaceId: (json['surfaceId'] ?? '').toString(),
      routeId: (json['routeId'] ?? '').toString(),
      operationId: (json['operationId'] ?? '').toString(),
      requestId: (json['requestId'] ?? '').toString(),
      traceId: (json['traceId'] ?? '').toString(),
      pageName: (json['pageName'] ?? '').toString(),
      targetType: (json['targetType'] ?? '').toString(),
      targetKey: (json['targetKey'] ?? '').toString(),
      entityType: (json['entityType'] ?? '').toString(),
      entityId: (json['entityId'] ?? '').toString(),
      experimentBucket: (json['experimentBucket'] ?? '').toString(),
      clientSentAt: (json['clientSentAt'] ?? '').toString(),
      errorCode: (json['errorCode'] ?? '').toString(),
      errorModule: (json['errorModule'] ?? '').toString(),
      errorKind: (json['errorKind'] ?? '').toString(),
      errorReason: (json['errorReason'] ?? '').toString(),
      origin: (json['origin'] ?? '').toString(),
      nature: (json['nature'] ?? '').toString(),
      failurePoint: (json['failurePoint'] ?? '').toString(),
      stackHash: (json['stackHash'] ?? '').toString(),
      businessObject: (json['businessObject'] ?? '').toString(),
      functionModule: (json['functionModule'] ?? '').toString(),
      appRuntimeEnv: (json['appRuntimeEnv'] ?? '').toString(),
      appVersion: (json['appVersion'] ?? '').toString(),
      platform: (json['platform'] ?? '').toString(),
      networkClass: (json['networkClass'] ?? '').toString(),
      payload: _asObject(json['payload']),
      metrics: _asObject(json['metrics']),
    );
  }

  factory OpsEventRecordInput.fromJsonObject(Map<String, Object?> json) {
    return OpsEventRecordInput.fromJson(Map<String, dynamic>.from(json));
  }
}

class OpsEventBatchAck {
  const OpsEventBatchAck({
    required this.acceptedCount,
    required this.duplicateCount,
  });

  final int acceptedCount;
  final int duplicateCount;

  factory OpsEventBatchAck.fromJson(Map<String, dynamic> json) {
    return OpsEventBatchAck(
      acceptedCount: _asInt(json['acceptedCount']),
      duplicateCount: _asInt(json['duplicateCount']),
    );
  }
}

class OpsEventSummary {
  const OpsEventSummary({
    required this.totalCount,
    required this.dimensions,
    this.eventType = '',
    this.eventName = '',
    this.latestOccurredAt = '',
  });

  final int totalCount;
  final Map<String, Map<String, int>> dimensions;
  final String eventType;
  final String eventName;
  final String latestOccurredAt;

  factory OpsEventSummary.fromJson(Map<String, dynamic> json) {
    final dimensions = <String, Map<String, int>>{};
    final rawDimensions =
        (json['dimensions'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    for (final entry in rawDimensions.entries) {
      final rawBucket =
          (entry.value as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      dimensions[entry.key] = rawBucket.map(
        (key, value) => MapEntry(key, _asInt(value)),
      );
    }
    return OpsEventSummary(
      totalCount: _asInt(json['totalCount']),
      dimensions: dimensions,
      eventType: (json['eventType'] ?? '').toString(),
      eventName: (json['eventName'] ?? '').toString(),
      latestOccurredAt: (json['latestOccurredAt'] ?? '').toString(),
    );
  }
}

class OpsEventDrilldownItem {
  const OpsEventDrilldownItem({
    required this.eventId,
    required this.eventType,
    required this.eventName,
    required this.occurredAt,
    this.pageName = '',
    this.surfaceId = '',
    this.routeId = '',
    this.targetType = '',
    this.targetKey = '',
    this.entityType = '',
    this.entityId = '',
    this.experimentBucket = '',
    this.payload = const <String, dynamic>{},
    this.metrics = const <String, dynamic>{},
  });

  final String eventId;
  final String eventType;
  final String eventName;
  final String occurredAt;
  final String pageName;
  final String surfaceId;
  final String routeId;
  final String targetType;
  final String targetKey;
  final String entityType;
  final String entityId;
  final String experimentBucket;
  final Map<String, dynamic> payload;
  final Map<String, dynamic> metrics;

  factory OpsEventDrilldownItem.fromJson(Map<String, dynamic> json) {
    return OpsEventDrilldownItem(
      eventId: (json['eventId'] ?? '').toString(),
      eventType: (json['eventType'] ?? '').toString(),
      eventName: (json['eventName'] ?? '').toString(),
      occurredAt: (json['occurredAt'] ?? '').toString(),
      pageName: (json['pageName'] ?? '').toString(),
      surfaceId: (json['surfaceId'] ?? '').toString(),
      routeId: (json['routeId'] ?? '').toString(),
      targetType: (json['targetType'] ?? '').toString(),
      targetKey: (json['targetKey'] ?? '').toString(),
      entityType: (json['entityType'] ?? '').toString(),
      entityId: (json['entityId'] ?? '').toString(),
      experimentBucket: (json['experimentBucket'] ?? '').toString(),
      payload: _asObject(json['payload']),
      metrics: _asObject(json['metrics']),
    );
  }
}

class OpsEventDrilldown {
  const OpsEventDrilldown({required this.totalCount, required this.items});

  final int totalCount;
  final List<OpsEventDrilldownItem> items;

  factory OpsEventDrilldown.fromJson(Map<String, dynamic> json) {
    final rawItems =
        (json['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return OpsEventDrilldown(
      totalCount: _asInt(json['totalCount']),
      items: rawItems
          .map(OpsEventDrilldownItem.fromJson)
          .toList(growable: false),
    );
  }
}

abstract class OpsEventRepository {
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  });

  Future<void> flushPending();

  Future<OpsEventSummary> getEventSummary({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
  });

  Future<OpsEventDrilldown> getEventDrilldown({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
    int limit = CloudApiDefaults.pageLimit,
  });
}

class MockOpsEventRepository implements OpsEventRepository {
  final List<OpsEventRecordInput> recorded = <OpsEventRecordInput>[];

  @override
  Future<OpsEventSummary> getEventSummary({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
  }) async {
    final matched = _filter(
      eventType: eventType,
      eventName: eventName,
      pageName: pageName,
      surfaceId: surfaceId,
      routeId: routeId,
      targetType: targetType,
      targetKey: targetKey,
      entityType: entityType,
      entityId: entityId,
      experimentBucket: experimentBucket,
      source: source,
    );
    final dimensions = <String, Map<String, int>>{};
    for (final event in matched) {
      _addDimension(dimensions, 'pageName', event.pageName);
      _addDimension(dimensions, 'surfaceId', event.surfaceId);
      _addDimension(dimensions, 'routeId', event.routeId);
      _addDimension(dimensions, 'experimentBucket', event.experimentBucket);
      _addDimension(dimensions, 'targetKey', event.targetKey);
      _addDimension(dimensions, 'entityId', event.entityId);
      _addDimension(dimensions, 'source', event.source);
      _addDimension(dimensions, 'eventName', event.eventName);
    }
    return OpsEventSummary(
      totalCount: matched.length,
      dimensions: dimensions,
      eventType: eventType,
      eventName: eventName,
      latestOccurredAt: matched.isEmpty ? '' : matched.first.occurredAt,
    );
  }

  @override
  Future<OpsEventDrilldown> getEventDrilldown({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final matched = _filter(
      eventType: eventType,
      eventName: eventName,
      pageName: pageName,
      surfaceId: surfaceId,
      routeId: routeId,
      targetType: targetType,
      targetKey: targetKey,
      entityType: entityType,
      entityId: entityId,
      experimentBucket: experimentBucket,
      source: source,
    );
    final items = matched
        .take(limit)
        .map((event) {
          return OpsEventDrilldownItem(
            eventId: event.eventId,
            eventType: event.eventType,
            eventName: event.eventName,
            occurredAt: event.occurredAt,
            pageName: event.pageName,
            surfaceId: event.surfaceId,
            routeId: event.routeId,
            targetType: event.targetType,
            targetKey: event.targetKey,
            entityType: event.entityType,
            entityId: event.entityId,
            experimentBucket: event.experimentBucket,
            payload: event.payload,
            metrics: event.metrics,
          );
        })
        .toList(growable: false);
    return OpsEventDrilldown(totalCount: items.length, items: items);
  }

  @override
  Future<void> flushPending() async {}

  @override
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  }) async {
    recorded.addAll(events);
    return OpsEventBatchAck(acceptedCount: events.length, duplicateCount: 0);
  }

  List<OpsEventRecordInput> _filter({
    required String eventType,
    required String eventName,
    required String pageName,
    required String surfaceId,
    required String routeId,
    required String targetType,
    required String targetKey,
    required String entityType,
    required String entityId,
    required String experimentBucket,
    required String source,
  }) {
    return recorded
        .where((event) {
          return (eventType.isEmpty || event.eventType == eventType) &&
              (eventName.isEmpty || event.eventName == eventName) &&
              (pageName.isEmpty || event.pageName == pageName) &&
              (surfaceId.isEmpty || event.surfaceId == surfaceId) &&
              (routeId.isEmpty || event.routeId == routeId) &&
              (targetType.isEmpty || event.targetType == targetType) &&
              (targetKey.isEmpty || event.targetKey == targetKey) &&
              (entityType.isEmpty || event.entityType == entityType) &&
              (entityId.isEmpty || event.entityId == entityId) &&
              (experimentBucket.isEmpty ||
                  event.experimentBucket == experimentBucket) &&
              (source.isEmpty || event.source == source);
        })
        .toList(growable: false)
      ..sort((a, b) => b.occurredAt.compareTo(a.occurredAt));
  }
}

class RemoteOpsEventRepository
    with WidgetsBindingObserver
    implements OpsEventRepository {
  RemoteOpsEventRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    String? queueBoxName,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _queueBoxName = queueBoxName ?? kOpsEventQueueBoxName {
    _bindLifecycle();
  }

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final String _queueBoxName;

  void _bindLifecycle() {
    try {
      WidgetsBinding.instance.addObserver(this);
    } catch (_) {}
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      unawaited(flushPending());
    }
  }

  void dispose() {
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {}
  }

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Future<Box<String>> _ensureBox() async {
    if (!Hive.isBoxOpen(_queueBoxName)) {
      try {
        await Hive.initFlutter();
      } catch (_) {}
      return Hive.openBox<String>(_queueBoxName);
    }
    return Hive.box<String>(_queueBoxName);
  }

  @override
  Future<void> flushPending() async {
    final box = await _ensureBox();
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    var consecutiveFailures = 0;
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final parsed = (jsonDecode(raw) as List)
            .whereType<Map>()
            .map(
              (item) =>
                  OpsEventRecordInput.fromJson(item.cast<String, dynamic>()),
            )
            .toList(growable: false);
        await _postBatch(parsed);
        await box.delete(key);
        consecutiveFailures = 0;
      } catch (e) {
        developer.log(
          'OpsEventRepository.flushPending failed key=$key: $e',
          name: 'ops',
        );
        consecutiveFailures++;
        if (consecutiveFailures >= 3) break;
      }
    }
  }

  @override
  Future<OpsEventSummary> getEventSummary({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        OpsApiMetadata.getEventSummaryPath,
        queryParameters: _queryParameters(
          eventType: eventType,
          eventName: eventName,
          pageName: pageName,
          surfaceId: surfaceId,
          routeId: routeId,
          targetType: targetType,
          targetKey: targetKey,
          entityType: entityType,
          entityId: entityId,
          experimentBucket: experimentBucket,
          source: source,
        ),
      ),
      headers: CloudRequestHeaders.forPage(OpsRequestPageIds.getEventSummary),
    );
    return OpsEventSummary.fromJson(
      CloudResponseDecoder.asObject(
        decoded is String ? jsonDecode(decoded) : decoded,
      ),
    );
  }

  @override
  Future<OpsEventDrilldown> getEventDrilldown({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        OpsApiMetadata.getEventDrilldownPath,
        queryParameters: _queryParameters(
          eventType: eventType,
          eventName: eventName,
          pageName: pageName,
          surfaceId: surfaceId,
          routeId: routeId,
          targetType: targetType,
          targetKey: targetKey,
          entityType: entityType,
          entityId: entityId,
          experimentBucket: experimentBucket,
          source: source,
          limit: limit,
        ),
      ),
      headers: CloudRequestHeaders.forPage(OpsRequestPageIds.getEventDrilldown),
    );
    return OpsEventDrilldown.fromJson(
      CloudResponseDecoder.asObject(
        decoded is String ? jsonDecode(decoded) : decoded,
      ),
    );
  }

  @override
  Future<OpsEventBatchAck> reportEventBatch({
    required List<OpsEventRecordInput> events,
  }) async {
    if (events.isEmpty) {
      return const OpsEventBatchAck(acceptedCount: 0, duplicateCount: 0);
    }
    await flushPending();
    try {
      return await _postBatch(events);
    } catch (e) {
      developer.log(
        'ops reportEventBatch failed, enqueuing: $e',
        name: 'OpsEventRepository',
      );
      await _enqueue(events);
      return const OpsEventBatchAck(acceptedCount: 0, duplicateCount: 0);
    }
  }

  Future<OpsEventBatchAck> _postBatch(List<OpsEventRecordInput> events) async {
    final decoded = await _httpClient.postJson(
      _uri(OpsApiMetadata.reportEventBatchPath),
      headers: CloudRequestHeaders.forPage(OpsRequestPageIds.reportEventBatch),
      body: <String, dynamic>{
        'events': events.map((event) => event.toJson()).toList(growable: false),
      },
    );
    return OpsEventBatchAck.fromJson(
      CloudResponseDecoder.asObject(
        decoded is String ? jsonDecode(decoded) : decoded,
      ),
    );
  }

  Future<void> _enqueue(List<OpsEventRecordInput> events) async {
    final box = await _ensureBox();
    final now = DateTime.now().microsecondsSinceEpoch.toString();
    await box.put(
      now,
      jsonEncode(events.map((event) => event.toJson()).toList(growable: false)),
    );
    const maxBacklog = 200;
    if (box.length > maxBacklog) {
      final keys = box.keys.map((key) => key.toString()).toList(growable: false)
        ..sort();
      final overflow = box.length - maxBacklog;
      for (var i = 0; i < overflow; i++) {
        await box.delete(keys[i]);
      }
    }
  }

  Map<String, String> _queryParameters({
    String eventType = '',
    String eventName = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String targetType = '',
    String targetKey = '',
    String entityType = '',
    String entityId = '',
    String experimentBucket = '',
    String source = '',
    int? limit,
  }) {
    return <String, String>{
      if (eventType.trim().isNotEmpty) 'eventType': eventType.trim(),
      if (eventName.trim().isNotEmpty) 'eventName': eventName.trim(),
      if (pageName.trim().isNotEmpty) 'pageName': pageName.trim(),
      if (surfaceId.trim().isNotEmpty) 'surfaceId': surfaceId.trim(),
      if (routeId.trim().isNotEmpty) 'routeId': routeId.trim(),
      if (targetType.trim().isNotEmpty) 'targetType': targetType.trim(),
      if (targetKey.trim().isNotEmpty) 'targetKey': targetKey.trim(),
      if (entityType.trim().isNotEmpty) 'entityType': entityType.trim(),
      if (entityId.trim().isNotEmpty) 'entityId': entityId.trim(),
      if (experimentBucket.trim().isNotEmpty)
        'experimentBucket': experimentBucket.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
      if (limit != null && limit > 0) 'limit': '$limit',
    };
  }
}

Map<String, dynamic> _asObject(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.cast<String, dynamic>();
  }
  return const <String, dynamic>{};
}

int _asInt(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse((value ?? '').toString()) ?? 0;
}

void _addDimension(
  Map<String, Map<String, int>> dimensions,
  String name,
  String value,
) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) {
    return;
  }
  final bucket = dimensions.putIfAbsent(name, () => <String, int>{});
  bucket.update(trimmed, (count) => count + 1, ifAbsent: () => 1);
}
