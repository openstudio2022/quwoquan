import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// User 域 Repository：persona、follow、settings、push token 等业务对象入口。
///
/// 说明：端侧目前 persona 管理页仍是 UI 内 mock；这里先落地骨架，
/// 后续再把页面数据源切到该 Repository。
abstract class UserRepository {
  Future<List<Map<String, dynamic>>> listPersonas();
  Future<void> activatePersona(String personaId);

  Future<Map<String, dynamic>> getNotificationSettings();
  Future<Map<String, dynamic>> getPrivacySettings();
}

class MockUserRepository implements UserRepository {
  @override
  Future<void> activatePersona(String personaId) async {}

  @override
  Future<Map<String, dynamic>> getNotificationSettings() async {
    return <String, dynamic>{'enablePush': true};
  }

  @override
  Future<Map<String, dynamic>> getPrivacySettings() async {
    return <String, dynamic>{'profileVisibility': 'public'};
  }

  @override
  Future<List<Map<String, dynamic>>> listPersonas() async {
    return const <Map<String, dynamic>>[];
  }
}

class RemoteUserRepository implements UserRepository {
  RemoteUserRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<List<Map<String, dynamic>>> listPersonas() async {
    final uri = _uri(UserApiMetadata.listPersonasPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listPersonas),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'user.persona.list',
    );
    return page.items;
  }

  @override
  Future<void> activatePersona(String personaId) async {
    final uri = _uri(UserApiMetadata.activatePersonaPath(personaId: personaId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.activatePersona),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<Map<String, dynamic>> getNotificationSettings() async {
    final uri = _uri(UserApiMetadata.getNotificationSettingsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.getNotificationSettings,
      ),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'user.notification_settings.get',
    );
  }

  @override
  Future<Map<String, dynamic>> getPrivacySettings() async {
    final uri = _uri(UserApiMetadata.getPrivacySettingsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.getPrivacySettings),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'user.privacy_settings.get',
    );
  }
}

