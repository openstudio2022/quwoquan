import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/presentation/assistant_preferences_provider.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'assistant_management_preference_flow.dart';

/// 私人助理管理页
///
/// 显式助手偏好与 Skill Center 入口均消费真实云端能力。
/// Skill 授权由 Skill Center 按 active package 目录声明的
/// requiredConsentScopes 统一管理，此页不维护按 Skill ID 特判的权限开关。
class AssistantManagementPage extends ConsumerStatefulWidget {
  const AssistantManagementPage({super.key, required this.onBack});

  final VoidCallback onBack;

  @override
  ConsumerState<AssistantManagementPage> createState() =>
      _AssistantManagementPageState();
}

class _AssistantManagementPageState
    extends ConsumerState<AssistantManagementPage>
    with _AssistantManagementPreferenceFlow {
  @override
  void initState() {
    super.initState();
    unawaited(_readAssistantPreferences());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      // 页面曝光（R20）：GoRoute 无 name 不经 pageAccess observer，页面自身
      // 直调现行 pageAccess 通道。
      unawaited(
        writeAppPageAccessOpen(
          location: AppRoutePaths.assistantManagement,
          pageVisitId: AppTraceContextStore.instance.newPageVisitId(),
          visitRecorder: ref.read(visitRecorderServiceProvider),
          telemetryReporter: ref.read(appTelemetryReporterProvider),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: AppConceptConstants.assistantManagementTitle,
      onBack: widget.onBack,
      body: SingleChildScrollView(
        padding: EdgeInsets.only(
          left: SettingsSemanticConstants.insetFormListHorizontalPadding,
          right: SettingsSemanticConstants.insetFormListHorizontalPadding,
          top: AppSpacing.intraGroupSm,
          bottom: AppSpacing.xl,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SettingsInsetGroupedSection(
              isDark: isDark,
              header: AssistantText.assistantMemorySectionTitle,
              child: _buildPreferencesSection(
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupXl),
            SettingsInsetGroupedSection(
              isDark: isDark,
              header: AssistantText.assistantSupportingCapabilities,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () => context.push(AppRoutePaths.assistantSkills),
                child: Row(
                  children: [
                    Icon(
                      CupertinoIcons.square_grid_2x2,
                      color: fgPrimary,
                      size: AppSpacing.twenty,
                    ),
                    SizedBox(width: AppSpacing.interGroupSm),
                    Expanded(
                      child: Text(
                        AssistantText.assistantSkillCenter,
                        textAlign: TextAlign.left,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          fontWeight: FontWeight.w700,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                    Icon(CupertinoIcons.chevron_forward, color: fgSecondary),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPreferencesSection({
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.interGroupSm,
            AppSpacing.md,
            AppSpacing.intraGroupSm,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AssistantText.assistantPreferenceDefaultsTitle,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: FontWeight.w700,
                  color: fgPrimary,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Wrap(
                spacing: AppSpacing.intraGroupSm,
                runSpacing: AppSpacing.intraGroupSm,
                children: [
                  _preferenceChoiceButton(
                    AssistantText.assistantPreferenceConcise,
                    AssistantPreferenceKind.replyLength,
                    'concise',
                  ),
                  _preferenceChoiceButton(
                    AssistantText.assistantPreferenceDetailed,
                    AssistantPreferenceKind.replyLength,
                    'detailed',
                  ),
                  _preferenceChoiceButton(
                    AssistantText.assistantPreferenceCasual,
                    AssistantPreferenceKind.tone,
                    'casual',
                  ),
                  _preferenceChoiceButton(
                    AssistantText.assistantPreferenceDeepThink,
                    AssistantPreferenceKind.responseStyle,
                    'deep_think',
                  ),
                ],
              ),
            ],
          ),
        ),
        if (_preferenceMutationError != null)
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AppSectionErrorCard(
                margin: EdgeInsets.all(AppSpacing.md),
                semantic: _preferenceMutationErrorSemantic(
                  _preferenceMutationError!,
                ),
                onAction: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    await _retryPendingPreferenceMutation();
                  }
                },
              ),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                child: CupertinoButton(
                  key: const ValueKey<String>(
                    'assistant_preference_reread_after_failure',
                  ),
                  onPressed:
                      _preferenceReadInFlight || _preferenceMutationInFlight
                      ? null
                      : _readAssistantPreferences,
                  child: Text(SearchText.reload),
                ),
              ),
            ],
          ),
        if (_preferenceReadError != null)
          AppSectionErrorCard(
            margin: EdgeInsets.all(AppSpacing.md),
            semantic: _preferenceLoadErrorSemantic(_preferenceReadError!),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await _readAssistantPreferences();
              }
            },
          ),
        if (_preferenceMutationInFlight ||
            (_preferenceReadInFlight && _lastConfirmedPreferences != null))
          Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: AppRequestFeedback.section(),
          ),
        _buildPreferencesBody(fgPrimary: fgPrimary, fgSecondary: fgSecondary),
      ],
    );
  }

  Widget _buildPreferencesBody({
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    final confirmed = _lastConfirmedPreferences;
    if (confirmed != null) {
      return _buildConfirmedPreferences(
        confirmed,
        fgPrimary: fgPrimary,
        fgSecondary: fgSecondary,
      );
    }
    if (_preferenceReadInFlight) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: AppRequestFeedback.section(),
      );
    }
    return const SizedBox.shrink();
  }

  Widget _buildConfirmedPreferences(
    List<AssistantPreference> preferences, {
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    final active = preferences
        .where(
          (preference) => preference.status == AssistantPreferenceStatus.active,
        )
        .toList(growable: false);
    final revocable = preferences
        .where(_isRevocablePreference)
        .toList(growable: false);
    if (active.isEmpty && revocable.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: Text(
          AssistantText.assistantMemoryEmpty,
          style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
        ),
      );
    }
    return Column(
      children: <Widget>[
        ...revocable.map(
          (preference) => _buildRevocationUndo(
            preference,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        ),
        ...active.map(
          (preference) => _preferenceRow(
            preference,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            statusLabel: _preferenceDetail(preference),
            actionLabel: AssistantText.assistantPreferenceForget,
            onAction: () => _revokePreference(preference),
          ),
        ),
      ],
    );
  }

  UiErrorSemantic _preferenceMutationErrorSemantic(Object error) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.section,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: resolved.title,
      message: resolved.message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction: const UiErrorAction(
        type: UiErrorActionType.retry,
        label: ContentText.tryAgain,
      ),
      secondaryAction: resolved.secondaryAction,
      dismissible: false,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      copyKey: resolved.copyKey,
      recoveryAction: resolved.recoveryAction,
      presentation: UiErrorPresentation.sectionSoftCard,
      tone: resolved.tone,
      appearanceMode: resolved.appearanceMode,
      sourceRouteId: resolved.sourceRouteId,
      sourceSurfaceId: resolved.sourceSurfaceId,
      sourceOperationId: resolved.sourceOperationId,
      requestId: resolved.requestId,
      traceId: resolved.traceId,
      userRecoveryGroup: resolved.userRecoveryGroup,
    );
  }

  UiErrorSemantic _preferenceLoadErrorSemantic(Object error) {
    return ensureRetryUiErrorSemantic(
      runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.section,
      ),
    );
  }

  bool _isRevocablePreference(AssistantPreference preference) {
    if (preference.status != AssistantPreferenceStatus.revoked) return false;
    final deadline = DateTime.tryParse(
      preference.revocationDeadline?.trim() ?? '',
    );
    return deadline != null && deadline.toUtc().isAfter(DateTime.now().toUtc());
  }

  Widget _buildRevocationUndo(
    AssistantPreference preference, {
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.interGroupSm,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '${_preferenceTitle(preference)} · '
              '${AssistantText.assistantPreferenceForgot}',
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupSm),
            onPressed: _preferenceActionsBlocked
                ? null
                : () => _restorePreference(preference),
            child: Text(
              AssistantText.assistantPreferenceUndo,
              style: TextStyle(color: fgPrimary),
            ),
          ),
        ],
      ),
    );
  }

  Widget _preferenceRow(
    AssistantPreference preference, {
    required Color fgPrimary,
    required Color fgSecondary,
    required String statusLabel,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.interGroupSm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            CupertinoIcons.slider_horizontal_3,
            size: AppSpacing.iconSmall,
            color: fgSecondary,
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _preferenceTitle(preference),
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w700,
                    color: fgPrimary,
                  ),
                ),
                SizedBox(height: AppSpacing.two),
                Text(
                  statusLabel,
                  style: TextStyle(
                    fontSize: AppTypography.xsPlus,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupSm),
            onPressed: _preferenceActionsBlocked ? null : onAction,
            child: Text(actionLabel),
          ),
        ],
      ),
    );
  }

  Widget _preferenceChoiceButton(
    String label,
    AssistantPreferenceKind kind,
    String value,
  ) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.intraGroupSm,
      ),
      onPressed: _preferenceActionsBlocked
          ? null
          : () => _setLongTermPreference(kind, value),
      child: Text(label),
    );
  }

  String _preferenceTitle(AssistantPreference preference) {
    if (_requiresExplicitConfirmation(preference.kind) &&
        preference.value.trim().isNotEmpty) {
      return preference.value.trim();
    }
    return switch (preference.value.trim()) {
      'concise' => AssistantText.assistantPreferenceConcise,
      'detailed' => AssistantText.assistantPreferenceDetailed,
      'casual' => AssistantText.assistantPreferenceCasual,
      'deep_think' => AssistantText.assistantPreferenceDeepThink,
      'professional' => AssistantText.assistantPreferenceProfessional,
      'warm' => AssistantText.assistantPreferenceWarm,
      _ => AssistantText.assistantMemoryUntitled,
    };
  }

  String _preferenceDetail(AssistantPreference preference) {
    final scope = preference.scope == AssistantPreferenceScope.session
        ? AssistantText.assistantPreferenceSessionScope
        : AssistantText.assistantPreferenceLongTermScope;
    final updatedAt = _formattedPreferenceUpdatedAt(preference.updatedAt);
    return <String>[
      if (_requiresExplicitConfirmation(preference.kind))
        _confirmedPreferenceKindLabel(preference.kind),
      scope,
      _preferenceSourceLabel(preference.sourceType),
      if (updatedAt.isNotEmpty)
        context.l10n.assistantMemoryUpdatedAt(updatedAt),
    ].join(' · ');
  }

  bool _requiresExplicitConfirmation(AssistantPreferenceKind kind) {
    return switch (kind) {
      AssistantPreferenceKind.frequentLocations ||
      AssistantPreferenceKind.familyTerms ||
      AssistantPreferenceKind.dietaryRestrictions ||
      AssistantPreferenceKind.travelPreferences => true,
      _ => false,
    };
  }

  String _confirmedPreferenceKindLabel(AssistantPreferenceKind kind) {
    return switch (kind) {
      AssistantPreferenceKind.frequentLocations =>
        AssistantText.assistantMemoryFrequentLocations,
      AssistantPreferenceKind.familyTerms =>
        AssistantText.assistantMemoryFamilyTerms,
      AssistantPreferenceKind.dietaryRestrictions =>
        AssistantText.assistantMemoryDietaryRestrictions,
      AssistantPreferenceKind.travelPreferences =>
        AssistantText.assistantMemoryTravelPreferences,
      _ => AssistantText.assistantMemoryUntitled,
    };
  }

  String _preferenceSourceLabel(AssistantPreferenceSourceType sourceType) {
    return switch (sourceType) {
      AssistantPreferenceSourceType.sessionConfirmed =>
        AssistantText.assistantMemorySourceConfirmedSession,
      AssistantPreferenceSourceType.management =>
        AssistantText.assistantMemorySourceManagement,
      AssistantPreferenceSourceType.explicitRewrite =>
        AssistantText.assistantMemorySourceExplicitRewrite,
      AssistantPreferenceSourceType.unknown =>
        AssistantText.assistantMemoryUntitled,
    };
  }

  String _formattedPreferenceUpdatedAt(String? raw) {
    final normalized = raw?.trim();
    if (normalized == null || normalized.isEmpty) {
      return '';
    }
    final parsed = DateTime.tryParse(normalized);
    if (parsed == null) {
      return '';
    }
    final local = parsed.toLocal();
    return context.l10n.monthDayTemplate(local.month, local.day);
  }

  Future<void> _setLongTermPreference(
    AssistantPreferenceKind kind,
    String value,
  ) async {
    await _startPreferenceMutation(
      _SetAssistantPreferenceAttempt(kind: kind, value: value),
    );
  }

  Future<void> _revokePreference(AssistantPreference preference) async {
    await _startPreferenceMutation(
      _RevokeAssistantPreferenceAttempt(preferenceId: preference.preferenceId),
    );
  }

  Future<void> _restorePreference(AssistantPreference preference) async {
    await _startPreferenceMutation(
      _RestoreAssistantPreferenceAttempt(preferenceId: preference.preferenceId),
    );
  }
}
