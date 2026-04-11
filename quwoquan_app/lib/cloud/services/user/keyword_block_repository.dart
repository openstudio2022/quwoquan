import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/privacy_settings_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
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

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<List<String>> getBlockedKeywords() async {
    final uri = _uri(UserApiMetadata.getPrivacySettingsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getPrivacySettings),
    );
    final map = CloudResponseDecoder.asObject(
      decoded,
      context: UserRequestPageIds.getPrivacySettings,
    );
    final wire = PrivacySettingsWireDto.fromMap(map);
    return wire.blockedKeywords
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<void> setBlockedKeywords(List<String> keywords) async {
    final uri = _uri(UserApiMetadata.updatePrivacySettingsPath);
    final normalized = keywords.map((e) => e.trim()).where((e) => e.isNotEmpty).toSet().toList();
    await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.updatePrivacySettings,
      ),
      body: <String, dynamic>{'blockedKeywords': normalized},
    );
  }
}

