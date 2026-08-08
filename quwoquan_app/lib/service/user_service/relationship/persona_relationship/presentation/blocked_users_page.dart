import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show blockedListQueryProvider, personaRelationshipBlockWriterProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// PersonaRelationship 私有拉黑列表页。
///
/// 页面只消费对象级 [BlockedListQuery]/[BlockCommandWriter]；拉黑态真相来自
/// 云端列表与 capability，不维护进程内 Set。
class BlockedUsersPage extends ConsumerStatefulWidget {
  const BlockedUsersPage({super.key});

  @override
  ConsumerState<BlockedUsersPage> createState() => _BlockedUsersPageState();
}

class _BlockedUsersPageState extends ConsumerState<BlockedUsersPage> {
  static const Duration _unblockReadbackTimeout = Duration(seconds: 10);
  static const int _unblockReadbackPageSize = 100;

  final List<BlockedListItemView> _items = <BlockedListItemView>[];
  final Set<String> _unblocking = <String>{};
  final Map<String, int> _unblockAttemptByTarget = <String, int>{};
  String? _nextCursor;
  Object? _rawError;
  bool _loading = false;
  bool _loadingMore = false;
  int _listRequestGeneration = 0;
  int _unblockAttemptSequence = 0;

  @override
  void initState() {
    super.initState();
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(_load(reset: true));
    }
  }

  Future<void> _load({required bool reset}) async {
    if (_loading || _loadingMore) {
      return;
    }
    final requestGeneration = ++_listRequestGeneration;
    setState(() {
      if (reset) {
        _loading = true;
        _rawError = null;
      } else {
        _loadingMore = true;
      }
    });
    try {
      final page = await ref
          .read(blockedListQueryProvider)
          .listBlockedUsers(
            ListBlockedUsersQuery(
              cursor: reset ? null : _nextCursor,
              limit: 20,
            ),
          );
      if (!mounted || requestGeneration != _listRequestGeneration) {
        return;
      }
      setState(() {
        if (reset) {
          _items
            ..clear()
            ..addAll(page.items);
        } else {
          _items.addAll(page.items);
        }
        _nextCursor = page.nextCursor;
        _rawError = null;
      });
    } catch (error) {
      if (!mounted || requestGeneration != _listRequestGeneration) {
        return;
      }
      setState(() => _rawError = error);
    } finally {
      if (mounted && requestGeneration == _listRequestGeneration) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  void _invalidateListRequests() {
    _listRequestGeneration += 1;
    _loading = false;
    _loadingMore = false;
  }

  Future<void> _confirmUnblock(BlockedListItemView item) async {
    if (_unblocking.contains(item.targetPersonaId)) {
      return;
    }
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(ContentText.blockedUsersUnblockConfirmTitle),
        content: const Text(ContentText.blockedUsersUnblockConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(ContentText.blockedUsersUnblock),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) {
      return;
    }
    await _unblock(item);
  }

  Future<void> _unblock(BlockedListItemView item) async {
    if (_unblocking.contains(item.targetPersonaId)) {
      return;
    }
    final targetPersonaId = item.targetPersonaId;
    final attempt = ++_unblockAttemptSequence;
    Object? failure;
    setState(() {
      _unblocking.add(targetPersonaId);
      _unblockAttemptByTarget[targetPersonaId] = attempt;
      // Any earlier list request is now stale. Its late response must not
      // overwrite the authoritative verification started by this mutation.
      _invalidateListRequests();
    });
    try {
      final result = await ref
          .read(
            personaRelationshipBlockWriterProvider(AppUiSurfaces.blockedUsers),
          )
          .unblockUser(UnblockUserCommand(targetPersonaId: targetPersonaId));
      if (!mounted || _unblockAttemptByTarget[targetPersonaId] != attempt) {
        return;
      }
      if (result.targetPersonaId != targetPersonaId || result.blocked) {
        throw StateError('UnblockUser returned a mismatched typed result');
      }
      final targetStillBlocked = await _authoritativeReadbackContains(
        targetPersonaId,
      ).timeout(_unblockReadbackTimeout);
      if (targetStillBlocked) {
        throw StateError(
          'UnblockUser did not converge in the authoritative blocked list',
        );
      }
      if (!mounted || _unblockAttemptByTarget[targetPersonaId] != attempt) {
        return;
      }
      setState(() {
        _items.removeWhere(
          (candidate) => candidate.targetPersonaId == targetPersonaId,
        );
      });
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'unblock_user',
              pageName: 'BlockedUsersPage',
              targetType: 'user',
              targetKey: targetPersonaId,
            ),
      );
      AppToast.show(context, ContentText.blockedUsersUnblockSuccess);
    } catch (error) {
      if (_isCurrentUnblockAttempt(targetPersonaId, attempt)) {
        failure = error;
      }
    } finally {
      if (_isCurrentUnblockAttempt(targetPersonaId, attempt)) {
        setState(() => _unblocking.remove(targetPersonaId));
      }
    }
    if (failure != null &&
        mounted &&
        _unblockAttemptByTarget[targetPersonaId] == attempt) {
      final semantic = ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _unblock(item);
          }
        },
      );
    }
  }

  bool _isCurrentUnblockAttempt(String targetPersonaId, int attempt) =>
      mounted && _unblockAttemptByTarget[targetPersonaId] == attempt;

  Future<bool> _authoritativeReadbackContains(String targetPersonaId) async {
    final reader = ref.read(blockedListQueryProvider);
    final seenCursors = <String>{};
    String? cursor;
    while (true) {
      final page = await reader.listBlockedUsers(
        ListBlockedUsersQuery(cursor: cursor, limit: _unblockReadbackPageSize),
      );
      if (page.items.any(
        (candidate) => candidate.targetPersonaId == targetPersonaId,
      )) {
        return true;
      }
      final nextCursor = page.nextCursor?.trim() ?? '';
      if (nextCursor.isEmpty) {
        return false;
      }
      if (!seenCursors.add(nextCursor)) {
        throw StateError('Blocked list readback returned a cursor cycle');
      }
      cursor = nextCursor;
    }
  }

  Future<void> _requestLogin() async {
    await requireLogin(
      ref,
      context,
      AuthGateReason.blockUser,
      redirect: AppRoutePaths.blockedUsers,
      dismissFallback: AppRoutePaths.settings,
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final isAuthenticated = ref.watch(
      authSessionControllerProvider.select((state) => state.isAuthenticated),
    );
    ref.listen<bool>(
      authSessionControllerProvider.select((state) => state.isAuthenticated),
      (previous, next) {
        if (next && previous != true && _items.isEmpty) {
          unawaited(_load(reset: true));
        }
      },
    );
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: ContentText.blockedUsersTitle,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoutePaths.settings);
        }
      },
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: isAuthenticated
              ? _buildAuthenticatedBody(isDark)
              : _buildLoginRequired(isDark),
        ),
      ),
    );
  }

  Widget _buildAuthenticatedBody(bool isDark) {
    if (_loading && _items.isEmpty) {
      return AppRequestFeedback.section();
    }
    if (_rawError case final error? when _items.isEmpty) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load(reset: true);
            return _rawError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    if (_items.isEmpty) {
      return _BlockedUsersEmptyState(isDark: isDark);
    }
    return ListView(
      padding: EdgeInsets.only(
        left: SettingsSemanticConstants.insetFormListHorizontalPadding,
        right: SettingsSemanticConstants.insetFormListHorizontalPadding,
        top: AppSpacing.intraGroupSm,
        bottom: AppSpacing.xl,
      ),
      children: <Widget>[
        SettingsInsetGroupedSection(
          isDark: isDark,
          density: SettingsInsetSectionDensity.compact,
          child: Column(
            children: <Widget>[
              for (var index = 0; index < _items.length; index += 1) ...[
                _BlockedUserRow(
                  item: _items[index],
                  isDark: isDark,
                  busy: _unblocking.contains(_items[index].targetPersonaId),
                  onUnblock: () => _confirmUnblock(_items[index]),
                ),
                if (index != _items.length - 1)
                  SettingsInsetFormSectionDivider(isDark: isDark),
              ],
            ],
          ),
        ),
        if (_nextCursor != null || _loadingMore)
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.interGroupMd),
            child: Center(
              child: _loadingMore
                  ? AppRequestFeedback.inline()
                  : CupertinoButton(
                      onPressed: () => _load(reset: false),
                      child: const Text(ContentText.loadMore),
                    ),
            ),
          ),
      ],
    );
  }

  Widget _buildLoginRequired(bool isDark) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.lock_shield,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              ContentText.blockedUsersLoginTitle,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContentText.blockedUsersLoginSubtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupLg),
            CupertinoButton.filled(
              onPressed: _requestLogin,
              child: const Text(FoundationText.profileLoginNow),
            ),
          ],
        ),
      ),
    );
  }
}

