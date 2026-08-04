// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_catalog_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/assistant_remote_test_support.dart';
import '../../../support/canonical_digest_fixture.dart';

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
  'displayName': '贴身旅行管家',
  'description': '一路计划，一路记录，一键成游记。',
  'category': 'travel',
  'requiresConsent': true,
  'requiredConsentScopes': <String>[
    'assistant.memory.preferences.read',
    'travel.trip.read',
  ],
  'iconHint': 'airplane',
  'coverMediaRef': 'assistant.skill.travel.cover',
  'targetUsers': <String>['small_group_trip_organizer'],
  'dataUseSummary': '只读取已授权行程。',
  'exampleRefs': <String>[],
  'activationMode': 'hybrid',
  'allowedSurfaceKinds': <String>['personal', 'conversation', 'circle'],
  'configurationSchemaDigest': canonicalFixtureSha256(_configurationSchema),
  'setupTemplateRef': 'assistant.skill.setup.travel_companion',
  'configurationRequiredFields': <String>[],
};

final class _CatalogAuthTokenProvider implements CloudAuthTokenProvider {
  const _CatalogAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-catalog-test-token';
}
