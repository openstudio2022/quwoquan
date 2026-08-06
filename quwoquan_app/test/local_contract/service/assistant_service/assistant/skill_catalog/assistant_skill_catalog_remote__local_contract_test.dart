// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
// readiness_case: skill_catalog_get_skill_catalog_item_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/adapters/skill_catalog_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';
import '../../../../../support/runtime/codec/canonical_digest_fixture.dart';

const _configurationSchema = <String, Object?>{
  'type': 'object',
  'additionalProperties': false,
  'properties': <String, Object?>{
    'travelPace': <String, Object?>{
      'type': 'string',
      'enum': <String>['relaxed', 'balanced'],
    },
  },
};

void main() {
  test(
    'SkillCatalog lists lightweight items then fetches one setup schema',
    () async {
      final requests = <http.Request>[];
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requests.add(request);
          final response = request.url.path == '/assistant/skills'
              ? <String, Object?>{
                  'items': <Object?>[_catalogItem()],
                }
              : <String, Object?>{
                  'item': _catalogItem(),
                  'configurationSchema': _configurationSchema,
                };
          return http.Response(
            jsonEncode(response),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _CatalogAuthTokenProvider(),
      );
      final adapter = RemoteAssistantSkillCatalogAdapter(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.assistantSkills.id,
          routeId: AppUiSurfaces.assistantSkills.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'assistant-test-account',
            personaId: 'assistant-test-persona',
          ),
        ),
      );

      final listed = await adapter.listSkillCatalog();
      final detail = await adapter.getSkillCatalogItem(
        skillId: 'travel_companion',
      );

      expect(listed.single.skillId, 'travel_companion');
      expect(detail.item.releaseDigest, listed.single.releaseDigest);
      expect(detail.configurationSchema, isA<Map>());
      expect(requests.map((request) => request.url.path), <String>[
        '/assistant/skills',
        '/assistant/skills/travel_companion',
      ]);
      expect(requests.first.url.queryParameters['limit'], '64');
    },
  );
}

Map<String, Object?> _catalogItem() => <String, Object?>{
  'packageId': 'quwoquan.official.travel',
  'releaseDigest': canonicalFixtureSha256(const <String, Object?>{
    'packageId': 'quwoquan.official.travel',
    'releaseId': 'travel-companion-local-contract',
  }),
  'skillId': 'travel_companion',
  'domainId': 'travel',
  'displayName': '贴身旅行管家',
  'description': '一路计划，一路记录，一键成游记。',
  'catalogGroup': <String, Object?>{'id': 'travel', 'displayText': '旅行'},
  'requiresConsent': true,
  'requiredConsentScopes': <String>[
    'assistant.memory.preferences.read',
    'travel.trip.read',
  ],
  'consentScopeLabels': <Object?>[
    <String, Object?>{
      'id': 'assistant.memory.preferences.read',
      'displayText': '读取助手偏好',
    },
    <String, Object?>{'id': 'travel.trip.read', 'displayText': '读取行程'},
  ],
  'iconHint': 'airplane',
  'coverMediaRef': 'assistant.skill.travel.cover',
  'targetAudiences': <Object?>[
    <String, Object?>{
      'id': 'small_group_trip_organizer',
      'displayText': '小团组织者',
    },
  ],
  'dataUseSummary': '只读取已授权行程。',
  'examples': <Object?>[],
  'activationMode': 'hybrid',
  'surfaceKinds': <Object?>[
    <String, Object?>{'id': 'personal', 'displayText': '个人'},
    <String, Object?>{'id': 'conversation', 'displayText': '会话'},
    <String, Object?>{'id': 'circle', 'displayText': '圈子'},
  ],
  'configurationSchemaDigest': canonicalFixtureSha256(_configurationSchema),
  'setupTemplateRef': 'assistant.skill.setup.travel_companion',
  'configurationRequiredFields': <String>[],
};

final class _CatalogAuthTokenProvider implements CloudAuthTokenProvider {
  const _CatalogAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-catalog-test-token';
}