class _BlockedUserRow extends StatelessWidget {
  const _BlockedUserRow({
    required this.item,
    required this.isDark,
    required this.busy,
    required this.onUnblock,
  });

  final BlockedListItemView item;
  final bool isDark;
  final bool busy;
  final VoidCallback onUnblock;

  @override
  Widget build(BuildContext context) {
    final handle = item.userHandle.isEmpty ? '' : '@${item.userHandle}';
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
      ),
      child: Row(
        children: <Widget>[
          ClipOval(
            child: SizedBox.square(
              dimension: AppSpacing.avatarUserMd,
              child: AppMediaImage(
                imageSource: item.avatarUrl ?? '',
                fit: BoxFit.cover,
                placeholder: Icon(
                  CupertinoIcons.person_crop_circle_fill,
                  color: AppColors.iosSecondaryLabel(context),
                  size: AppSpacing.iconLarge,
                ),
                errorWidget: Icon(
                  CupertinoIcons.person_crop_circle_fill,
                  color: AppColors.iosSecondaryLabel(context),
                  size: AppSpacing.iconLarge,
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  item.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: SettingsSemanticConstants.labelColor(isDark),
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.medium,
                  ),
                ),
                if (handle.isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    handle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: AppColors.iosSecondaryLabel(context),
                      fontSize: AppTypography.iosFootnote,
                    ),
                  ),
                ],
              ],
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            onPressed: busy ? null : onUnblock,
            child: busy
                ? AppRequestFeedback.inline()
                : const Text(ContentText.blockedUsersUnblock),
          ),
        ],
      ),
    );
  }
}

class _BlockedUsersEmptyState extends StatelessWidget {
  const _BlockedUsersEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.person_crop_circle_badge_checkmark,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              ContentText.blockedUsersEmptyTitle,
              style: TextStyle(
                color: SettingsSemanticConstants.labelColor(isDark),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContentText.blockedUsersEmptySubtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
