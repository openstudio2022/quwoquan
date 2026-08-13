import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_personalization_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_outbox_notifier.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_activity_view/application/public/skill_activity_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/application/skill_catalog_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/application/skill_subscription_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/application/skill_surface_placement_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/application/skill_user_setting_facet.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_facet_projection_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_facets.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_write_target_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_query_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_query_reader.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/application/connector_management_facet.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/integration_dependencies.dart';
import 'package:quwoquan_app/runtime/di/notification_dependencies.dart';
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';

/// 对话页唯一显式 Session/Run/Turn composition；对象 adapter 仍保持分离。
final _assistantSessionRunFacadeProvider =
    Provider<AssistantSessionRunComposition>((ref) {
      return AssistantProductionComposition.sessionRunFacade(
        client: ref.watch(generatedCloudOperationClientProvider),
        presentationCapabilities: ref.watch(
          assistantPresentationCapabilitySnapshotFactoryProvider,
        ),
        invocationContext:
            (clientPageId, {idempotencyKey, networkSurface = false}) =>
                _assistantOperationInvocationContext(
                  ref,
                  clientPageId: clientPageId,
                  idempotencyKey: idempotencyKey,
                  networkSurface: networkSurface,
                ),
      );
    });

final assistantPresentationCapabilitySnapshotFactoryProvider =
    Provider<AssistantPresentationCapabilitySnapshotFactory>((ref) {
      return (surfacePolicy) =>
          _assistantPresentationCapabilities(ref, surfacePolicy);
    });

AssistantPresentationCapabilitySnapshot _assistantPresentationCapabilities(
  Ref ref,
  AssistantPresentationSurfacePolicy surfacePolicy,
) {
  final appearance = ref.read(appearanceSnapshotProvider);
  final viewportWidth = appearance.responsiveState.size.width;
  if (!viewportWidth.isFinite || viewportWidth <= 0) {
    throw StateError(
      'Assistant presentation viewport is unavailable before the App shell snapshot',
    );
  }
  final networkClass = ref.read(appTelemetryContextProvider).networkClass;
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.fromWidth(
      viewportWidth,
      compactBelow: AppSpacing.markdownCompactBreakpoint,
      expandedFrom: AppSpacing.expandedBreakpoint,
    ),
    platform: platformWireName(ref.read(platformTargetProvider)),
    darkTheme: appearance.isDark,
    textScale: appearance.textScaleFactor,
    reducedMotion: appearance.disableAnimations,
    offline: networkClass == 'none',
    // No canonical MediaAssetRef -> delivery URL resolver is wired into the
    // Assistant renderer yet, so production must not advertise media nodes.
    mediaEnabled: false,
    // The personal Assistant page owns typed preference/tool continuation
    // handlers. Global network search owns no presentation action handler.
    actionsEnabled:
        surfacePolicy == AssistantPresentationSurfacePolicy.personal,
  );
}

