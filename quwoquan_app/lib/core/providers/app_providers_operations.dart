import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/application/user/persona_relationship/persona_relationship_facets.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/application/account/user_settings/blocked_keyword_writer.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/tag/tag/tag_feedback_fact/application/tag_feedback_command_writer.dart';
import 'package:quwoquan_app/cloud/remote/search/hot_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_follow_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/application/entity/homepage_review_operation_ports.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/cloud/services/integration/location_query_contracts.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_append_writer.dart';
import 'package:quwoquan_app/cloud/remote/content/profile_interaction/profile_interaction_remote.dart';
import 'package:quwoquan_app/cloud/remote/entity/homepage_review/homepage_review_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/greeting_request/greeting_request_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/recent_search_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/search_feedback_remote.dart';
import 'package:quwoquan_app/tag/tag/tag_feedback_fact/adapters/tag_feedback_fact_remote.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/platform/location/geolocator_location_gateway.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/services/blocked_keyword_snapshot_cache.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/integration_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/application/search/search_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
/// VisitRecord typed append 写面：production Remote-only（08 Mock 隔离），
/// alpha/test 经 ProviderScope override 注入替身。
final opsVisitAppendWriterProvider = Provider<OpsVisitAppendWriter>((ref) {
  return OpsProductionComposition.generatedAdapter<OpsVisitAppendWriter>(
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
});

final locationGatewayProvider = Provider<LocationGateway>((ref) {
  return const GeolocatorLocationGateway();
});

final createLocationNearbyReaderProvider = Provider<NearbyLocationReader>((
  ref,
) {
  return IntegrationProductionComposition.generatedAdapter<NearbyLocationReader>(
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
  return IntegrationProductionComposition.generatedAdapter<LocationSearchReader>(
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
  return IntegrationProductionComposition.generatedAdapter<LocationSearchReader>(
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
    Provider.family<ContentReportCommandWriter, AppUiSurface>((ref, surface) {
      return ContentProductionComposition.generatedAdapter<
        ContentReportCommandWriter
      >(
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
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.homeFeed),
      );
    });

final workBrowserContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.workBrowser),
      );
    });

final userProfileContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.userProfile),
      );
    });

final circleDetailContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportCommandWriterProvider(AppUiSurfaces.circleDetail),
      );
    });

final myReportsContentReportQueryProvider = Provider<ContentMyReportQueryFacet>(
  (ref) {
    return ContentProductionComposition.generatedAdapter<ContentMyReportQueryFacet>(
      ContentProductionAdapter.reportQuery,
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => _reportInvocationContext(
        ref,
        surface: AppUiSurfaces.myReports,
        clientPageId: clientPageId,
      ),
    );
  },
);

