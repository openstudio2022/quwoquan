import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/author_impact_query.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/relationship/subject_follow/application/public/subject_follow_writer.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_edit_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/application/public/profile_update_proposal_ports.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/account_session_ports.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/application/public/credential_binding_ports.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/application/blocked_keyword_writer.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/application/tag_feedback_fact_appender.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/application/public/homepage_review_operation_ports.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_location_coordinator.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/location_query_contracts.dart';
import 'package:quwoquan_app/runtime/observability/visit/visit_append_port.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/platform/location/geolocator_location_gateway.dart';
import 'package:quwoquan_app/runtime/platform/location/location_gateway.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/application/blocked_keyword_snapshot_cache.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/di/integration_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_dependencies.dart';
import 'package:quwoquan_app/runtime/di/search_dependencies.dart';
import 'package:quwoquan_app/runtime/di/tag_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/runtime/di/visit_record_dependencies.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/visit_record/application/public/visit_record_writer.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/recent_search_ports.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/search_recent_history_store.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_history_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/application/public/search_feedback_fact_appender.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';

/// VisitRecord typed append 写面：production Remote-only（08 Mock 隔离），
/// alpha/test 经 ProviderScope override 注入替身。
final opsVisitAppendWriterProvider = Provider<VisitAppendPort>((ref) {
  final writer = OpsProductionComposition.generatedAdapter<VisitRecordWriter>(
    OpsProductionAdapter.visitAppend,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (String clientPageId, {required String idempotencyKey}) =>
            locationInvocationContext(
              ref,
              surface: AppUiSurfaces.appShell,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
  return VisitRecordAppendBridge(writer);
});

final locationGatewayProvider = Provider<LocationGateway>((ref) {
  return const GeolocatorLocationGateway();
});

final createLocationNearbyReaderProvider = Provider<NearbyLocationReader>((
  ref,
) {
  return IntegrationProductionComposition.generatedAdapter<
    NearbyLocationReader
  >(
    IntegrationProductionAdapter.locationQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => locationInvocationContext(
      ref,
      surface: AppUiSurfaces.createWorkspace,
      clientPageId: clientPageId,
    ),
  );
});

final createLocationSearchReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return IntegrationProductionComposition.generatedAdapter<
    LocationSearchReader
  >(
    IntegrationProductionAdapter.locationQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => locationInvocationContext(
      ref,
      surface: AppUiSurfaces.createWorkspace,
      clientPageId: clientPageId,
    ),
  );
});

final globalSearchLocationReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return IntegrationProductionComposition.generatedAdapter<
    LocationSearchReader
  >(
    IntegrationProductionAdapter.locationQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => locationInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchNetworkResults,
      clientPageId: clientPageId,
    ),
  );
});

final createLocationCoordinatorProvider = Provider<CreateLocationCoordinator>((
  ref,
) {
  return CreateLocationCoordinator(
    nearbyReader: ref.watch(createLocationNearbyReaderProvider),
    searchReader: ref.watch(createLocationSearchReaderProvider),
    locationGateway: ref.watch(locationGatewayProvider),
  );
});

final _contentReportCommandWriterProvider =
    Provider.family<ContentReportWriter, AppUiSurface>((ref, surface) {
      return ContentProductionComposition.generatedAdapter<ContentReportWriter>(
        ContentProductionAdapter.reportCommand,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      );
    });

final homeFeedContentReportCommandWriterProvider =
    Provider<ContentReportWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.homeFeed),
      );
    });

final workBrowserContentReportCommandWriterProvider =
    Provider<ContentReportWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.workBrowser),
      );
    });

final userProfileContentReportCommandWriterProvider =
    Provider<ContentReportWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.userProfile),
      );
    });

final circleDetailContentReportCommandWriterProvider =
    Provider<ContentReportWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.circleDetail),
      );
    });

final myReportsContentReportQueryProvider = Provider<ContentMyReportsReader>((
  ref,
) {
  return ContentProductionComposition.generatedAdapter<ContentMyReportsReader>(
    ContentProductionAdapter.reportQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.myReports,
      clientPageId: clientPageId,
    ),
  );
});