CloudOperationInvocationContext _assistantOperationInvocationContext(
  Ref ref, {
  required String clientPageId,
  String? idempotencyKey,
  bool networkSurface = false,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.read(currentUserIdProvider).trim();
  return CloudOperationInvocationContext(
    surfaceId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.id
        : AppUiSurfaces.personalAssistantDialog.id,
    routeId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.routeId
        : AppUiSurfaces.personalAssistantDialog.routeId,
    clientPageId: clientPageId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

CloudOperationInvocationContext _assistantSkillCenterInvocationContext(
  Ref ref, {
  required String clientPageId,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.read(currentUserIdProvider).trim();
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.assistantSkills.id,
    routeId: AppUiSurfaces.assistantSkills.routeId,
    clientPageId: clientPageId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

/// Production composition is Remote-only. Alpha/test adapters must override
/// these Facets from their physically separate composition root.
final assistantSessionRunFacetProvider = Provider<AssistantSessionRunFacade>(
  (ref) => ref.watch(_assistantSessionRunFacadeProvider),
);

final assistantRunControlFacetProvider = Provider<AssistantRunControlFacet>(
  (ref) => ref.watch(_assistantSessionRunFacadeProvider),
);

final assistantSkillSubscriptionFacetProvider =
    Provider<AssistantSkillSubscriptionFacet>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            AssistantSkillSubscriptionFacet
          >(
            AssistantProductionAdapter.skillSubscription,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {String? idempotencyKey}) =>
                    _assistantSkillCenterInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final assistantSkillCatalogFacetProvider = Provider<AssistantSkillCatalogFacet>(
  (ref) =>
      AssistantProductionComposition.generatedAdapter<
        AssistantSkillCatalogFacet
      >(
        AssistantProductionAdapter.skillCatalog,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (String clientPageId) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
            ),
      ),
);

final assistantSkillUserSettingFacetProvider =
    Provider<AssistantSkillUserSettingFacet>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            AssistantSkillUserSettingFacet
          >(
            AssistantProductionAdapter.skillUserSetting,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {String? idempotencyKey}) =>
                    _assistantSkillCenterInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final assistantSkillSurfacePlacementFacetProvider =
    Provider<AssistantSkillSurfacePlacementFacet>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            AssistantSkillSurfacePlacementFacet
          >(
            AssistantProductionAdapter.skillSurfacePlacement,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {String? idempotencyKey}) =>
                    _assistantSkillCenterInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final assistantSkillConsentFacetProvider = Provider<AssistantSkillConsentFacet>(
  (ref) => AssistantProductionComposition.skillConsentFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    accountId: ref.watch(resolvedOwnerUserIdProvider).trim(),
    invocationContext: (String clientPageId, {String? idempotencyKey}) =>
        _assistantSkillCenterInvocationContext(
          ref,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
        ),
  ),
);

final assistantSkillActivityQueryProvider =
    Provider<AssistantSkillActivityQuery>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            AssistantSkillActivityQuery
          >(
            AssistantProductionAdapter.skillActivity,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext: (String clientPageId) =>
                _assistantSkillCenterInvocationContext(
                  ref,
                  clientPageId: clientPageId,
                ),
          ),
    );

final skillDataControlProcessCommandWriterProvider =
    Provider<SkillDataControlProcessCommandWriter>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            SkillDataControlProcessCommandWriter
          >(
            AssistantProductionAdapter.skillDataControl,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {String? idempotencyKey}) =>
                    _assistantSkillCenterInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final skillDataControlProcessQueryProvider =
    Provider<SkillDataControlProcessQuery>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            SkillDataControlProcessQuery
          >(
            AssistantProductionAdapter.skillDataControl,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {String? idempotencyKey}) =>
                    _assistantSkillCenterInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final assistantConnectorManagementFacetProvider =
    Provider<ConnectorManagementFacet>((ref) {
      return IntegrationProductionComposition.generatedAdapter<
        ConnectorManagementFacet
      >(
        IntegrationProductionAdapter.connectorManagement,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (String clientPageId, {String? idempotencyKey}) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

final assistantLearningFactAppendFacetProvider =
    Provider<AssistantLearningFactAppendFacet>(
      (ref) =>
          AssistantProductionComposition.generatedAdapter<
            AssistantLearningFactAppendFacet
          >(
            AssistantProductionAdapter.learningFactAppend,
            client: ref.watch(generatedCloudOperationClientProvider),
            invocationContext:
                (String clientPageId, {required String idempotencyKey}) =>
                    _assistantOperationInvocationContext(
                      ref,
                      clientPageId: clientPageId,
                      idempotencyKey: idempotencyKey,
                    ),
          ),
    );

final assistantLearningFactOutboxEnvironmentProvider = Provider<String>(
  (_) => CloudRuntimeConfig.appRuntimeEnv,
);

final assistantLearningFactOutboxProvider =
    NotifierProvider<AssistantLearningFactOutboxNotifier, int>(
      AssistantLearningFactOutboxNotifier.new,
    );

final assistantPersonalizationFacetProvider =
    Provider<AssistantPersonalizationFacade>(
      (ref) => AssistantProductionComposition.personalizationFacade(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext:
            (clientPageId, {idempotencyKey, networkSurface = false}) =>
                _assistantOperationInvocationContext(
                  ref,
                  clientPageId: clientPageId,
                  idempotencyKey: idempotencyKey,
                  networkSurface: networkSurface,
                ),
      ),
    );

final assistantTaskQueryProvider = Provider<AssistantTaskQuery>(
  (ref) => AssistantProductionComposition.taskQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (clientPageId, {idempotencyKey, networkSurface = false}) =>
            _assistantOperationInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              networkSurface: networkSurface,
            ),
  ),
);

final assistantPreferenceFacetProvider = Provider<AssistantPreferenceFacet>(
  (ref) => AssistantProductionComposition.preferenceFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (clientPageId, {idempotencyKey, networkSurface = false}) =>
            _assistantOperationInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              networkSurface: networkSurface,
            ),
  ),
);

final assistantSearchRunFacetProvider = Provider<AssistantSearchRunFacade>(
  (ref) => AssistantProductionComposition.searchRunFacade(
    client: ref.watch(generatedCloudOperationClientProvider),
    presentationCapabilities: ref.watch(
      assistantPresentationCapabilitySnapshotFactoryProvider,
    ),
    invocationContext:
        (clientPageId, {idempotencyKey, networkSurface = false}) =>
            _assistantOperationInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              networkSurface: networkSurface,
            ),
  ),
);

