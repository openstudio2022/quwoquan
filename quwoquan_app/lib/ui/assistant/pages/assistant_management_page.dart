import 'dart:async';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

/// 私人助理管理页
///
/// 隐私权限、只读记忆列表与技能中心入口均消费真实云端能力。
/// 无后端支撑的本地假开关（性格/读聊天/位置/通知）已随 B8 阶段 3b 删除。
class AssistantManagementPage extends ConsumerStatefulWidget {
  const AssistantManagementPage({super.key, required this.onBack});

  final VoidCallback onBack;

  @override
  ConsumerState<AssistantManagementPage> createState() =>
      _AssistantManagementPageState();
}

class _AssistantManagementPageState
    extends ConsumerState<AssistantManagementPage> {
  Object? _preferenceMutationError;
  bool _preferenceMutationInFlight = false;
  AssistantPreferenceFact? _revokedPreferenceForUndo;

  @override
  void initState() {
    super.initState();
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
    final contentAccessState = ref.watch(personalContentAccessProvider);
    final preferencesAsync = ref.watch(assistantPreferencesProvider);
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
              header: AssistantText.assistantPrivacyPermissions,
              child: Column(
                children: [
                  _buildPermissionRow(
                    AssistantText.assistantContentAccessPermission,
                    contentAccessState.granted,
                    (value) {
                      if (contentAccessState.isHydrating ||
                          contentAccessState.isSyncing) {
                        return;
                      }
                      unawaited(
                        ref
                            .read(personalContentAccessProvider.notifier)
                            .setGranted(value),
                      );
                    },
                    CupertinoIcons.lock_shield,
                    enabled:
                        !contentAccessState.isHydrating &&
                        !contentAccessState.isSyncing,
                    detail: contentAccessState.isSyncing
                        ? AssistantText.assistantSyncing
                        : (contentAccessState.isHydrating
                              ? AssistantText.assistantLoading
                              : (contentAccessState.granted
                                    ? AssistantText
                                          .assistantContentAccessGranted
                                    : AssistantText
                                          .assistantContentAccessNotGranted)),
                  ),
                  if ((contentAccessState.errorMessage ?? '').trim().isNotEmpty)
                    AppSectionErrorCard(
                      margin: EdgeInsets.fromLTRB(
                        AppSpacing.md,
                        AppSpacing.zero,
                        AppSpacing.md,
                        AppSpacing.interGroupSm,
                      ),
                      semantic: _consentErrorSemantic(
                        contentAccessState.errorMessage!.trim(),
                      ),
                      onAction: (action) async {
                        if (action.type == UiErrorActionType.retry ||
                            action.type == UiErrorActionType.resubmit) {
                          await ref
                              .read(personalContentAccessProvider.notifier)
                              .refresh();
                        }
                      },
                    ),
                ],
              ),
            ),
            SizedBox(height: AppSpacing.interGroupXl),
            SettingsInsetGroupedSection(
              isDark: isDark,
              header: AssistantText.assistantMemorySectionTitle,
              child: _buildPreferencesSection(
                preferencesAsync,
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

  UiErrorSemantic _consentErrorSemantic(String message) {
    return AppUserRecoveryContract.semanticFor(
      group: AppUserRecoveryGroup.reloadLater,
      category: UiErrorCategory.sectionLoad,
      scope: UiErrorScope.section,
      presentation: UiErrorPresentation.sectionSoftCard,
    );
  }

  Widget _buildPreferencesSection(
    AsyncValue<List<AssistantPreferenceFact>> preferencesAsync, {
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
          AppSectionErrorCard(
            margin: EdgeInsets.all(AppSpacing.md),
            semantic: runtimeErrorSemantic(
              context,
              error: _preferenceMutationError!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
            ),
            onAction: (_) async {
              if (mounted) {
                setState(() => _preferenceMutationError = null);
              }
            },
          ),
        preferencesAsync.when(
          loading: () => Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: AppRequestFeedback.section(),
          ),
          error: (error, _) => AppSectionErrorCard(
            margin: EdgeInsets.all(AppSpacing.md),
            semantic: _preferenceLoadErrorSemantic(error),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                ref.invalidate(assistantPreferencesProvider);
              }
            },
          ),
          data: (preferences) {
            final active = preferences
                .where(
                  (preference) =>
                      preference.status == AssistantPreferenceStatus.active,
                )
                .toList(growable: false);
            if (active.isEmpty && !_hasRevocationUndo) {
              return Padding(
                padding: EdgeInsets.all(AppSpacing.md),
                child: Text(
                  AssistantText.assistantMemoryEmpty,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                ),
              );
            }
            return Column(
              children: <Widget>[
                if (_hasRevocationUndo)
                  _buildRevocationUndo(
                    _revokedPreferenceForUndo!,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
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
          },
        ),
      ],
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

  bool get _hasRevocationUndo {
    final preference = _revokedPreferenceForUndo;
    if (preference == null ||
        preference.status != AssistantPreferenceStatus.revoked) {
      return false;
    }
    final deadline = DateTime.tryParse(
      preference.revocationDeadline?.trim() ?? '',
    );
    return deadline != null && deadline.toUtc().isAfter(DateTime.now().toUtc());
  }

  Widget _buildRevocationUndo(
    AssistantPreferenceFact preference, {
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
            onPressed: _preferenceMutationInFlight
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
    AssistantPreferenceFact preference, {
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
            onPressed: _preferenceMutationInFlight ? null : onAction,
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
      onPressed: _preferenceMutationInFlight
          ? null
          : () => _setLongTermPreference(kind, value),
      child: Text(label),
    );
  }

  String _preferenceTitle(AssistantPreferenceFact preference) {
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

  String _preferenceDetail(AssistantPreferenceFact preference) {
    final scope = preference.scope == AssistantPreferenceScope.session
        ? AssistantText.assistantPreferenceSessionScope
        : AssistantText.assistantPreferenceLongTermScope;
    final updatedAt = _formattedPreferenceUpdatedAt(preference.updatedAt);
    return <String>[
      scope,
      if (updatedAt.isNotEmpty)
        context.l10n.assistantMemoryUpdatedAt(updatedAt),
    ].join(' · ');
  }

  String _formattedPreferenceUpdatedAt(String raw) {
    final parsed = DateTime.tryParse(raw.trim());
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
    await _runPreferenceMutation(
      () => ref
          .read(assistantPreferenceFactFacetProvider)
          .setAssistantPreference(
            scope: AssistantPreferenceScope.longTerm,
            kind: kind,
            value: value,
            sourceType: AssistantPreferenceSourceType.management,
          ),
    );
  }

  Future<void> _revokePreference(AssistantPreferenceFact preference) async {
    final revoked = await _runPreferenceMutation(
      () => ref
          .read(assistantPreferenceFactFacetProvider)
          .revokeAssistantPreference(preferenceId: preference.preferenceId),
    );
    if (revoked != null && mounted) {
      setState(() => _revokedPreferenceForUndo = revoked);
    }
  }

  Future<void> _restorePreference(AssistantPreferenceFact preference) async {
    final restored = await _runPreferenceMutation(
      () => ref
          .read(assistantPreferenceFactFacetProvider)
          .restoreAssistantPreference(preferenceId: preference.preferenceId),
    );
    if (restored != null && mounted) {
      setState(() => _revokedPreferenceForUndo = null);
    }
  }

  Future<T?> _runPreferenceMutation<T>(Future<T> Function() action) async {
    if (_preferenceMutationInFlight) {
      return null;
    }
    setState(() {
      _preferenceMutationInFlight = true;
      _preferenceMutationError = null;
    });
    try {
      final result = await action();
      ref.invalidate(assistantPreferencesProvider);
      return result;
    } catch (error) {
      _preferenceMutationError = error;
      return null;
    } finally {
      if (mounted) {
        setState(() => _preferenceMutationInFlight = false);
      }
    }
  }

  Widget _buildPermissionRow(
    String label,
    bool value,
    ValueChanged<bool> onChanged,
    IconData icon, {
    bool enabled = true,
    String? detail,
  }) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.interGroupSm,
      ),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconSmall, color: fgSecondary),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w700,
                    color: fgPrimary,
                  ),
                ),
                if (detail != null && detail.trim().isNotEmpty) ...[
                  SizedBox(height: AppSpacing.two),
                  Text(
                    detail,
                    style: TextStyle(
                      fontSize: AppTypography.xsPlus,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          CupertinoSwitch(
            value: value,
            onChanged: enabled ? onChanged : null,
            activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
            inactiveTrackColor:
                SettingsSemanticConstants.switchInactiveTrackColor(isDark),
          ),
        ],
      ),
    );
  }
}