ProfileUpdateProposalWriter _profileUpdateProposalCommandWriter(
  Ref ref,
  AppUiSurface surface,
) {
  return UserProductionComposition.generatedAdapter<
    ProfileUpdateProposalWriter
  >(
    UserProductionAdapter.profileUpdateProposal,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _profileUpdateProposalInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

ProfileUpdateProposalReader _profileUpdateProposalQueryReader(
  Ref ref,
  AppUiSurface surface,
) {
  return UserProductionComposition.generatedAdapter<
    ProfileUpdateProposalReader
  >(
    UserProductionAdapter.profileUpdateProposal,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _profileUpdateProposalInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

SubjectFollowWriter _subjectFollowCommandWriter(Ref ref, AppUiSurface surface) {
  return UserProductionComposition.generatedAdapter<SubjectFollowWriter>(
    UserProductionAdapter.subjectFollow,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: surface,
      clientPageId: clientPageId,
    ),
  );
}

/// 实体主页详情页的关注写入口；关注关系唯一归属 user.SubjectFollow 聚合。
final homepageSubjectFollowCommandWriterProvider =
    Provider<SubjectFollowWriter>((ref) {
      return _subjectFollowCommandWriter(ref, AppUiSurfaces.homepageDetail);
    });

final _accountSessionCommandWriterProvider = Provider<AccountSessionWriter>((
  ref,
) {
  return UserProductionComposition.generatedAdapter<AccountSessionWriter>(
    UserProductionAdapter.accountSession,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) =>
        _accountSessionInvocationContext(ref, clientPageId),
  );
});

/// AccountSession 组合装配边界；业务消费者使用下方细粒度子 Facet。
final accountSessionCommandWriterProvider = Provider<AccountSessionWriter>((
  ref,
) {
  return ref.watch(_accountSessionCommandWriterProvider);
});

/// 六路 public bootstrap 登录写面。
final accountSessionLoginCommandWriterProvider =
    Provider<AccountSessionLoginWriter>((ref) {
      return UserProductionComposition.generatedAdapter<AccountSessionWriter>(
        UserProductionAdapter.accountSession,
        client: ref.watch(unauthenticatedGeneratedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _accountSessionInvocationContext(ref, clientPageId),
      );
    });

/// refresh/logout 会话生命周期写面。
final accountSessionLifecycleCommandWriterProvider =
    Provider<AccountSessionLifecycleWriter>((ref) {
      return ref.watch(accountSessionCommandWriterProvider);
    });

/// UserAccount 生命周期终态写面（CloseAccount，Apple 5.1.1(v) 注销）。
/// production Remote-only；alpha/test 经 ProviderScope override 注入替身。
final accountLifecycleCommandWriterProvider =
    Provider<AccountLifecycleCommandWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AccountLifecycleCommandWriter
      >(
        UserProductionAdapter.accountLifecycle,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: AppUiSurfaces.settingsAccountSecurity,
          clientPageId: clientPageId,
        ),
      );
    });

/// AuthenticationChallenge OTP/一键/支付宝授权的对象级 production 写面。
final authenticationChallengeCommandWriterProvider =
    Provider<AuthenticationChallengeWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AuthenticationChallengeWriter
      >(
        UserProductionAdapter.authenticationChallenge,
        client: ref.watch(unauthenticatedGeneratedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: AppUiSurfaces.login,
          clientPageId: clientPageId,
        ),
      );
    });

CloudOperationInvocationContext _accountSessionInvocationContext(
  Ref ref,
  String clientPageId,
) {
  final surface =
      clientPageId == UserRequestPageIds.loginAnonymous ||
          clientPageId == UserRequestPageIds.refreshToken
      ? AppUiSurfaces.appShell
      : clientPageId == UserRequestPageIds.logout
      ? AppUiSurfaces.settingsHome
      : AppUiSurfaces.login;
  return _reportInvocationContext(
    ref,
    surface: surface,
    clientPageId: clientPageId,
  );
}

/// 登录首次绑定与设置页凭证管理共用的 CredentialBinding 商用写面。
final appCredentialBindingCommandWriterProvider =
    Provider<CredentialBindingWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        CredentialBindingWriter
      >(
        UserProductionAdapter.credentialBindingCommand,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface:
              clientPageId == UserRequestPageIds.completeFederatedPhoneBinding
              ? AppUiSurfaces.login
              : AppUiSurfaces.settingsAccountSecurity,
          clientPageId: clientPageId,
        ),
      );
    });

final credentialBindingQueryProvider = Provider<CredentialBindingReader>((ref) {
  return UserProductionComposition.generatedAdapter<CredentialBindingReader>(
    UserProductionAdapter.credentialBindingQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.settingsAccountSecurity,
      clientPageId: clientPageId,
    ),
  );
});

