import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// Behavior event for recommendation pipeline.
class BehaviorEvent {
  const BehaviorEvent({
    required this.contentId,
    required this.action,
    this.tags,
    this.duration,
  });

  final String contentId;

  /// One of: impression, click, dwell, like, favorite, share, dislike, report
  final String action;
  final List<String>? tags;

  /// Dwell time in seconds (for dwell action)
  final double? duration;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contentId': contentId,
    'action': action,
    if (tags != null && tags!.isNotEmpty) 'tags': tags,
    if (duration != null && duration! > 0) 'duration': duration,
  };
}

/// Behavior Repository (三层模式: Abstract → Mock → Remote)
///
/// 端侧行为上报，对接云侧 POST /v1/content/behaviors。
/// sessionId 通过 CloudRequestHeaders 自动注入。
abstract class BehaviorRepository {
  Future<void> reportEvents({required List<BehaviorEvent> events});

  Future<void> reportSingle({
    required String contentId,
    required String action,
    List<String>? tags,
    double? duration,
  }) {
    return reportEvents(
      events: <BehaviorEvent>[
        BehaviorEvent(
          contentId: contentId,
          action: action,
          tags: tags,
          duration: duration,
        ),
      ],
    );
  }
}

/// Mock 实现：本地记录，不发 HTTP 请求。
class MockBehaviorRepository extends BehaviorRepository {
  final List<BehaviorEvent> recorded = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    recorded.addAll(events);
  }
}

/// Remote 实现：对接云侧 POST /v1/content/behaviors。
class RemoteBehaviorRepository extends BehaviorRepository {
  RemoteBehaviorRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    if (events.isEmpty) return;

    final uri = Uri.parse('$_baseUrl/v1/content/behaviors');
    final body = <String, dynamic>{
      'sessionId': CloudRequestHeaders.sessionId,
      'events': events.map((e) => e.toJson()).toList(),
    };

    try {
      await _httpClient.postJson(
        uri,
        headers: CloudRequestHeaders.forPage('content.behavior.report'),
        body: body,
      );
    } catch (_) {
      // Fire-and-forget: behavior reporting should not block UI.
      // Errors are silently dropped; observability is on the server side.
    }
  }
}
