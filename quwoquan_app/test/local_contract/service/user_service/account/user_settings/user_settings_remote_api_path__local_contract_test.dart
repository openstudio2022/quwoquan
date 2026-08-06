/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/adapters/user_settings_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserSettingsGetNotificationSettings,
          )) {
    return remoteApiPathJsonResponse({
      'userId': 'user-1',
      'enablePush': true,
      'enableMarketing': false,
      'quietHoursStart': null,
      'quietHoursEnd': null,
      'version': 1,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserSettingsGetPrivacySettings,
          )) {
    return remoteApiPathJsonResponse({
      'userId': 'user-1',
      'allowStrangerMsg': true,
      'profileVisibility': 'public',
      'contentLanguage': null,
      'feedPreference': null,
      'assistantEnabled': true,
      'blockedKeywords': <Object?>[],
      'version': 1,
      'updatedAt': '2026-07-20T00:00:00Z',
    });
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('UserSettingsQuery Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteUserSettingsQueryReader settingsQuery;

    setUp(() {
      log = [];
      settingsQuery = RemoteUserSettingsQueryReader(
        client: buildRemoteApiPathOperationClient(
          log,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId) {
          final surface =
              clientPageId == UserRequestPageIds.getNotificationSettings
              ? AppUiSurfaces.settingsNotifications
              : AppUiSurfaces.settingsPrivacy;
          return CloudOperationInvocationContext(
            surfaceId: surface.id,
            routeId: surface.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          );
        },
      );
    });

    test(
      'getNotificationSettings → GET /user/settings/notifications',
      () async {
        await settingsQuery.getNotificationSettings();
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserSettingsGetNotificationSettings,
          ),
        );
        expectRemoteApiPathHeaders(
          log.last.headers,
          clientPageId: UserRequestPageIds.getNotificationSettings,
          surfaceId: AppUiSurfaces.settingsNotifications.id,
          operationId:
              AppCloudOperationIds.userUserSettingsGetNotificationSettings,
        );
      },
    );

    test('getPrivacySettings → GET /user/settings/privacy', () async {
      await settingsQuery.getPrivacySettings();
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userUserSettingsGetPrivacySettings,
        ),
      );
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: UserRequestPageIds.getPrivacySettings,
        surfaceId: AppUiSurfaces.settingsPrivacy.id,
        operationId: AppCloudOperationIds.userUserSettingsGetPrivacySettings,
      );
    });
  });
}
