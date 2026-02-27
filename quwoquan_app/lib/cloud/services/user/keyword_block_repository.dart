import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 屏蔽词设置 Repository（三层模式）
abstract class KeywordBlockRepository {
  Future<List<String>> getBlockedKeywords();
  Future<void> setBlockedKeywords(List<String> keywords);

  Future<void> addBlockedKeyword(String keyword) async {
    final k = keyword.trim();
    if (k.isEmpty) return;
    final current = await getBlockedKeywords();
    if (current.contains(k)) return;
    await setBlockedKeywords(<String>[...current, k]);
  }
}

class MockKeywordBlockRepository extends KeywordBlockRepository {
  final List<String> _keywords = <String>[];

  @override
  Future<List<String>> getBlockedKeywords() async => List<String>.from(_keywords);

  @override
  Future<void> setBlockedKeywords(List<String> keywords) async {
    _keywords
      ..clear()
      ..addAll(keywords.map((e) => e.trim()).where((e) => e.isNotEmpty).toSet());
  }
}

class RemoteKeywordBlockRepository extends KeywordBlockRepository {
  RemoteKeywordBlockRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  })  : _httpClient = httpClient ?? CloudHttpClient(client: client ?? http.Client()),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<List<String>> getBlockedKeywords() async {
    final uri = Uri.parse('$_baseUrl/v1/user/settings/privacy');
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('user.settings.privacy.get'),
    );
    final map = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    final raw = map['blockedKeywords'];
    if (raw is List) {
      return raw.map((e) => e.toString().trim()).where((e) => e.isNotEmpty).toList();
    }
    return <String>[];
  }

  @override
  Future<void> setBlockedKeywords(List<String> keywords) async {
    final uri = Uri.parse('$_baseUrl/v1/user/settings/privacy');
    final normalized = keywords.map((e) => e.trim()).where((e) => e.isNotEmpty).toSet().toList();
    await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage('user.settings.privacy.patch'),
      body: <String, dynamic>{'blockedKeywords': normalized},
    );
  }
}

