part of 'app_providers.dart';

final cloudClientContextProvider = Provider<CloudClientContextProvider>((ref) {
  return const AppCloudClientContextProvider();
});

final cloudRuntimeEnvironmentProvider = Provider<CloudRuntimeEnvironment>((
  ref,
) {
  return CloudRuntimeEnvironment.fromCompileTime();
});

final generatedCloudOperationClientProvider =
    Provider<GeneratedCloudOperationClient>((ref) {
      final clientContext = ref.watch(cloudClientContextProvider);
      return buildGeneratedCloudOperationClient(
        httpClient: ref.watch(cloudHttpClientProvider),
        clientContextProvider: clientContext,
        environment: ref.watch(cloudRuntimeEnvironmentProvider),
        telemetrySink: AppCloudOperationTelemetrySink(
          clientContextProvider: clientContext,
        ),
      );
    });

/// VisitRecord typed append 写面：production Remote-only（08 Mock 隔离），
/// alpha/test 经 ProviderScope override 注入替身。
final opsVisitAppendWriterProvider = Provider<OpsVisitAppendWriter>((ref) {
  return RemoteOpsVisitAppendWriter(
    httpClient: ref.watch(cloudHttpClientProvider),
  );
});

final locationGatewayProvider = Provider<LocationGateway>((ref) {
  return const GeolocatorLocationGateway();
});

final _createLocationRemoteAdapterProvider =
    Provider<RemoteLocationQueryAdapter>((ref) {
      return RemoteLocationQueryAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _locationInvocationContext(
          ref,
          surface: AppUiSurfaces.createWorkspace,
          clientPageId: clientPageId,
        ),
      );
    });

final createLocationNearbyReaderProvider = Provider<NearbyLocationReader>((
  ref,
) {
  return ref.watch(_createLocationRemoteAdapterProvider);
});

final createLocationSearchReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return ref.watch(_createLocationRemoteAdapterProvider);
});

final globalSearchLocationReaderProvider = Provider<LocationSearchReader>((
  ref,
) {
  return RemoteLocationQueryAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _locationInvocationContext(
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

final _contentReportRemoteAdapterProvider =
    Provider.family<RemoteContentReportAdapter, AppUiSurface>((ref, surface) {
      return RemoteContentReportAdapter(
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
        _contentReportRemoteAdapterProvider(AppUiSurfaces.homeFeed),
      );
    });

final workBrowserContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.workBrowser),
      );
    });

final userProfileContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.userProfile),
      );
    });

final circleDetailContentReportCommandWriterProvider =
    Provider<ContentReportCommandWriter>((ref) {
      return ref.watch(
        _contentReportRemoteAdapterProvider(AppUiSurfaces.circleDetail),
      );
    });

final myReportsContentReportQueryProvider = Provider<ContentMyReportQueryFacet>(
  (ref) {
    return RemoteContentReportQueryAdapter(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => _reportInvocationContext(
        ref,
        surface: AppUiSurfaces.myReports,
        clientPageId: clientPageId,
      ),
    );
  },
);

final _profileUpdateProposalRemoteProvider =
    Provider.family<RemoteProfileUpdateProposalFacet, AppUiSurface>(
      (ref, surface) => RemoteProfileUpdateProposalFacet(
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

final _subjectFollowRemoteProvider =
    Provider.family<RemoteSubjectFollowFacet, AppUiSurface>(
      (ref, surface) => RemoteSubjectFollowFacet(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
      ),
    );

/// 实体主页详情页的关注写入口；关注关系唯一归属 user.SubjectFollow 聚合。
final homepageSubjectFollowCommandWriterProvider =
    Provider<SubjectFollowCommandWriter>((ref) {
      return ref.watch(
        _subjectFollowRemoteProvider(AppUiSurfaces.homepageDetail),
      );
    });

final _accountSessionRemoteProvider =
    Provider<RemoteAccountSessionCommandWriter>((ref) {
      return RemoteAccountSessionCommandWriter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) {
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
        },
      );
    });

/// AccountSession 组合装配边界；业务消费者使用下方细粒度子 Facet。
final accountSessionCommandWriterProvider =
    Provider<AccountSessionCommandWriter>((ref) {
      return ref.watch(_accountSessionRemoteProvider);
    });

/// 六路 public bootstrap 登录写面。
final accountSessionLoginCommandWriterProvider =
    Provider<AccountSessionLoginCommandWriter>((ref) {
      return ref.watch(accountSessionCommandWriterProvider);
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
      return RemoteAccountLifecycleCommandWriter(
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
      return RemoteAuthenticationChallengeCommandWriter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: AppUiSurfaces.login,
          clientPageId: clientPageId,
        ),
      );
    });

