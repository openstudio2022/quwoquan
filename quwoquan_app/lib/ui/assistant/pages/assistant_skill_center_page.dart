import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show TimeOfDay;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/assistant/assistant/page_context/domain/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/assistant/assistant/skill_user_setting/presentation/assistant_skill_setup_schema.dart';
import 'package:quwoquan_app/assistant/assistant/skill_user_setting/presentation/assistant_skill_setup_sheet.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_lifecycle_sheet.dart';
import 'package:quwoquan_app/assistant/assistant/skill_subscription/presentation/assistant_skill_subscription_setup_sheet.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'assistant_skill_center_models.dart';
part 'assistant_skill_center_sections.dart';

// settings-canonical-exception: Skill Center 能力仪表板布局 CR-20260719-122

/// Skill Center 仪表板（能力入口与统计）
///
/// 目标：接入真实技能清单与开关，遵循 i18n 与语义 token。
class AssistantSkillCenterPage extends ConsumerStatefulWidget {
  const AssistantSkillCenterPage({
    super.key,
    required this.onBack,
    this.embedded = false,
  });

  final VoidCallback onBack;
  final bool embedded;

  @override
  ConsumerState<AssistantSkillCenterPage> createState() =>
      _AssistantSkillCenterPageState();
}

class _AssistantSkillCenterPageState
    extends ConsumerState<AssistantSkillCenterPage> {
  static const int _recentSessionPreviewLimit = 3;

  bool _updating = false;
  bool _recentSessionsExpanded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.embedded) {
        return;
      }
      // 页面曝光（R20）：与既有 skill_center_action 事件同一 pageAccess 通道。
      unawaited(
        writeAppPageAccessOpen(
          location: AppRoutePaths.assistantSkills,
          pageVisitId: AppTraceContextStore.instance.newPageVisitId(),
          visitRecorder: ref.read(visitRecorderServiceProvider),
          telemetryReporter: ref.read(appTelemetryReporterProvider),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final pageBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final blockBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final skillsAsync = ref.watch(assistantSkillCenterProvider);
    final tasksAsync = ref.watch(assistantScheduleTasksProvider);
    final sessionsAsync = ref.watch(assistantRecentSessionsProvider);
    final connectorsAsync = ref.watch(assistantConnectorCenterProvider);

    final content = Stack(
      children: [
        SafeArea(
          child: CustomScrollView(
            slivers: [
              CupertinoSliverRefreshControl(onRefresh: _refreshAllSections),
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.interGroupMd,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildTasksSection(
                        tasksAsync: tasksAsync,
                        fgPrimary: fgPrimary,
                        fgSecondary: fgSecondary,
                        blockBg: blockBg,
                      ),
                      SizedBox(height: AppSpacing.interGroupMd),
                      _buildSessionsSection(
                        l10n: l10n,
                        sessionsAsync: sessionsAsync,
                        fgPrimary: fgPrimary,
                        fgSecondary: fgSecondary,
                        blockBg: blockBg,
                      ),
                      SizedBox(height: AppSpacing.interGroupMd),
                      _buildConnectorSection(
                        connectorsAsync: connectorsAsync,
                        fgPrimary: fgPrimary,
                        fgSecondary: fgSecondary,
                        blockBg: blockBg,
                      ),
                      SizedBox(height: AppSpacing.interGroupMd),
                      skillsAsync.when(
                        loading: AppRequestFeedback.section,
                        error: (error, _) => AppSectionErrorCard(
                          margin: EdgeInsets.zero,
                          semantic: ensureRetryUiErrorSemantic(
                            runtimeErrorSemantic(
                              context,
                              error: error,
                              category: UiErrorCategory.sectionLoad,
                              scope: UiErrorScope.section,
                            ),
                          ),
                          onAction: (action) async {
                            if (action.type == UiErrorActionType.retry ||
                                action.type == UiErrorActionType.resubmit) {
                              ref.invalidate(assistantSkillCenterProvider);
                            }
                          },
                        ),
                        data: (skills) => Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildPackageSection(
                              l10n: l10n,
                              skills: skills,
                              fgPrimary: fgPrimary,
                              fgSecondary: fgSecondary,
                              blockBg: blockBg,
                            ),
                            SizedBox(height: AppSpacing.interGroupMd),
                            Text(
                              l10n.assistantSkillCenterAllSkillsTitle,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                fontWeight: AppTypography.semiBold,
                                color: fgPrimary,
                              ),
                            ),
                            SizedBox(height: AppSpacing.intraGroupSm),
                            ...skills.map(
                              (skill) => _buildSkillRow(
                                skill: skill,
                                fgPrimary: fgPrimary,
                                fgSecondary: fgSecondary,
                                blockBg: blockBg,
                              ),
                            ),
                          ],
                        ),
                      ),
                      SizedBox(height: AppSpacing.interGroupMd),
                      _buildDataControlSection(
                        fgPrimary: fgPrimary,
                        fgSecondary: fgSecondary,
                        blockBg: blockBg,
                      ),
                      SizedBox(height: AppSpacing.interGroupLg),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
        if (_updating)
          Positioned.fill(
            child: Container(
              color: CupertinoColors.black.withValues(alpha: 0.08),
              child: AppRequestFeedback.section(),
            ),
          ),
      ],
    );

    if (widget.embedded) {
      return Container(color: pageBg, child: content);
    }

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        middle: Text(
          l10n.assistantSkillCenterTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
      ),
      child: content,
    );
  }

  void _toggleRecentSessionsExpanded() {
    setState(() {
      _recentSessionsExpanded = !_recentSessionsExpanded;
    });
  }

  String _skillStatusLabel(AssistantSkillCenterItem skill) {
    if (!skill.enabled) {
      return AssistantText.assistantSkillDisabled;
    }
    if (!skill.consentGranted) {
      return AssistantText.assistantSkillConsentRequired;
    }
    return AssistantText.assistantSkillEnabled;
  }

  bool _isOngoingTask(AssistantTaskItemView task) {
    return switch (task.status.trim().toLowerCase()) {
      'done' || 'completed' || 'cancelled' || 'canceled' => false,
      _ => true,
    };
  }

  String _taskDetailLabel(AssistantTaskItemView task) {
    final description = task.description?.trim() ?? '';
    final dueAt = _formattedTaskDueAt(task.dueAt);
    return <String>[
      _taskStatusLabel(task.status),
      if (description.isNotEmpty) description,
      if (dueAt.isNotEmpty) context.l10n.assistantTaskDueAt(dueAt),
    ].join(' · ');
  }

  String _taskStatusLabel(String status) {
    return switch (status.trim().toLowerCase()) {
      'in_progress' ||
      'active' ||
      'running' => AssistantText.assistantTaskStatusInProgress,
      'done' || 'completed' => AssistantText.assistantTaskStatusCompleted,
      'cancelled' || 'canceled' => AssistantText.assistantTaskStatusCancelled,
      _ => AssistantText.assistantTaskStatusPending,
    };
  }

  String _formattedTaskDueAt(String? raw) {
    final parsed = DateTime.tryParse(raw?.trim() ?? '');
    if (parsed == null) {
      return '';
    }
    final local = parsed.toLocal();
    final date = context.l10n.monthDayTemplate(local.month, local.day);
    final time = TimeOfDay.fromDateTime(local).format(context);
    return '$date $time';
  }

  Future<void> _refreshAllSections() async {
    ref.invalidate(assistantSkillCenterProvider);
    ref.invalidate(assistantScheduleTasksProvider);
    ref.invalidate(assistantRecentSessionsProvider);
    ref.invalidate(assistantConnectorCenterProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(assistantSkillCenterProvider.future).then((_) {}),
      ref.read(assistantScheduleTasksProvider.future).then((_) {}),
      ref.read(assistantRecentSessionsProvider.future).then((_) {}),
      ref.read(assistantConnectorCenterProvider.future).then((_) {}),
    ]);
  }

  Future<void> _revokeConnectorConnection(
    ConnectorConnectionView connection,
  ) async {
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(
          AssistantText.assistantConnectorDisconnectConfirmTitle,
        ),
        content: const Text(
          AssistantText.assistantConnectorDisconnectConfirmBody,
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(context.l10n.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(AssistantText.assistantConnectorDisconnect),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) {
      return;
    }
    Object? mutationError;
    await _setUpdating(true);
    try {
      await ref
          .read(assistantConnectorManagementFacetProvider)
          .revokeConnectorConnection(
            connectionId: connection.connectionId,
            expectedRevision: connection.revision,
            idempotencyKey: const Uuid().v4(),
          );
      ref.invalidate(assistantConnectorCenterProvider);
    } catch (error) {
      mutationError = error;
      ref.invalidate(assistantConnectorCenterProvider);
    } finally {
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _showSkillMutationError(Object error) async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
    );
  }

  Future<void> _togglePackage(
    List<AssistantSkillCenterItem> skills,
    bool enabled,
  ) async {
    Object? mutationError;
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await _setExistingSkillEnabled(skill, enabled);
      }
      ref.invalidate(assistantSkillCenterProvider);
      unawaited(
        _logSkillCenterPackageToggle(
          enabled: enabled,
          skillCount: skills.length,
        ),
      );
    } catch (error) {
      ref.invalidate(assistantSkillCenterProvider);
      mutationError = error;
    } finally {
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _toggleSkill(
    AssistantSkillCenterItem skill,
    bool enabled,
  ) async {
    Object? mutationError;
    await _setUpdating(true);
    try {
      await _setExistingSkillEnabled(skill, enabled);
      ref.invalidate(assistantSkillCenterProvider);
      unawaited(
        _logSkillCenterSingleSkillToggle(
          skillId: skill.skillId,
          enabled: enabled,
        ),
      );
    } catch (error) {
      ref.invalidate(assistantSkillCenterProvider);
      mutationError = error;
    } finally {
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _setExistingSkillEnabled(
    AssistantSkillCenterItem skill,
    bool enabled,
  ) async {
    final facet = ref.read(assistantSkillUserSettingFacetProvider);
    final setting = skill.setting;
    final rawConfiguration = setting?.configurationData;
    if (rawConfiguration != null && rawConfiguration is! Map) {
      throw StateError('skill configurationData is not an object');
    }
    await facet.putSkillUserSetting(
      skillId: skill.skillId,
      status: enabled
          ? SkillUserSettingStatus.enabled
          : SkillUserSettingStatus.disabled,
      configurationData: rawConfiguration == null
          ? const <String, Object?>{}
          : Map<String, Object?>.from(rawConfiguration as Map),
      configurationSchemaDigest:
          setting?.configurationSchemaDigest ??
          skill.catalog.configurationSchemaDigest,
      memoryPolicy: setting?.memoryPolicy ?? SkillMemoryPolicy.packageDefault,
      connectorConnectionRefs:
          setting?.connectorConnectionRefs ?? const <String>[],
      expectedRevision: setting?.revision ?? 0,
      clientRequestId: const Uuid().v4(),
    );
  }

  Future<void> _toggleSubscription(
    SkillSubscriptionWire subscription,
    bool enabled,
  ) async {
    Object? mutationError;
    await _setUpdating(true);
    try {
      await ref
          .read(assistantSkillSubscriptionFacetProvider)
          .updateSkillSubscriptionStatus(
            subscriptionId: subscription.subscriptionId,
            status: enabled
                ? SkillSubscriptionStatus.active.wireName
                : SkillSubscriptionStatus.paused.wireName,
            clientRequestId: const Uuid().v4(),
          );
    } catch (error) {
      mutationError = error;
    } finally {
      // 服务端是唯一状态源；成功或失败后都重新读取当前 subscriptionId。
      ref.invalidate(assistantSkillCenterProvider);
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _createProactiveSubscription(
    AssistantSkillCenterItem skill,
  ) async {
    final setup = await showAssistantSkillSubscriptionSetupSheet(
      context: context,
      skillName: skill.catalog.displayName,
    );
    if (!mounted || setup == null) {
      return;
    }
    Object? mutationError;
    await _setUpdating(true);
    try {
      final domainId = skill.catalog.domainId.trim();
      if (domainId.isEmpty) {
        throw StateError('skill catalog domainId is unavailable');
      }
      await ref
          .read(assistantSkillSubscriptionFacetProvider)
          .createSkillSubscription(
            skillId: skill.skillId,
            domainId: domainId,
            rawText: setup.rawText,
            queries: <String>[setup.rawText],
            cron: setup.cron,
            timezone: setup.timezone,
            clientRequestId: const Uuid().v4(),
          );
      ref.invalidate(assistantSkillCenterProvider);
    } catch (error) {
      mutationError = error;
      ref.invalidate(assistantSkillCenterProvider);
    } finally {
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _toggleConsent(AssistantSkillCenterItem skill) async {
    if (skill.catalog.requiredConsentScopes.isEmpty) {
      return;
    }
    Object? mutationError;
    await _setUpdating(true);
    try {
      final facet = ref.read(assistantSkillConsentFacetProvider);
      if (skill.consentGranted) {
        await facet.revokeSkillConsent(
          skillId: skill.skillId,
          clientRequestId: const Uuid().v4(),
        );
      } else {
        await facet.grantSkillConsent(
          skillId: skill.skillId,
          grantedScopes: skill.catalog.requiredConsentScopes,
          clientRequestId: const Uuid().v4(),
        );
      }
      ref.invalidate(assistantSkillCenterProvider);
    } catch (error) {
      mutationError = error;
      ref.invalidate(assistantSkillCenterProvider);
    } finally {
      await _setUpdating(false);
    }
    if (mutationError != null) {
      await _showSkillMutationError(mutationError);
    }
  }

  Future<void> _openSkillDetail(AssistantSkillCenterItem skill) async {
    Object? loadError;
    AssistantSkillCatalogItemDetailView? detail;
    await _setUpdating(true);
    try {
      detail = await ref
          .read(assistantSkillCatalogFacetProvider)
          .getSkillCatalogItem(skillId: skill.skillId);
    } catch (error) {
      loadError = error;
    } finally {
      await _setUpdating(false);
    }
    if (!mounted) return;
    if (loadError != null || detail == null) {
      await _showSkillMutationError(
        loadError ?? StateError('skill detail unavailable'),
      );
      return;
    }
    final item = detail.item;
    if (item.skillId != skill.skillId ||
        item.releaseDigest != skill.catalog.releaseDigest) {
      ref.invalidate(assistantSkillCenterProvider);
      await _showSkillMutationError(
        StateError('skill catalog release changed while opening detail'),
      );
      return;
    }
    final detailSkill = AssistantSkillCenterItem(
      catalog: item,
      setting: skill.setting,
      subscriptions: skill.subscriptions,
      consent: skill.consent,
    );
    final rawConfiguration = skill.setting?.configurationData;
    final initialConfiguration = rawConfiguration is Map
        ? Map<String, Object?>.from(rawConfiguration)
        : const <String, Object?>{};
    final schema = AssistantSkillSetupSchema.tryParse(
      detail.configurationSchema,
      requiredFields: item.configurationRequiredFields,
    );
    await showAssistantSkillSetupSheet(
      context: context,
      title: item.displayName,
      valueDescription: item.description?.trim() ?? '',
      dataUseSummary: item.dataUseSummary,
      targetUserLabels: item.targetAudiences
          .map((label) => label.displayText)
          .toList(growable: false),
      surfaceLabels: item.surfaceKinds
          .map((label) => label.displayText)
          .toList(growable: false),
      requiredPermissionScopes: detailSkill.requiredConsentScopeLabels
          .map(
            (label) => AssistantSkillConsentScopePresentation(
              displayText: label.displayText,
              description: label.description ?? '',
              granted: detailSkill.isConsentScopeGranted(label.id),
            ),
          )
          .toList(growable: false),
      optionalPermissionScopes: detailSkill.optionalConsentScopeLabels
          .map(
            (label) => AssistantSkillConsentScopePresentation(
              displayText: label.displayText,
              description: label.description ?? '',
              granted: detailSkill.isConsentScopeGranted(label.id),
            ),
          )
          .toList(growable: false),
      schema: schema,
      initialConfiguration: initialConfiguration,
      onSave: schema == null
          ? null
          : (value) => _saveSkillConfiguration(
              skill: skill,
              catalog: item,
              configuration: value,
            ),
    );
  }

  Future<void> _openSkillLifecycle(AssistantSkillCenterItem skill) async {
    await showAssistantSkillLifecycleSheet(
      context: context,
      skillId: skill.skillId,
      skillName: skill.catalog.displayName,
      activityQuery: ref.read(assistantSkillActivityQueryProvider),
      dataControlFacet: ref.read(assistantSkillDataControlFacetProvider),
      onProductAction: (action) => unawaited(
        _logSkillLifecycleAction(skillId: skill.skillId, action: action),
      ),
    );
    if (!mounted) return;
    ref.invalidate(assistantSkillCenterProvider);
  }

  Future<void> _saveSkillConfiguration({
    required AssistantSkillCenterItem skill,
    required AssistantSkillCatalogItemView catalog,
    required Map<String, Object?> configuration,
  }) async {
    final setting = skill.setting;
    await ref
        .read(assistantSkillUserSettingFacetProvider)
        .putSkillUserSetting(
          skillId: skill.skillId,
          status: setting?.status ?? SkillUserSettingStatus.enabled,
          configurationData: configuration,
          configurationSchemaDigest: catalog.configurationSchemaDigest,
          memoryPolicy:
              setting?.memoryPolicy ?? SkillMemoryPolicy.packageDefault,
          connectorConnectionRefs:
              setting?.connectorConnectionRefs ?? const <String>[],
          expectedRevision: setting?.revision ?? 0,
          clientRequestId: const Uuid().v4(),
        );
    ref.invalidate(assistantSkillCenterProvider);
  }

  Future<void> _setUpdating(bool value) async {
    if (!mounted) return;
    setState(() => _updating = value);
  }

  Future<void> _logSkillCenterPackageToggle({
    required bool enabled,
    required int skillCount,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: <String, Object?>{
        'event': 'skill_center_action',
        'action': 'package_toggle',
        'enabled': enabled,
        'skillCount': skillCount,
      },
      summaryPayload: const <String, Object?>{
        'event': 'skill_center_action',
        'action': 'package_toggle',
      },
    );
  }

  Future<void> _logSkillCenterSingleSkillToggle({
    required String skillId,
    required bool enabled,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: <String, Object?>{
        'event': 'skill_center_action',
        'action': 'single_skill_toggle',
        'skillId': skillId,
        'enabled': enabled,
      },
      summaryPayload: const <String, Object?>{
        'event': 'skill_center_action',
        'action': 'single_skill_toggle',
      },
    );
  }

  Future<void> _logSkillLifecycleAction({
    required String skillId,
    required AssistantSkillLifecycleUiAction action,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: <String, Object?>{
        'event': 'skill_center_action',
        'action': action.name,
        'skillId': skillId,
      },
      summaryPayload: <String, Object?>{
        'event': 'skill_center_action',
        'action': action.name,
      },
    );
  }
}
