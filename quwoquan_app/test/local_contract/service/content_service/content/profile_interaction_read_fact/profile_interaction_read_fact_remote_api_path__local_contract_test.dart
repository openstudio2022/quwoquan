/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004
// readiness_case: profile_interaction_read_fact_append_profile_interaction_read_fact_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_read_fact/adapters/profile_interaction_read_fact_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  if (request.method == 'POST' &&
      request.url.path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds
                .contentProfileInteractionReadFactAppendProfileInteractionReadFact,
            pathParameters: const <String, String>{
              'personaId': 'persona-1',
              'interactionId': 'activity-1',
            },
          )) {
    return remoteApiPathJsonResponse({
      'factId': 'fact-1',
      'activityId': 'activity-1',
      'state': 'read',
      'occurredAt': '2026-07-19T00:00:00Z',
      'replayed': false,
    });
  }
  return remoteApiPathJsonResponse('{}');
}

void main() {
  group('Profile interaction read fact adapter — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteProfileInteractionReadFactWriter readFactWriter;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      readFactWriter = RemoteProfileInteractionReadFactWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.profileHome.id,
          routeId: AppUiSurfaces.profileHome.routeId,
          clientPageId: clientPageId,
          idempotencyKey:
              clientPageId ==
                  ContentRequestPageIds.appendProfileInteractionReadFact
              ? 'profile-interaction-path-contract'
              : null,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );
    });

    test('append read fact → canonical mutation path', () async {
      await readFactWriter.appendReadFact(
        AppendContentProfileInteractionReadFactCommand(
          personaId: 'persona-1',
          activityId: 'activity-1',
          state: ProfileInteractionReadState.read,
        ),
      );
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds
              .contentProfileInteractionReadFactAppendProfileInteractionReadFact,
          pathParameters: const <String, String>{
            'personaId': 'persona-1',
            'interactionId': 'activity-1',
          },
        ),
      );
    });
  });
}