/// 设置页当前暴露的 CredentialBinding 商用写面。
final appCredentialBindingCommandWriterProvider =
    Provider<AppCredentialBindingCommandWriter>((ref) {
      return RemoteAppCredentialBindingCommandWriter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _reportInvocationContext(
          ref,
          surface: AppUiSurfaces.settingsAccountSecurity,
          clientPageId: clientPageId,
        ),
      );
    });

final credentialBindingQueryProvider = Provider<CredentialBindingQuery>((ref) {
  return RemoteCredentialBindingQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _reportInvocationContext(
      ref,
      surface: AppUiSurfaces.settingsAccountSecurity,
      clientPageId: clientPageId,
    ),
  );
});

final _userProfileQueryFacetProvider =
    Provider.family<RemoteUserProfileQueryFacet, AppUiSurface>((ref, surface) {
      return RemoteUserProfileQueryFacet(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, canonicalOperationId) {
          final operation = appCloudOperationContracts[canonicalOperationId];
          if (operation == null || !operation.surfaceIds.contains(surface.id)) {
            throw StateError(
              'UserProfile operation 未绑定调用 surface: '
              '$canonicalOperationId -> ${surface.id}; '
              '允许值=${operation?.surfaceIds.join(',') ?? ''}',
            );
          }
          if (canonicalOperationId ==
              AppCloudOperationIds.userUserProfileGetActivePersonaContext) {
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
          return _locationInvocationContext(
            ref,
            surface: surface,
            clientPageId: clientPageId,
          );
        },
      );
    });

/// UserProfile 公开资料、主页聚合与统计读面。
final profileQueryProvider = Provider.family<ProfileQuery, AppUiSurface>((
  ref,
  surface,
) {
  final userProfileQuery = ref.watch(_userProfileQueryFacetProvider(surface));
  return RemoteProfileQuery(
    publicProfileQuery: userProfileQuery,
    userHomepageQuery: userProfileQuery,
  );
});

/// Content/Post 作者影响摘要与证据读面。
final authorImpactQueryProvider = Provider<AuthorImpactQuery>((ref) {
  return RemoteAuthorImpactQuery(
    httpClient: ref.watch(cloudHttpClientProvider),
  );
});

/// Profile 私有编辑快照与二维码读面。
final profileEditQueryProvider =
    Provider.family<ProfileEditQuery, AppUiSurface>((ref, surface) {
      final userProfileQuery = ref.watch(
        _userProfileQueryFacetProvider(surface),
      );
      return RemoteProfileEditQuery(
        editSnapshotQuery: userProfileQuery,
        publicProfileQuery: userProfileQuery,
      );
    });

/// Persona 管理投影与公开分身资料读面。
final personaQueryProvider = Provider.family<PersonaQuery, AppUiSurface>((
  ref,
  surface,
) {
  final userProfileQuery = ref.watch(_userProfileQueryFacetProvider(surface));
  return RemotePersonaQuery(
    managementQuery: userProfileQuery,
    publicProfileQuery: userProfileQuery,
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
          (state) => (state.status, state.ownerId, state.activeSubAccountId),
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

final _personaRelationshipRemoteProvider =
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
      return ref.watch(_personaRelationshipRemoteProvider(surface));
    });

/// 拉黑管理页私有查询面；production 只装配 Remote，alpha/test 显式 override。
final blockedListQueryProvider = Provider<BlockedListQuery>((ref) {
  return ref.watch(
    _personaRelationshipRemoteProvider(AppUiSurfaces.blockedUsers),
  );
});

final _greetingRequestRemoteProvider =
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
      return ref.watch(
        _profileUpdateProposalRemoteProvider(AppUiSurfaces.profileEdit),
      );
    });

final profileEditProposalQueryReaderProvider =
    Provider<ProfileUpdateProposalQueryReader>((ref) {
      return ref.watch(
        _profileUpdateProposalRemoteProvider(AppUiSurfaces.profileEdit),
      );
    });

final assistantProfileProposalCommandWriterProvider =
    Provider<ProfileUpdateProposalCommandWriter>((ref) {
      return ref.watch(
        _profileUpdateProposalRemoteProvider(
          AppUiSurfaces.personalAssistantDialog,
        ),
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
          return _locationInvocationContext(
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
  final personaId = persona?.subAccountId.trim() ?? '';
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

/// SearchQuery term-heat 榜单查询面：production 只经 generated client。
final searchHotQueryReaderProvider = Provider<SearchHotQueryReader>((ref) {
  return RemoteSearchHotQueryReader(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _locationInvocationContext(
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

/// TagFeedback typed append 写面：标签编辑页添加/移除动作产出反馈事实。
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
  final personaId = persona?.subAccountId.trim() ?? '';
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

CloudOperationInvocationContext _locationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.subAccountId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}