final assistantCreationRunFacetProvider =
    Provider<AssistantCreationRunProcessCommandWriter>(
      (ref) => ref.watch(_assistantSessionRunFacadeProvider),
    );

final _remoteAppMessageAdapterProvider =
    Provider<AppProductionAppMessageFacets>((ref) {
      return NotificationProductionComposition.appMessageFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _notificationInvocationContext(ref, clientPageId: clientPageId),
      );
    });

/// Production composition is Remote-only. Alpha/test adapters must override
/// these Facets from their physically separate composition root.
final appMessageQueryProvider = Provider<AppMessageQuery>(
  (ref) => ref.watch(_remoteAppMessageAdapterProvider).query,
);

final appMessageCommandWriterProvider = Provider<AppMessageCommandWriter>(
  (ref) => ref.watch(_remoteAppMessageAdapterProvider).commandWriter,
);

CloudOperationInvocationContext _notificationInvocationContext(
  Ref ref, {
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  // AppMessage inbox 的宿主面是消息页通知维度（chatList surface）；
  // metadata ui_surfaces.yaml 已绑定对应 operation。
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.chatList.id,
    clientPageId: clientPageId,
    routeId: AppUiSurfaces.chatList.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

final cacheTelemetrySinkProvider = Provider<CacheTelemetrySink>((ref) {
  return _AppCacheTelemetrySink(ref.watch(appTelemetryReporterProvider));
});

class _AppCacheTelemetrySink implements CacheTelemetrySink {
  const _AppCacheTelemetrySink(this._telemetry);

  final AppTelemetryRecorder _telemetry;

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    if (eventName == 'cache.hit.source') {
      final source = (attributes['source'] ?? '').toString().trim();
      final cacheClass = (attributes['cacheClass'] ?? '').toString().trim();
      unawaited(
        _telemetry.record(
          AppTelemetryPayload.homeFeedCacheReadOutcome(
            cacheSource: AppTelemetryValueCacheSource.values.contains(source)
                ? source
                : AppTelemetryValueCacheSource.unknown,
            cacheClass: cacheClass.isEmpty ? 'unknown' : cacheClass,
            result: 'hit',
            surfaceId: 'home_feed',
          ),
        ),
      );
    }
    final traceStore = AppTraceContextStore.instance;
    unawaited(
      AppLogService.instance.writeEvent(
        logType: AppLogType.perf,
        level: AppLogLevel.info,
        context: AppLogContext(
          sessionId: traceStore.sessionId,
          requestId: traceStore.newRequestId(),
          sourceDomain: 'runtime',
          component: 'local_cache',
          target: 'cache',
          action: eventName,
        ),
        payload: <String, dynamic>{
          'kind': eventName,
          ...attributes.map((key, value) => MapEntry(key, value)),
        },
        summaryPayload: <String, dynamic>{
          'kind': eventName,
          ...attributes.map((key, value) => MapEntry(key, value)),
        },
      ),
    );
  }
}

/// Homepage facet bundle 只在 composition root 聚合同一 Remote 实例。
/// 页面只能注入下方的窄 Query / CommandWriter capability。
final _homepageFacetProjectionAdapterProvider =
    Provider<HomepageFacetProjectionAdapter>((ref) {
      final commandFacets = ref.watch(_homepageCommandFacetsProvider);
      return HomepageFacetProjectionAdapter(
        query: ref.watch(homepageQueryAdapterProvider),
        candidateWriter: commandFacets.candidateWriter,
      );
    });

final homepageFacetSetProvider = Provider<HomepageFacetSet>(
  (ref) => ref.watch(_homepageFacetProjectionAdapterProvider),
);

final homepageQueryProvider = Provider<HomepageQuery>(
  (ref) => ref.watch(homepageFacetSetProvider),
);

final homepageCommandWriterProvider = Provider<HomepageCommandWriter>(
  (ref) => ref.watch(homepageFacetSetProvider),
);

final homepageWriteTargetReaderProvider = Provider<HomepageWriteTargetReader>(
  (ref) => ref.watch(_homepageFacetProjectionAdapterProvider),
);

final homepageClaimRequestCommandWriterProvider =
    Provider<HomepageClaimRequestCommandWriter>(
      (ref) => ref.watch(_homepageCommandFacetsProvider).claimRequestWriter,
    );

final homepageClaimRequestQueryReaderProvider =
    Provider<HomepageClaimRequestQueryReader>(
      (ref) =>
          ref.watch(_homepageSubmissionQueryFacetsProvider).claimRequestReader,
    );

final homepageStatusReportCommandWriterProvider =
    Provider<HomepageStatusReportCommandWriter>(
      (ref) => ref.watch(_homepageCommandFacetsProvider).statusReportWriter,
    );

final homepageStatusReportQueryReaderProvider =
    Provider<HomepageStatusReportQueryReader>(
      (ref) =>
          ref.watch(_homepageSubmissionQueryFacetsProvider).statusReportReader,
    );

final homepageQueryActorContextProvider = Provider<CloudOperationActorContext>((
  ref,
) {
  final session = ref.watch(authSessionControllerProvider);
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = session.activePersonaId.trim();
  return CloudOperationActorContext(
    accountId: accountId.isEmpty ? null : accountId,
    personaId: personaId.isEmpty ? null : personaId,
  );
});

final _homepageQueryFacetsProvider = Provider<AppProductionHomepageQueryFacets>(
  (ref) {
    final actorContext = ref.watch(homepageQueryActorContextProvider);

    CloudOperationInvocationContext invocationContext(
      AppUiSurface surface,
      String clientPageId, {
      CloudOperationCancellationSignal? cancellation,
      DateTime? deadlineAt,
    }) {
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
        actor: actorContext,
      );
    }

    return EntityProductionComposition.homepageQueryFacets(
      client: ref.watch(generatedCloudOperationClientProvider),
      detailInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
          invocationContext(
            AppUiSurfaces.homepageDetail,
            clientPageId,
            cancellation: cancellation,
            deadlineAt: deadlineAt,
          ),
      introductionInvocationContext:
          (clientPageId, {cancellation, deadlineAt}) => invocationContext(
            AppUiSurfaces.homepageIntroduction,
            clientPageId,
            cancellation: cancellation,
            deadlineAt: deadlineAt,
          ),
      searchInvocationContext: (clientPageId, {cancellation, deadlineAt}) =>
          invocationContext(
            AppUiSurfaces.homepagePicker,
            clientPageId,
            cancellation: cancellation,
            deadlineAt: deadlineAt,
          ),
    );
  },
);

