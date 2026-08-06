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
  final List<BlockedListItemView> _items = <BlockedListItemView>[];
  final Set<String> _unblocking = <String>{};
  String? _nextCursor;
  Object? _rawError;
  bool _loading = false;
  bool _loadingMore = false;

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
      if (!mounted) {
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
      if (!mounted) {
        return;
      }
      setState(() => _rawError = error);
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
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
    setState(() => _unblocking.add(item.targetPersonaId));
    try {
      final result = await ref
          .read(
            personaRelationshipBlockWriterProvider(AppUiSurfaces.blockedUsers),
          )
          .unblockUser(
            UnblockUserCommand(targetPersonaId: item.targetPersonaId),
          );
      if (!mounted) {
        return;
      }
      if (!result.blocked) {
        setState(() {
          _items.removeWhere(
            (candidate) => candidate.targetPersonaId == item.targetPersonaId,
          );
        });
      }
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'unblock_user',
              pageName: 'BlockedUsersPage',
              targetType: 'user',
              targetKey: item.targetPersonaId,
            ),
      );
      AppToast.show(context, ContentText.blockedUsersUnblockSuccess);
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _unblock(item);
          }
        },
      );
    } finally {
      if (mounted) {
        setState(() => _unblocking.remove(item.targetPersonaId));
      }
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
