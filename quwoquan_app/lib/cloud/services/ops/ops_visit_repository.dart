import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

class OpsVisitReportInput {
  const OpsVisitReportInput({
    required this.userId,
    required this.targetType,
    required this.targetKey,
    this.sessionId = '',
    this.source = '',
  });

  final String userId;
  final String targetType;
  final String targetKey;
  final String sessionId;
  final String source;

  factory OpsVisitReportInput.fromJson(Map<String, dynamic> json) {
    return OpsVisitReportInput(
      userId: (json['userId'] ?? '').toString(),
      targetType: (json['targetType'] ?? '').toString(),
      targetKey: (json['targetKey'] ?? '').toString(),
      sessionId: (json['sessionId'] ?? '').toString(),
      source: (json['source'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'userId': userId,
      'targetType': targetType,
      'targetKey': targetKey,
      if (sessionId.trim().isNotEmpty) 'sessionId': sessionId.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
    };
  }
}

class OpsVisitStatsItem {
  const OpsVisitStatsItem({
    required this.targetType,
    required this.targetKey,
    required this.userId,
    required this.visitCount,
  });

  final String targetType;
  final String targetKey;
  final String userId;
  final int visitCount;

  factory OpsVisitStatsItem.fromJson(Map<String, dynamic> json) {
    return OpsVisitStatsItem(
      targetType: (json['targetType'] ?? '').toString(),
      targetKey: (json['targetKey'] ?? '').toString(),
      userId: (json['userId'] ?? '').toString(),
      visitCount: _asInt(json['visitCount']),
    );
  }
}

class OpsVisitStats {
  const OpsVisitStats({required this.totalVisits, required this.items});

  final int totalVisits;
  final List<OpsVisitStatsItem> items;

  factory OpsVisitStats.fromJson(Map<String, dynamic> json) {
    final rawItems =
        (json['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return OpsVisitStats(
      totalVisits: _asInt(json['totalVisits']),
      items: rawItems
          .map(OpsVisitStatsItem.fromJson)
          .where((item) => item.targetKey.trim().isNotEmpty)
          .toList(growable: false),
    );
  }

  static const OpsVisitStats empty = OpsVisitStats(
    totalVisits: 0,
    items: <OpsVisitStatsItem>[],
  );
}

abstract class OpsVisitRepository {
  Future<void> recordVisit({required OpsVisitReportInput input});

  Future<OpsVisitStats> getVisitStats({
    required String targetType,
    required String targetKey,
  });
}

class MockOpsVisitRepository implements OpsVisitRepository {
  final Map<String, int> _counts = <String, int>{};

  @override
  Future<void> recordVisit({required OpsVisitReportInput input}) async {
    final key = '${input.userId}|${input.targetType}|${input.targetKey}';
    _counts.update(key, (count) => count + 1, ifAbsent: () => 1);
  }

  @override
  Future<OpsVisitStats> getVisitStats({
    required String targetType,
    required String targetKey,
  }) async {
    var total = 0;
    final items = <OpsVisitStatsItem>[];
    for (final entry in _counts.entries) {
      final parts = entry.key.split('|');
      if (parts.length != 3) {
        continue;
      }
      if (parts[1] != targetType || parts[2] != targetKey) {
        continue;
      }
      total += entry.value;
      items.add(
        OpsVisitStatsItem(
          targetType: parts[1],
          targetKey: parts[2],
          userId: parts[0],
          visitCount: entry.value,
        ),
      );
    }
    return OpsVisitStats(totalVisits: total, items: items);
  }
}

class RemoteOpsVisitRepository implements OpsVisitRepository {
  RemoteOpsVisitRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(client: http.Client()),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Map<String, String> _headersForOps({required String pageId}) {
    return CloudRequestHeaders.forPage(pageId);
  }

  @override
  Future<void> recordVisit({required OpsVisitReportInput input}) async {
    await _httpClient.postJson(
      _uri(OpsApiMetadata.recordVisitPath),
      headers: _headersForOps(pageId: OpsRequestPageIds.recordVisit),
      body: input.toJson(),
    );
  }

  @override
  Future<OpsVisitStats> getVisitStats({
    required String targetType,
    required String targetKey,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        OpsApiMetadata.getVisitStatsPath,
        queryParameters: <String, String>{
          'targetType': targetType,
          'targetKey': targetKey,
        },
      ),
      headers: _headersForOps(pageId: OpsRequestPageIds.getVisitStats),
    );
    final object = decoded is String
        ? CloudResponseDecoder.asObject(jsonDecode(decoded))
        : CloudResponseDecoder.asObject(decoded);
    return OpsVisitStats.fromJson(object);
  }
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