CloudOperationInvocationContext Function(String, String)
_userProfileInvocationContext(Ref ref, AppUiSurface surface) {
  return (clientPageId, canonicalOperationId) {
    final operation = appCloudOperationContracts[canonicalOperationId];
    if (operation == null || !operation.surfaceIds.contains(surface.id)) {
      throw StateError(
        'UserProfile operation 未绑定调用 surface: '
        '$canonicalOperationId -> ${surface.id}; '
        '允许值=${operation?.surfaceIds.join(',') ?? ''}',
      );
    }
    if (canonicalOperationId ==
        AppCloudOperationIds.userUserAccountGetActivePersonaContext) {
      final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        clientPageId: clientPageId,
        routeId: surface.routeId,
        actor: CloudOperationActorContext(
          accountId: accountId.isEmpty ? null : accountId,
        ),
      );
    }
    return locationInvocationContext(
      ref,
      surface: surface,
      clientPageId: clientPageId,
    );
  };
}

/// UserProfile 公开资料、主页聚合与统计读面。
final profileQueryProvider = Provider.family<ProfileQuery, AppUiSurface>((
  ref,
  surface,
) {
  return UserProductionComposition.generatedAdapter<ProfileQuery>(
    UserProductionAdapter.profileQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: _userProfileInvocationContext(ref, surface),
  );
});

/// Content/Post 作者影响摘要与证据读面。
final authorImpactQueryProvider =
    Provider.family<AuthorImpactQuery, AppUiSurface>((ref, surface) {
      return ContentProductionComposition.generatedAdapter<AuthorImpactQuery>(
        ContentProductionAdapter.authorImpact,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => locationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      );
    });

/// Profile 私有编辑快照与二维码读面。
final profileEditQueryProvider =
    Provider.family<ProfileEditQuery, AppUiSurface>((ref, surface) {
      return UserProductionComposition.generatedAdapter<ProfileEditQuery>(
        UserProductionAdapter.profileEditQuery,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: _userProfileInvocationContext(ref, surface),
      );
    });

/// Persona 管理投影与公开分身资料读面。
final personaQueryProvider = Provider.family<PersonaQuery, AppUiSurface>((
  ref,
  surface,
) {
  return UserProductionComposition.generatedAdapter<PersonaQuery>(
    UserProductionAdapter.personaQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: _userProfileInvocationContext(ref, surface),
  );
});

final _personaRelationshipFollowRemoteProvider =
    Provider.family<AppProductionPersonaRelationshipFollowFacets, AppUiSurface>(
      (ref, surface) {
        return UserProductionComposition.personaRelationshipFollowFacets(
          client: ref.watch(generatedCloudOperationClientProvider),
          invocationContext: (clientPageId, canonicalOperationId) {
            final operation = appCloudOperationContracts[canonicalOperationId];
            if (operation == null ||
                !operation.surfaceIds.contains(surface.id)) {
              throw StateError(
                'PersonaRelationship operation 未绑定调用 surface: '
                '$canonicalOperationId -> ${surface.id}; '
                '允许值=${operation?.surfaceIds.join(',') ?? ''}',
              );
            }
            return _reportInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
            );
          },
        );
      },
    );

/// PersonaRelationship 关注/粉丝列表读面。
final personaRelationshipQueryProvider =
    Provider.family<PersonaRelationshipQuery, AppUiSurface>((ref, surface) {
      return ref.watch(_personaRelationshipFollowRemoteProvider(surface)).query;
    });

/// PersonaRelationship 关注 set/unset 命令面。
final personaRelationshipCommandWriterProvider =
    Provider.family<PersonaRelationshipCommandWriter, AppUiSurface>((
      ref,
      surface,
    ) {
      return ref
          .watch(_personaRelationshipFollowRemoteProvider(surface))
          .commandWriter;
    });

final _personaRemoteWriterProvider =
    Provider<AppProductionPersonaCommandFacets>((ref) {
      return UserProductionComposition.personaCommandFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: clientPageId == UserRequestPageIds.updateUserProfile
              ? AppUiSurfaces.profileEdit
              : AppUiSurfaces.profilePersonas,
          clientPageId: clientPageId,
        ),
      );
    });

/// Persona 生命周期命令的对象级 production 写面（分身管理页）。
final personaCommandWriterProvider = Provider<PersonaManagementCommandWriter>((
  ref,
) {
  return ref.watch(_personaRemoteWriterProvider).managementWriter;
});

