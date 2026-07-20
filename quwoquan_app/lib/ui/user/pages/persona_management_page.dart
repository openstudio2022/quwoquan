import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_form_page.dart';
import 'package:quwoquan_app/ui/user/providers/persona_management_provider.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';

class PersonaManagementPage extends ConsumerStatefulWidget {
  const PersonaManagementPage({super.key});

  @override
  ConsumerState<PersonaManagementPage> createState() =>
      _PersonaManagementPageState();
}

class _PersonaManagementPageState extends ConsumerState<PersonaManagementPage> {
  late final JourneyEventTracker _journeyTracker;
  late final DateTime _enteredAt;

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: UITextConstants.personaManagementLoadFailedTitle,
      message: resolved.message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction:
          resolved.primaryAction ??
          const UiErrorAction(
            type: UiErrorActionType.retry,
            label: UITextConstants.tryAgain,
          ),
      secondaryAction: resolved.secondaryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      recoveryAction: resolved.recoveryAction,
      presentation: resolved.presentation,
      tone: resolved.tone,
    );
  }

  Future<void> _showActionErrorFeedback({
    required Object error,
    required String title,
    required String fallbackMessage,
    Future<void> Function()? onRetry,
  }) async {
    if (!mounted) {
      return;
    }
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    final semantic = UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: title,
      message: fallbackMessage,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction: onRetry == null
          ? resolved.primaryAction
          : const UiErrorAction(
              type: UiErrorActionType.retry,
              label: UITextConstants.tryAgain,
            ),
      secondaryAction: resolved.secondaryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      recoveryAction: resolved.recoveryAction,
      presentation: resolved.presentation,
      tone: resolved.tone,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: semantic,
      onAction: (action) async {
        if ((action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) &&
            onRetry != null) {
          await onRetry();
        }
      },
    );
  }

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _enteredAt = DateTime.now();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(
        _journeyTracker.trackAction(
          journey: 'persona_management',
          action: 'enter',
          pageName: 'PersonaManagementPage',
        ),
      );
      unawaited(ref.read(personaManagementProvider.notifier).load());
    });
  }

  @override
  void dispose() {
    unawaited(
      _journeyTracker.trackAction(
        journey: 'persona_management',
        action: 'exit',
        pageName: 'PersonaManagementPage',
        payload: <String, dynamic>{
          'durationMs': DateTime.now().difference(_enteredAt).inMilliseconds,
        },
      ),
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final enabled = ref.watch(personaManagementFeatureFlagProvider);
    final state = ref.watch(personaManagementProvider);
    final notifier = ref.read(personaManagementProvider.notifier);
    final quota = state.quota;
    final pageErrorSemantic = state.rawError == null
        ? null
        : _resolvePageErrorSemantic(state.rawError!);
    final canCreate =
        quota == null || quota.usedSubAccounts < quota.maxSubAccounts;

    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(
          context,
        ).withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.personaManage,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: enabled && canCreate
            ? AppNavigationBarIconButton(
                icon: CupertinoIcons.add,
                onPressed: () => _showCreateDialog(notifier),
              )
            : null,
      ),
      body: !enabled
          ? Center(
              child: Text(
                UITextConstants.personaManage,
                style: TextStyle(color: AppColors.iosSecondaryLabel(context)),
              ),
            )
          : state.isLoading
          ? const Center(child: CupertinoActivityIndicator())
          : pageErrorSemantic != null
          ? AppPageErrorState(
              semantic: pageErrorSemantic,
              onAction: (action) async {
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  await notifier.load();
                }
              },
            )
          : ListView(
              padding: EdgeInsets.only(
                top: AppSpacing.containerSm,
                bottom:
                    MediaQuery.viewPaddingOf(context).bottom +
                    AppSpacing.interGroupLg,
              ),
              children: <Widget>[
                if (state.pendingSyncSuggestion != null)
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                    ),
                    child: _SuggestionCard(
                      suggestion: state.pendingSyncSuggestion!,
                      onApplyAll: () => _applySuggestion(
                        notifier,
                        state.pendingSyncSuggestion!,
                      ),
                      onSelectTargets: () => _showTargetPicker(
                        notifier,
                        state.pendingSyncSuggestion!,
                      ),
                      onIgnore: notifier.ignorePendingSuggestion,
                    ),
                  ),
                if (state.pendingSyncSuggestion != null)
                  SizedBox(height: AppSpacing.interGroupMd),
                Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  child: ProfileIosSectionCard(
                    addShadow: true,
                    child: Row(
                      children: <Widget>[
                        Container(
                          width: AppSpacing.buttonSize,
                          height: AppSpacing.buttonSize,
                          decoration: BoxDecoration(
                            color: AppColors.iosTintedFill(context),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            CupertinoIcons.person_2,
                            color: AppColors.iosAccent(context),
                            size: AppSpacing.iconMedium,
                          ),
                        ),
                        SizedBox(width: AppSpacing.containerSm),
                        Expanded(
                          child: Text(
                            '${state.items.length}/${quota?.maxSubAccounts ?? 5}',
                            style: TextStyle(
                              fontSize: AppTypography.iosTitle3,
                              fontWeight: AppTypography.semiBold,
                              color: AppColors.iosLabel(context),
                            ),
                          ),
                        ),
                        if (canCreate)
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: () => _showCreateDialog(notifier),
                            child: const Text(UITextConstants.personaCreate),
                          ),
                      ],
                    ),
                  ),
                ),
                if (state.items.length <= 1) ...<Widget>[
                  SizedBox(height: AppSpacing.interGroupSm),
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                    ),
                    child: Text(
                      UITextConstants.personaDefaultOnlyHint,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        height: AppSpacing.textLineHeightFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                        fontWeight: AppTypography.regular,
                      ),
                    ),
                  ),
                ],
                SizedBox(height: AppSpacing.interGroupMd),
                ...state.items.map(
                  (persona) => Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.interGroupSm,
                    ),
                    child: _PersonaCard(
                      persona: persona,
                      isCurrent: _isCurrentPersona(state, persona),
                      onActivate: () =>
                          notifier.activatePersona(persona.subAccountId),
                      onEdit: () => _showEditDialog(notifier, persona),
                      onRetire: () => _handleRetire(notifier, persona),
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  bool _isCurrentPersona(
    PersonaManagementState state,
    PersonaManagementItemViewData persona,
  ) {
    final current = state.activeContext?.subAccountId;
    if (current == null || current.isEmpty) {
      return persona.isActive;
    }
    return current == persona.subAccountId;
  }

  Future<void> _showCreateDialog(PersonaManagementNotifier notifier) async {
    final quota = ref.read(personaManagementProvider).quota;
    if (quota != null && quota.quotaReached) {
      await notifier.trackQuotaReached(quota.maxSubAccounts);
      if (!mounted) {
        return;
      }
      AppToast.show(
        context,
        UITextConstants.profileSubAccountMaxReachedTemplate.replaceFirst(
          '%s',
          '${quota.maxSubAccounts}',
        ),
      );
      return;
    }

    final created = await Navigator.of(context).push<PersonaFormResult>(
      CupertinoPageRoute<PersonaFormResult>(
        builder: (_) => PersonaFormPage.create(notifier: notifier),
      ),
    );
    if (!mounted || created == null || created.createdPersona == null) {
      return;
    }
    await _showCreateSuccessDialog(notifier, created.createdPersona!);
  }

  Future<void> _showCreateSuccessDialog(
    PersonaManagementNotifier notifier,
    PersonaManagementItemViewData created,
  ) async {
    await showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(UITextConstants.personaCreateSuccess),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text(UITextConstants.personaSwitchLater),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () async {
              Navigator.of(dialogContext).pop();
              await notifier.activatePersona(created.subAccountId);
            },
            child: const Text(UITextConstants.personaSwitchNow),
          ),
        ],
      ),
    );
  }

  Future<void> _showEditDialog(
    PersonaManagementNotifier notifier,
    PersonaManagementItemViewData persona,
  ) async {
    await Navigator.of(context).push<PersonaFormResult>(
      CupertinoPageRoute<PersonaFormResult>(
        builder: (_) =>
            PersonaFormPage.edit(notifier: notifier, persona: persona),
      ),
    );
  }

  Future<void> _handleRetire(
    PersonaManagementNotifier notifier,
    PersonaManagementItemViewData persona,
  ) async {
    try {
      final guard = await notifier.getLifecycleGuard(persona.subAccountId);
      if (!mounted) {
        return;
      }
      if (!guard.allowed) {
        AppToast.show(context, _retireBlockedMessage(guard.reason));
        return;
      }
      final confirmed = await showAppCupertinoDialog<bool>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(UITextConstants.personaRetire),
          content: Text(
            UITextConstants.personaRetireConfirmTemplate.replaceFirst(
              '%s',
              persona.displayName,
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(UITextConstants.cancel),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(UITextConstants.personaRetire),
            ),
          ],
        ),
      );
      if (confirmed == true) {
        await notifier.retirePersona(persona.subAccountId);
      }
    } catch (e) {
      if (mounted) {
        await _showActionErrorFeedback(
          error: e,
          title: UITextConstants.personaRetireErrorTitle,
          fallbackMessage: UITextConstants.personaRetireErrorMessage,
        );
      }
    }
  }

  String _retireBlockedMessage(String blockedReason) {
    return switch (blockedReason) {
      'blocked_primary_persona' => UITextConstants.personaRetirePrimaryBlocked,
      'blocked_last_persona' => UITextConstants.personaRetireLastBlocked,
      'blocked_active_persona' => UITextConstants.personaRetireActiveBlocked,
      'blocked_retired_persona' => UITextConstants.personaRetireAlreadyBlocked,
      _ => UITextConstants.personaRetireBlocked,
    };
  }

  Future<void> _applySuggestion(
    PersonaManagementNotifier notifier,
    PersonaSyncSuggestionViewData suggestion,
  ) async {
    try {
      await notifier.applySyncSuggestion(suggestion: suggestion);
    } catch (e) {
      if (mounted) {
        await _showActionErrorFeedback(
          error: e,
          title: UITextConstants.personaSyncErrorTitle,
          fallbackMessage: UITextConstants.personaSyncErrorMessage,
          onRetry: () async {
            await _applySuggestion(notifier, suggestion);
          },
        );
      }
    }
  }

  Future<void> _showTargetPicker(
    PersonaManagementNotifier notifier,
    PersonaSyncSuggestionViewData suggestion,
  ) async {
    final selected = <String, bool>{
      for (final id in suggestion.targetPersonaIds) id: true,
    };
    await showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => CupertinoAlertDialog(
          title: const Text(UITextConstants.personaSyncApplySelected),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              children: <Widget>[
                for (var i = 0; i < suggestion.targetPersonaIds.length; i++)
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      final id = suggestion.targetPersonaIds[i];
                      setDialogState(() {
                        selected[id] = !(selected[id] ?? false);
                      });
                    },
                    child: Row(
                      children: <Widget>[
                        Expanded(
                          child: Text(
                            suggestion.targetDisplayNames[i],
                            style: TextStyle(
                              color: AppColors.iosLabel(context),
                            ),
                          ),
                        ),
                        Icon(
                          selected[suggestion.targetPersonaIds[i]] == true
                              ? CupertinoIcons.check_mark_circled_solid
                              : CupertinoIcons.circle,
                          color: AppColors.iosAccent(context),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(UITextConstants.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                final targetIds = selected.entries
                    .where((entry) => entry.value)
                    .map((entry) => entry.key)
                    .toList(growable: false);
                if (targetIds.isEmpty) {
                  return;
                }
                await notifier.applySyncSuggestion(
                  suggestion: suggestion,
                  targetPersonaIds: targetIds,
                );
              },
              child: const Text(UITextConstants.confirm),
            ),
          ],
        ),
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({
    required this.suggestion,
    required this.onApplyAll,
    required this.onSelectTargets,
    required this.onIgnore,
  });

  final PersonaSyncSuggestionViewData suggestion;
  final VoidCallback onApplyAll;
  final VoidCallback onSelectTargets;
  final VoidCallback onIgnore;

  @override
  Widget build(BuildContext context) {
    return ProfileIosSectionCard(
      addShadow: true,
      backgroundColor: AppColors.iosTintedFill(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(UITextConstants.personaSyncSuggestionTitle),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            UITextConstants.personaSyncSuggestionBody,
            style: TextStyle(color: AppColors.iosSecondaryLabel(context)),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: <Widget>[
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onApplyAll,
                child: const Text(UITextConstants.personaSyncApplyAll),
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onSelectTargets,
                child: const Text(UITextConstants.personaSyncApplySelected),
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onIgnore,
                child: const Text(UITextConstants.personaSyncIgnore),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PersonaCard extends StatelessWidget {
  const _PersonaCard({
    required this.persona,
    required this.isCurrent,
    required this.onActivate,
    required this.onEdit,
    required this.onRetire,
  });

  final PersonaManagementItemViewData persona;
  final bool isCurrent;
  final VoidCallback onActivate;
  final VoidCallback onEdit;
  final VoidCallback onRetire;

  @override
  Widget build(BuildContext context) {
    final isRetired = persona.isRetired;
    final inheritanceLabel = persona.inheritsProfileFromOwner
        ? (persona.lastProfileSyncAt != null
              ? UITextConstants.personaInheritanceSynced
              : UITextConstants.personaInheritanceDefault)
        : UITextConstants.personaInheritanceCustom;
    final syncLabel = !persona.hasContactInfo
        ? UITextConstants.personaSyncStatusMissing
        : (persona.lastProfileSyncAt != null
              ? UITextConstants.personaSyncStatusReady
              : inheritanceLabel);

    return ProfileIosSectionCard(
      key: ValueKey<String>('persona-card-${persona.subAccountId}'),
      addShadow: isCurrent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Flexible(
                          child: Text(
                            persona.displayName,
                            style: TextStyle(
                              fontSize: AppTypography.iosTitle3,
                              fontWeight: AppTypography.semiBold,
                              color: AppColors.iosLabel(context),
                            ),
                          ),
                        ),
                        if (persona.isPrimary) ...<Widget>[
                          SizedBox(width: AppSpacing.intraGroupXs),
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerSm,
                              vertical: AppSpacing.intraGroupXs,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.iosTintedFill(context),
                              borderRadius: BorderRadius.circular(
                                AppSpacing.radiusTwenty,
                              ),
                            ),
                            child: const Text(UITextConstants.personaPrimary),
                          ),
                        ],
                      ],
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      '${UITextConstants.personaUserHandleLabel}: ${persona.userHandle.isEmpty ? '-' : persona.userHandle}',
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                    Text(
                      '${UITextConstants.personaPhoneLabel}: ${persona.phone.isEmpty ? '-' : persona.phone}',
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                    Text(
                      '${UITextConstants.personaEmailLabel}: ${persona.email.isEmpty ? '-' : persona.email}',
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      '$inheritanceLabel · $syncLabel',
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                key: ValueKey<String>('persona-status-${persona.subAccountId}'),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupXs,
                ),
                decoration: BoxDecoration(
                  color: isRetired
                      ? AppColors.iosFill(context)
                      : isCurrent
                      ? AppColors.iosAccent(context)
                      : AppColors.iosFill(context),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                ),
                child: Text(
                  isRetired
                      ? UITextConstants.personaRetired
                      : isCurrent
                      ? UITextConstants.personaCurrentUsing
                      : UITextConstants.personaInactive,
                  style: TextStyle(
                    color: !isRetired && isCurrent
                        ? AppColors.white
                        : AppColors.iosSecondaryLabel(context),
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: <Widget>[
              CupertinoButton(
                key: ValueKey<String>(
                  'persona-activate-${persona.subAccountId}',
                ),
                padding: EdgeInsets.zero,
                onPressed: isCurrent || isRetired ? null : onActivate,
                child: Text(
                  isRetired
                      ? UITextConstants.personaRetired
                      : isCurrent
                      ? UITextConstants.personaCurrentUsing
                      : UITextConstants.personaSwitchNow,
                ),
              ),
              CupertinoButton(
                key: ValueKey<String>('persona-edit-${persona.subAccountId}'),
                padding: EdgeInsets.zero,
                onPressed: isRetired ? null : onEdit,
                child: const Text(UITextConstants.profileEditLabel),
              ),
              if (!persona.isPrimary && !isRetired)
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onRetire,
                  child: const Text(UITextConstants.personaRetire),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