final homepageQueryAdapterProvider = Provider<HomepageQueryFacet>((ref) {
  return ref.watch(_homepageQueryFacetsProvider).query;
});

final homepageIntroductionQueryProvider = Provider<HomepageIntroductionQuery>((
  ref,
) {
  return ref.watch(_homepageQueryFacetsProvider).introduction;
});

/// production 命令写面只绑定 generated Remote adapter；不含 fixture 回退。
final _homepageCommandFacetsProvider =
    Provider<AppProductionHomepageCommandFacets>((ref) {
      final actorContext = ref.watch(homepageQueryActorContextProvider);
      CloudOperationInvocationContext commandInvocationContext(
        String clientPageId,
        AppUiSurface surface, {
        String? idempotencyKey,
      }) => CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        idempotencyKey: idempotencyKey ?? const Uuid().v4(),
        actor: actorContext,
      );
      return EntityProductionComposition.homepageCommandFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, surface) =>
            commandInvocationContext(clientPageId, surface),
        claimRequestInvocationContext: commandInvocationContext,
        statusReportInvocationContext: commandInvocationContext,
      );
    });

final _homepageSubmissionQueryFacetsProvider =
    Provider<AppProductionHomepageSubmissionQueryFacets>((ref) {
      final actorContext = ref.watch(homepageQueryActorContextProvider);
      CloudOperationInvocationContext queryInvocationContext(
        String clientPageId,
        AppUiSurface surface, {
        String? idempotencyKey,
      }) => CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        actor: actorContext,
      );
      return EntityProductionComposition.homepageSubmissionQueryFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        claimRequestInvocationContext: queryInvocationContext,
        statusReportInvocationContext: queryInvocationContext,
      );
    });
