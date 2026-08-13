import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';

/// 添加联系人确认页：展示目标用户资料与来源，统一以 follow 语义完成「添加」。
class ContactConfirmPage extends ConsumerStatefulWidget {
  const ContactConfirmPage({
    super.key,
    required this.targetUserId,
    this.handle = '',
    this.source = '',
  });

  final String targetUserId;
  final String handle;
  final String source;

  @override
  ConsumerState<ContactConfirmPage> createState() => _ContactConfirmPageState();
}

class _ContactConfirmPageState extends ConsumerState<ContactConfirmPage> {
  static const Duration _followReadbackTimeout = Duration(seconds: 10);

  late Future<_ConfirmData> _future;
  bool _adding = false;
  ContactAddState? _localAddState;
  int _followAttemptSequence = 0;
  int? _activeFollowAttempt;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_ConfirmData> _load() async {
    final profile = await ref
        .read(personaQueryProvider(AppUiSurfaces.addContactConfirm))
        .getPersonaProfile(widget.targetUserId);
    final capability = await ref
        .read(
          relationshipCapabilityRepositoryForSurfaceProvider(
            AppUiSurfaces.addContactConfirm,
          ),
        )
        .getCapability(widget.targetUserId);
    if (capability.targetPersonaId.trim() != widget.targetUserId.trim()) {
      throw StateError(
        'GetRelationshipCapability returned a mismatched target persona',
      );
    }
    return _ConfirmData(profile: profile, capability: capability);
  }

  void _reload() {
    setState(() {
      _activeFollowAttempt = null;
      _followAttemptSequence += 1;
      _adding = false;
      _localAddState = null;
      _future = _load();
    });
  }

  Future<void> _add(_ConfirmData data, ContactAddState addState) async {
    if (_adding || !_canSubmitFollow(data, addState)) {
      return;
    }
    final attempt = ++_followAttemptSequence;
    Object? failure;
    setState(() => _adding = true);
    _activeFollowAttempt = attempt;
    try {
      await ref
          .read(
            personaRelationshipCommandWriterProvider(
              AppUiSurfaces.addContactConfirm,
            ),
          )
          .follow(
            widget.targetUserId,
            sourceSurfaceId: AppUiSurfaces.addContactConfirm.id,
          );
      if (!mounted || _activeFollowAttempt != attempt) {
        return;
      }
      final confirmedCapability = await ref
          .read(
            relationshipCapabilityRepositoryForSurfaceProvider(
              AppUiSurfaces.addContactConfirm,
            ),
          )
          .getCapability(widget.targetUserId)
          .timeout(_followReadbackTimeout);
      if (confirmedCapability.targetPersonaId.trim() !=
              widget.targetUserId.trim() ||
          !confirmedCapability.viewerFollowsTarget ||
          confirmedCapability.isBlocked ||
          confirmedCapability.isBlockedBy) {
        throw StateError(
          'FollowUser did not converge in authoritative relationship state',
        );
      }
      // 权威确认后回写共享关系投影，其他 watch 该投影的页面即时一致。
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(
            widget.targetUserId,
            confirmedCapability.viewerFollowsTarget,
          );
      if (!mounted || _activeFollowAttempt != attempt) {
        return;
      }
      setState(() => _localAddState = ContactAddState.added);
      AppToast.show(context, ContactText.addContactConfirmedToast);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'follow_contact_confirmed',
              pageName: 'ContactConfirmPage',
              targetType: 'user',
              targetKey: widget.targetUserId,
              payload: <String, Object?>{'source': widget.source},
            ),
      );
    } catch (error) {
      if (_isCurrentFollowAttempt(attempt)) {
        failure = error;
      }
    } finally {
      if (_isCurrentFollowAttempt(attempt)) {
        setState(() => _adding = false);
      }
    }
    if (failure == null || !mounted || _activeFollowAttempt != attempt) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _add(data, addState);
        }
      },
    );
  }

  bool _isCurrentFollowAttempt(int attempt) =>
      mounted && _activeFollowAttempt == attempt;

  bool _canSubmitFollow(_ConfirmData data, ContactAddState addState) {
    final capability = data.capability;
    return addState.canTriggerAdd &&
        capability.targetPersonaId.trim() == widget.targetUserId.trim() &&
        capability.canFollow &&
        !capability.viewerFollowsTarget &&
        !capability.isBlocked &&
        !capability.isBlockedBy &&
        !capability.isSelf;
  }

  String get _sourceLabel {
    switch (widget.source) {
      case 'scan':
        return ContactText.addContactConfirmSourceScan;
      case 'phone':
        return ContactText.addContactConfirmSourcePhone;
      case 'search':
        return ContactText.addContactConfirmSourceSearch;
      case 'qr':
        return ContactText.addContactConfirmSourceQr;
      default:
        return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.home);
            }
          },
        ),
        middle: Text(
          ContactText.addContactSheetTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: FutureBuilder<_ConfirmData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return AppPageErrorState(
              semantic: UiErrorSemanticResolver.resolve(
                context,
                error: snapshot.error!,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
              ),
              onRecovery: (action) async {
                if (action.type == UiErrorActionType.retry) {
                  _reload();
                  return UiRecoveryOutcome.superseded;
                }
                return UiRecoveryOutcome.cancelled;
              },
            );
          }
          if (!snapshot.hasData) {
            return AppRequestFeedback.section();
          }
          return _buildBody(context, snapshot.data!);
        },
      ),
    );
  }

  Widget _buildBody(BuildContext context, _ConfirmData data) {
    final profile = data.profile;
    final addState =
        _localAddState ??
        ContactCandidateVm.addStateFromCapability(
          relationState: data.capability.relationState,
          canFollow: data.capability.canFollow,
          canUnfollow: data.capability.canUnfollow,
        );
    final handle = profile.userHandle.isNotEmpty
        ? profile.userHandle
        : widget.handle;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            SizedBox(height: AppSpacing.containerLg),
            Center(
              child: _Avatar(url: profile.avatarUrl, name: profile.displayName),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              profile.displayName,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            if (handle.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                '${ProfileText.editProfileQuwoquanIdLabel}: $handle',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
            if (_sourceLabel.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                _sourceLabel,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ),
            ],
            const Spacer(),
            _PrimaryButton(
              addState: addState,
              pending: _adding,
              enabled: _canSubmitFollow(data, addState),
              onAdd: () => _add(data, addState),
            ),
            SizedBox(height: AppSpacing.containerMd),
          ],
        ),
      ),
    );
  }
}

