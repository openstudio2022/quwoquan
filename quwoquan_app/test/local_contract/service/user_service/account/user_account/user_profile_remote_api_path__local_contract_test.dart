/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

const _personaProfile = <String, Object?>{
  'personaId': 'u1',
  'subjectType': 'persona',
  'userHandle': 'u1',
  'displayName': 'User One',
  'nicknameCustomized': false,
  'followerCount': 0,
  'followingCount': 0,
  'postCount': 0,
  'circleCount': 0,
  'likeCount': 0,
  'profileVisibility': 'public',
  'isolationLevel': 'open',
  'inheritsFromOwner': true,
  'updatedAt': '2026-07-20T00:00:00Z',
};

http.Response _responseFor(http.Request request) {
  if (request.method == 'GET' &&
      request.url.path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaProfile,
            pathParameters: const <String, String>{'personaId': 'u1'},
          )) {
    return remoteApiPathJsonResponse(_personaProfile);
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('ProfileQuery Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteProfileQuery query;

    setUp(() {
      log = [];
      final userProfileQuery = RemoteUserProfileQueryFacet(
        client: buildRemoteApiPathOperationClient(
          log,
          responseFor: _responseFor,
        ),
        invocationContext: (clientPageId, _) {
          final surface = clientPageId == UserRequestPageIds.getMeProfile
              ? AppUiSurfaces.profileHome
              : AppUiSurfaces.userProfile;
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
      query = RemoteProfileQuery(
        publicProfileQuery: userProfileQuery,
        userHomepageQuery: userProfileQuery,
      );
    });

    test('getUserProfile → GET generated persona profile path', () async {
      final profile = await query.getUserProfile('u1');

      expect(profile.personaId, 'u1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userUserAccountGetPersonaProfile,
          pathParameters: const <String, String>{'personaId': 'u1'},
        ),
      );
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: UserRequestPageIds.getPersonaProfile,
        surfaceId: AppUiSurfaces.userProfile.id,
        operationId: AppCloudOperationIds.userUserAccountGetPersonaProfile,
      );
    });
  });
}
