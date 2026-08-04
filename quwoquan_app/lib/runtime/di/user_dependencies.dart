import 'package:quwoquan_app/user/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_app/user/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/user/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_app/user/account/credential_binding/adapters/credential_binding_remote.dart';
import 'package:quwoquan_app/user/account/device_registration/adapters/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/user/profile_projection/following_subject/adapters/following_subject_remote.dart';
import 'package:quwoquan_app/user/persona_management/persona/adapters/persona_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_edit_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/user_profile_query_remote.dart';
import 'package:quwoquan_app/user/persona_management/profile_update_proposal/adapters/profile_update_proposal_remote.dart';
import 'package:quwoquan_app/user/relationship/subject_follow/adapters/subject_follow_remote.dart';
import 'package:quwoquan_app/user/account/user_account/adapters/user_sync_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// user domain 的 production Remote adapter 种类。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 泛型。
enum UserProductionAdapter {
  accountLifecycle,
  accountSession,
  authenticationChallenge,
  credentialBindingCommand,
  credentialBindingQuery,
  devicePushEndpoint,
  personaQuery,
  profileEditQuery,
  profileQuery,
  profileUpdateProposal,
  subjectFollow,
  userSync,
}

/// 共享同一 generated-client adapter 的对象级 FollowingSubject port。
final class AppProductionFollowingSubjectFacets {
  const AppProductionFollowingSubjectFacets({
    required this.query,
    required this.visitWriter,
  });

  final FollowingSubjectQuery query;
  final FollowedSubjectVisitCommandWriter visitWriter;
}

/// user domain 的唯一 production 装配入口。
final class UserProductionComposition {
  const UserProductionComposition._();

  static AppProductionFollowingSubjectFacets followingSubjectFacets({
    required GeneratedCloudOperationClient client,
    required FollowingSubjectInvocationContextFactory invocationContext,
  }) {
    final remote = RemoteFollowingSubjectFacet(
      client: client,
      invocationContext: invocationContext,
    );
    return AppProductionFollowingSubjectFacets(
      query: remote,
      visitWriter: remote,
    );
  }

  static T generatedAdapter<T>(
    UserProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    Object? clientContextSnapshot,
  }) {
    final dynamic context = invocationContext;
    final dynamic snapshot = clientContextSnapshot;
    final Object result = switch (adapter) {
      UserProductionAdapter.accountLifecycle =>
        RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: context,
        ),
      UserProductionAdapter.accountSession => RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: context,
      ),
      UserProductionAdapter.authenticationChallenge =>
        RemoteAuthenticationChallengeCommandWriter(
          client: client,
          invocationContext: context,
        ),
      UserProductionAdapter.credentialBindingCommand =>
        RemoteAppCredentialBindingCommandWriter(
          client: client,
          invocationContext: context,
        ),
      UserProductionAdapter.credentialBindingQuery =>
        RemoteCredentialBindingQuery(
          client: client,
          invocationContext: context,
        ),
      UserProductionAdapter.devicePushEndpoint =>
        RemoteDevicePushEndpointWriter(
          client: client,
          clientContextSnapshot: snapshot,
          invocationContext: context,
        ),
      UserProductionAdapter.personaQuery => RemotePersonaQuery(
        managementQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      UserProductionAdapter.profileEditQuery => RemoteProfileEditQuery(
        editSnapshotQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      UserProductionAdapter.profileQuery => RemoteProfileQuery(
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        userHomepageQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      UserProductionAdapter.profileUpdateProposal =>
        RemoteProfileUpdateProposalFacet(
          client: client,
          invocationContext: context,
        ),
      UserProductionAdapter.subjectFollow => RemoteSubjectFollowFacet(
        client: client,
        invocationContext: context,
      ),
      UserProductionAdapter.userSync => RemoteUserSyncRepository(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