ProfileUpdateProposalCommandWriter _profileUpdateProposalCommandWriter(
  Ref ref,
  AppUiSurface surface,
) {
  return UserProductionComposition.generatedAdapter<
    ProfileUpdateProposalCommandWriter
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

ProfileUpdateProposalQueryReader _profileUpdateProposalQueryReader(
  Ref ref,
  AppUiSurface surface,
) {
  return UserProductionComposition.generatedAdapter<
    ProfileUpdateProposalQueryReader
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

SubjectFollowCommandWriter _subjectFollowCommandWriter(
  Ref ref,
  AppUiSurface surface,
) {
  return UserProductionComposition.generatedAdapter<SubjectFollowCommandWriter>(
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
    Provider<SubjectFollowCommandWriter>((ref) {
      return _subjectFollowCommandWriter(ref, AppUiSurfaces.homepageDetail);
    });

final _accountSessionCommandWriterProvider =
    Provider<AccountSessionCommandWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AccountSessionCommandWriter
      >(
        UserProductionAdapter.accountSession,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _accountSessionInvocationContext(ref, clientPageId),
      );
    });

/// AccountSession 组合装配边界；业务消费者使用下方细粒度子 Facet。
final accountSessionCommandWriterProvider =
    Provider<AccountSessionCommandWriter>((ref) {
      return ref.watch(_accountSessionCommandWriterProvider);
    });

/// 六路 public bootstrap 登录写面。
final accountSessionLoginCommandWriterProvider =
    Provider<AccountSessionLoginCommandWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AccountSessionCommandWriter
      >(
        UserProductionAdapter.accountSession,
        client: ref.watch(unauthenticatedGeneratedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _accountSessionInvocationContext(ref, clientPageId),
      );
    });

/// refresh/logout 会话生命周期写面。
final accountSessionLifecycleCommandWriterProvider =
    Provider<AccountSessionLifecycleCommandWriter>((ref) {
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
    Provider<AuthenticationChallengeCommandWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AuthenticationChallengeCommandWriter
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
    Provider<AppCredentialBindingCommandWriter>((ref) {
      return UserProductionComposition.generatedAdapter<
        AppCredentialBindingCommandWriter
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

final credentialBindingQueryProvider = Provider<CredentialBindingQuery>((ref) {
  return UserProductionComposition.generatedAdapter<CredentialBindingQuery>(
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
    Provider.family<RemotePersonaRelationshipFollowAdapter, AppUiSurface>((
      ref,
      surface,
    ) {
      return RemotePersonaRelationshipFollowAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, canonicalOperationId) {
          final operation = appCloudOperationContracts[canonicalOperationId];
          if (operation == null || !operation.surfaceIds.contains(surface.id)) {
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
    });

/// PersonaRelationship 关注/粉丝列表读面。
final personaRelationshipQueryProvider =
    Provider.family<PersonaRelationshipQuery, AppUiSurface>((ref, surface) {
      return ref.watch(_personaRelationshipFollowRemoteProvider(surface));
    });

/// PersonaRelationship 关注 set/unset 命令面。
final personaRelationshipCommandWriterProvider =
    Provider.family<PersonaRelationshipCommandWriter, AppUiSurface>((
      ref,
      surface,
    ) {
      return ref.watch(_personaRelationshipFollowRemoteProvider(surface));
    });

final _personaRemoteWriterProvider = Provider<RemotePersonaCommandWriter>((
  ref,
) {
  return RemotePersonaCommandWriter(
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
  return ref.watch(_personaRemoteWriterProvider);
});

/// 资料保存命令（PATCH /user/profile）的对象级 production 写面（编辑资料页）。
final profileCommandWriterProvider = Provider<ProfileCommandWriter>((ref) {
  return ref.watch(_personaRemoteWriterProvider);
});

/// UserSettings 通知/隐私/通话/外观设置的对象级 production 写面。
final userSettingsCommandWriterProvider = Provider<UserSettingsCommandWriter>((
  ref,
) {
  return RemoteUserSettingsCommandWriter(
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
  return RemoteUserSettingsQueryReader(
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
    Provider.family<RemotePersonaRelationshipFacet, AppUiSurface>(
      (ref, surface) => RemotePersonaRelationshipFacet(
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
      return ref.watch(personaRelationshipRemoteProvider(surface));
    });

/// 拉黑管理页私有查询面；production 只装配 Remote，alpha/test 显式 override。
final blockedListQueryProvider = Provider<BlockedListQuery>((ref) {
  return ref.watch(
    personaRelationshipRemoteProvider(AppUiSurfaces.blockedUsers),
  );
});

final greetingRequestRemoteProvider =
    Provider.family<RemoteGreetingRequestFacet, AppUiSurface>(
      (ref, surface) => RemoteGreetingRequestFacet(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      ),
    );

final _homepageReviewRemoteProvider =
    Provider.family<RemoteHomepageReviewFacet, AppUiSurface>(
      (ref, surface) => RemoteHomepageReviewFacet(
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
      return ref.watch(
        _homepageReviewRemoteProvider(AppUiSurfaces.homepageDetail),
      );
    });

/// 实体主页详情页的评价查询（列表分页 + 我的评价预填）。
final homepageReviewQueryProvider = Provider<HomepageReviewQuery>((ref) {
  return ref.watch(_homepageReviewRemoteProvider(AppUiSurfaces.homepageDetail));
});

final profileEditProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalCommandWriter>((ref) {
      return _profileUpdateProposalCommandWriter(
        ref,
        AppUiSurfaces.profileEdit,
      );
    });

final profileEditProposalQueryReaderProvider =
    Provider<ProfileUpdateProposalQueryReader>((ref) {
      return _profileUpdateProposalQueryReader(ref, AppUiSurfaces.profileEdit);
    });

final assistantProfileProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalCommandWriter>((ref) {
      return _profileUpdateProposalCommandWriter(
        ref,
        AppUiSurfaces.personalAssistantDialog,
      );
    });

final _profileInteractionRemoteAdapterProvider =
    Provider<RemoteProfileInteractionAdapter>((ref) {
      return RemoteProfileInteractionAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) {
          if (clientPageId ==
              ContentRequestPageIds.updateProfileInteractionState) {
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
        },
      );
    });

final profileInteractionQueryFacetProvider =
    Provider<ContentProfileInteractionQueryFacet>((ref) {
      return ref.watch(_profileInteractionRemoteAdapterProvider);
    });

final profileInteractionReadFactAppendFacetProvider =
    Provider<ContentProfileInteractionReadFactAppendFacet>((ref) {
      return ref.watch(_profileInteractionRemoteAdapterProvider);
    });

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
  return RemoteSearchHotQueryReader(
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
final _recentSearchRemoteProvider = Provider<RemoteRecentSearchAdapter>((ref) {
  return RemoteRecentSearchAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchLanding,
      clientPageId: clientPageId,
    ),
  );
});

final recentSearchQueryProvider = Provider<RecentSearchQuery>((ref) {
  return ref.watch(_recentSearchRemoteProvider);
});

final recentSearchCommandWriterProvider = Provider<RecentSearchCommandWriter>((
  ref,
) {
  return ref.watch(_recentSearchRemoteProvider);
});

/// SearchFeedbackFact typed append 写面：搜索结果页 click/impression 归因上报。
final searchFeedbackCommandWriterProvider =
    Provider<SearchFeedbackCommandWriter>((ref) {
      return RemoteSearchFeedbackAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: AppUiSurfaces.globalSearchNetworkResults,
          clientPageId: clientPageId,
        ),
      );
    });

/// TagFeedbackFact typed append 写面：标签编辑页添加/移除动作产出反馈事实。
final tagFeedbackCommandWriterProvider = Provider<TagFeedbackCommandWriter>((
  ref,
) {
  return RemoteTagFeedbackAdapter(
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
