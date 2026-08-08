import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/adapters/credential_binding_remote.dart';
import 'package:quwoquan_app/service/user_service/account/device_registration/adapters/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/adapters/following_subject_remote.dart';
import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/application/public/following_subject_reader.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_query_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_edit_query_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/adapters/user_settings_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/adapters/followed_subject_visit_state_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/application/public/followed_subject_visit_state_writer.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/relationship_capability_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/adapters/profile_update_proposal_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/adapters/greeting_request_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_discovery_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_follow_remote.dart'
    as follow_remote;
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_remote.dart'
    as relationship_remote;
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/relationship/subject_follow/adapters/subject_follow_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_sync_remote.dart';
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

final class AppProductionPersonaRelationshipFollowFacets {
  const AppProductionPersonaRelationshipFollowFacets({
    required this.query,
    required this.commandWriter,
  });

  final PersonaRelationshipQuery query;
  final PersonaRelationshipCommandWriter commandWriter;
}

final class AppProductionPersonaCommandFacets {
  const AppProductionPersonaCommandFacets({
    required this.managementWriter,
    required this.profileWriter,
  });

  final PersonaManagementCommandWriter managementWriter;
  final ProfileCommandWriter profileWriter;
}

final class AppProductionPersonaRelationshipFacets {
  const AppProductionPersonaRelationshipFacets({
    required this.blockWriter,
    required this.blockedListQuery,
    required this.capabilityQuery,
  });

  final BlockCommandWriter blockWriter;
  final BlockedListQuery blockedListQuery;
  final RelationshipCapabilityQuery capabilityQuery;
}

final class AppProductionGreetingRequestFacets {
  const AppProductionGreetingRequestFacets({
    required this.commandWriter,
    required this.query,
  });

  final GreetingRequestCommandWriter commandWriter;
  final GreetingRequestQuery query;
}

/// user domain 的唯一 production 装配入口。
final class UserProductionComposition {
  const UserProductionComposition._();

  static FollowingSubjectReader followingSubjectReader({
    required GeneratedCloudOperationClient client,
    required FollowingSubjectInvocationContextFactory invocationContext,
  }) {
    return RemoteFollowingSubjectReader(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static FollowedSubjectVisitStateWriter followedSubjectVisitStateWriter({
    required GeneratedCloudOperationClient client,
    required FollowedSubjectVisitStateInvocationContextFactory
    invocationContext,
  }) {
    return RemoteFollowedSubjectVisitStateWriter(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static AppProductionPersonaRelationshipFollowFacets
  personaRelationshipFollowFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final remote = follow_remote.RemotePersonaRelationshipFollowAdapter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    return AppProductionPersonaRelationshipFollowFacets(
      query: remote,
      commandWriter: remote,
    );
  }

  static AppProductionPersonaCommandFacets personaCommandFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final remote = RemotePersonaCommandWriter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    return AppProductionPersonaCommandFacets(
      managementWriter: remote,
      profileWriter: remote,
    );
  }

  static UserSettingsCommandWriter userSettingsCommandWriter({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    return RemoteUserSettingsCommandWriter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
  }

  static UserSettingsQueryReader userSettingsQueryReader({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    return RemoteUserSettingsQueryReader(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
  }

  static AppProductionPersonaRelationshipFacets personaRelationshipFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final remote = relationship_remote.RemotePersonaRelationshipFacet(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    return AppProductionPersonaRelationshipFacets(
      blockWriter: remote,
      blockedListQuery: remote,
      capabilityQuery: remote,
    );
  }

  static AppProductionGreetingRequestFacets greetingRequestFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
  }) {
    final remote = RemoteGreetingRequestFacet(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    return AppProductionGreetingRequestFacets(
      commandWriter: remote,
      query: remote,
    );
  }

  static ContactDiscoveryRepository contactDiscoveryRepository({
    required GeneratedCloudOperationClient client,
    required ContactDiscoveryInvocationContextFactory invocationContext,
    required ContactDiscoveryIdempotencyKeyFactory idempotencyKeyFactory,
  }) {
    final remote = RemoteContactDiscoveryFacet(
      client: client,
      invocationContext: invocationContext,
    );
    return RemoteContactDiscoveryRepository(
      commandWriter: remote,
      query: remote,
      idempotencyKeyFactory: idempotencyKeyFactory,
    );
  }

  static RelationshipCapabilityRepository relationshipCapabilityRepository({
    required RelationshipCapabilityQuery query,
  }) {
    return RemoteRelationshipCapabilityRepository(query: query);
  }

  static GreetingRepository greetingRepository({
    required AppProductionGreetingRequestFacets facets,
  }) {
    return RemoteGreetingRepository(
      commandWriter: facets.commandWriter,
      query: facets.query,
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