class _ConfirmData {
  const _ConfirmData({required this.profile, required this.capability});

  final PersonaProfileViewData profile;
  final RelationshipCapabilityViewData capability;
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.url, required this.name});

  final String url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final initial = name.trim().isNotEmpty
        ? name.trim().characters.first.toUpperCase()
        : '';
    final fallback = ColoredBox(
      color: AppColors.iosAccent(context).withValues(alpha: 0.12),
      child: Center(
        child: initial.isEmpty
            ? Icon(
                CupertinoIcons.person_fill,
                size: AppSpacing.iconLarge,
                color: AppColors.iosAccent(context),
              )
            : Text(
                initial,
                style: TextStyle(
                  fontSize: AppTypography.iosTitle2,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosAccent(context),
                ),
              ),
      ),
    );
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.avatarUserXl,
        height: AppSpacing.avatarUserXl,
        child: url.trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: url,
                fit: BoxFit.cover,
                width: AppSpacing.avatarUserXl,
                height: AppSpacing.avatarUserXl,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    required this.addState,
    required this.pending,
    required this.enabled,
    required this.onAdd,
  });

  final ContactAddState addState;
  final bool pending;
  final bool enabled;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final isAdded = addState == ContactAddState.added;
    final isSelf = addState == ContactAddState.isSelf;
    final label = switch (addState) {
      ContactAddState.added => ContactText.contactAlreadyAdded,
      ContactAddState.canFollowBack => ContactText.contactAddBack,
      ContactAddState.isSelf => ContactText.contactAlreadyAdded,
      _ => ContactText.addContactSheetTitle,
    };
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        color: (isAdded || isSelf || !enabled)
            ? AppColors.iosSeparator(context)
            : AppColors.iosAccent(context),
        onPressed: (isAdded || isSelf || pending || !enabled) ? null : onAdd,
        child: pending
            ? AppRequestFeedback.inline()
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: (isAdded || isSelf || !enabled)
                      ? AppColors.iosSecondaryLabel(context)
                      : AppColors.white,
                ),
              ),
      ),
    );
  }
}