/// 资料保存命令（PATCH /user/profile）的对象级 production 写面（编辑资料页）。
final profileCommandWriterProvider = Provider<ProfileCommandWriter>((ref) {
  return ref.watch(_personaRemoteWriterProvider).profileWriter;
});

/// UserSettings 通知/隐私/通话/外观设置的对象级 production 写面。
final userSettingsCommandWriterProvider = Provider<UserSettingsCommandWriter>((
  ref,
) {
  return UserProductionComposition.userSettingsCommandWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: switch (clientPageId) {
        UserRequestPageIds.updateNotificationSettings =>
          AppUiSurfaces.settingsNotifications,
        UserRequestPageIds.updatePrivacySettings =>
          AppUiSurfaces.settingsPrivacy,
        UserRequestPageIds.updateCallSettings => AppUiSurfaces.settingsCalls,
        UserRequestPageIds.updateAppearanceSettings =>
          AppUiSurfaces.settingsDarkMode,
        _ => AppUiSurfaces.settingsHome,
      },
      clientPageId: clientPageId,
    ),
  );
});

final userSettingsQueryReaderProvider = Provider<UserSettingsQueryReader>((
  ref,
) {
  return UserProductionComposition.userSettingsQueryReader(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: switch (clientPageId) {
        UserRequestPageIds.getNotificationSettings =>
          AppUiSurfaces.settingsNotifications,
        UserRequestPageIds.getPrivacySettings => AppUiSurfaces.settingsPrivacy,
        UserRequestPageIds.getCallSettings => AppUiSurfaces.settingsCalls,
        UserRequestPageIds.getAppearanceSettings =>
          AppUiSurfaces.settingsDarkMode,
        _ => AppUiSurfaces.settingsHome,
      },
      clientPageId: clientPageId,
    ),
  );
});

final blockedKeywordSnapshotCacheProvider =
    Provider<BlockedKeywordSnapshotCache>((ref) {
      final cache = BlockedKeywordSnapshotCache();
      ref.listen(
        authSessionControllerProvider.select(
          (state) => (state.status, state.ownerId, state.activePersonaId),
        ),
        (previous, next) {
          if (previous != null && previous != next) {
            cache.clear();
          }
        },
      );
      return cache;
    });

final blockedKeywordWriterProvider = Provider<BlockedKeywordWriter>((ref) {
  final cache = ref.watch(blockedKeywordSnapshotCacheProvider);
  return BlockedKeywordWriter(
    query: ref.watch(userSettingsQueryReaderProvider),
    commands: ref.watch(userSettingsCommandWriterProvider),
    onChanged: cache.replace,
  );
});

final personaRelationshipRemoteProvider =
    Provider.family<AppProductionPersonaRelationshipFacets, AppUiSurface>(
      (ref, surface) => UserProductionComposition.personaRelationshipFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      ),
    );

/// PersonaRelationship 拉黑写面。调用页必须传入真实 surface，保证操作归因。
final personaRelationshipBlockWriterProvider =
    Provider.family<BlockCommandWriter, AppUiSurface>((ref, surface) {
      return ref.watch(personaRelationshipRemoteProvider(surface)).blockWriter;
    });

/// 拉黑管理页私有查询面；production 只装配 Remote，alpha/test 显式 override。
final blockedListQueryProvider = Provider<BlockedListQuery>((ref) {
  return ref
      .watch(personaRelationshipRemoteProvider(AppUiSurfaces.blockedUsers))
      .blockedListQuery;
});

final greetingRequestRemoteProvider =
    Provider.family<AppProductionGreetingRequestFacets, AppUiSurface>(
      (ref, surface) => UserProductionComposition.greetingRequestFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      ),
    );

final _homepageReviewFacetsProvider =
    Provider.family<AppProductionHomepageReviewFacets, AppUiSurface>(
      (ref, surface) => EntityProductionComposition.homepageReviewFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required command}) =>
            _profileUpdateProposalInvocationContext(
              ref,
              surface: surface,
              clientPageId: clientPageId,
              command: command,
            ),
      ),
    );

/// 实体主页详情页（opinion tab / 摘要卡）的评价写入口。
final homepageReviewCommandWriterProvider =
    Provider<HomepageReviewCommandWriter>((ref) {
      return ref
          .watch(_homepageReviewFacetsProvider(AppUiSurfaces.homepageDetail))
          .commandWriter;
    });

/// 实体主页详情页的评价查询（列表分页 + 我的评价预填）。
final homepageReviewQueryProvider = Provider<HomepageReviewQuery>((ref) {
  return ref
      .watch(_homepageReviewFacetsProvider(AppUiSurfaces.homepageDetail))
      .query;
});

final profileEditProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalWriter>((ref) {
      return _profileUpdateProposalCommandWriter(
        ref,
        AppUiSurfaces.profileEdit,
      );
    });

final profileEditProposalQueryReaderProvider =
    Provider<ProfileUpdateProposalReader>((ref) {
      return _profileUpdateProposalQueryReader(ref, AppUiSurfaces.profileEdit);
    });

final assistantProfileProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalWriter>((ref) {
      return _profileUpdateProposalCommandWriter(
        ref,
        AppUiSurfaces.personalAssistantDialog,
      );
    });

final profileInteractionQueryFacetProvider =
    Provider<ContentProfileInteractionQueryFacet>((ref) {
      return ContentProductionComposition.generatedAdapter<
        ContentProfileInteractionQueryFacet
      >(
        ContentProductionAdapter.profileInteractionActivity,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _profileInteractionInvocationContext(ref, clientPageId),
      );
    });

final profileInteractionReadFactAppendFacetProvider =
    Provider<ContentProfileInteractionReadFactAppendFacet>((ref) {
      return ContentProductionComposition.generatedAdapter<
        ContentProfileInteractionReadFactAppendFacet
      >(
        ContentProductionAdapter.profileInteractionReadFact,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _profileInteractionInvocationContext(ref, clientPageId),
      );
    });

CloudOperationInvocationContext _profileInteractionInvocationContext(
  Ref ref,
  String clientPageId,
) {
  if (clientPageId == ContentRequestPageIds.appendProfileInteractionReadFact) {
    return _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.profileHome,
      clientPageId: clientPageId,
    );
  }
  return locationInvocationContext(
    ref,
    surface: AppUiSurfaces.profileHome,
    clientPageId: clientPageId,
  );
}

CloudOperationInvocationContext _profileUpdateProposalInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    idempotencyKey: command ? const Uuid().v4() : null,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

/// SearchRequestFact term-heat 榜单查询面：production 只经 generated client。
final searchHotQueryReaderProvider = Provider<SearchHotQueryReader>((ref) {
  return SearchProductionComposition.hotQueryReader(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => locationInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchLanding,
      clientPageId: clientPageId,
    ),
  );
});

/// RecentSearchState 对象级 typed Facet：production Remote-only。
/// entryId 由服务端从语义键派生；命令幂等键由 executor 注入。
final _recentSearchFacetsProvider = Provider<AppProductionRecentSearchFacets>((
  ref,
) {
  return SearchProductionComposition.recentSearchFacets(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchLanding,
      clientPageId: clientPageId,
    ),
  );
});

final recentSearchQueryProvider = Provider<RecentSearchQuery>((ref) {
  return ref.watch(_recentSearchFacetsProvider).query;
});

final recentSearchCommandWriterProvider = Provider<RecentSearchCommandWriter>((
  ref,
) {
  return ref.watch(_recentSearchFacetsProvider).commandWriter;
});

/// 最近搜索本地恢复存储只在 composition root 构造 concrete adapter。
final recentSearchHistoryStoreProvider = Provider.autoDispose
    .family<RecentSearchHistoryStore, String>((ref, actorNamespace) {
      return SearchRecentHistoryStore(actorNamespace: actorNamespace);
    });

/// SearchFeedbackFact typed append 写面：搜索结果页 click/impression 归因上报。
final searchFeedbackFactAppenderProvider = Provider<SearchFeedbackFactAppender>(
  (ref) {
    return SearchProductionComposition.feedbackFactAppender(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => _reportInvocationContext(
        ref,
        surface: AppUiSurfaces.globalSearchNetworkResults,
        clientPageId: clientPageId,
      ),
    );
  },
);

/// TagFeedbackFact typed append 写面：标签编辑页添加/移除动作产出反馈事实。
final tagFeedbackFactAppenderProvider = Provider<TagFeedbackFactAppender>((
  ref,
) {
  return TagProductionComposition.feedbackFactAppender(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.profileCareerInterests,
      clientPageId: clientPageId,
    ),
  );
});

CloudOperationInvocationContext _reportInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    idempotencyKey: const Uuid().v4(),
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

CloudOperationInvocationContext locationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    idempotencyKey: idempotencyKey,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}
