import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// UserSettings.blockedKeywords 的私有管理页。
class BlockedKeywordsPage extends ConsumerStatefulWidget {
  const BlockedKeywordsPage({super.key});

  @override
  ConsumerState<BlockedKeywordsPage> createState() =>
      _BlockedKeywordsPageState();
}

class _BlockedKeywordsPageState extends ConsumerState<BlockedKeywordsPage> {
  final List<String> _keywords = <String>[];
  Object? _rawError;
  bool _loading = false;
  bool _saving = false;
  late final PageLifecycleObservability _pageObservability;
  late final DateTime _enteredAt;

  void _recordPageState({
    required String phase,
    Object? error,
    int? itemCount,
  }) {
    _pageObservability.recordPageState(
      pageName: 'BlockedKeywordsPage',
      route: AppRoutePaths.blockedKeywords,
      surface: AppUiSurfaces.blockedKeywords.id,
      phase: phase,
      error: error,
      itemCount: itemCount,
      durationMs: phase == 'exit'
          ? DateTime.now().difference(_enteredAt).inMilliseconds
          : null,
    );
  }

  @override
  void initState() {
    super.initState();
    _pageObservability = ref.read(pageLifecycleObservabilityProvider);
    _enteredAt = DateTime.now();
    _recordPageState(phase: 'enter');
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _rawError = null;
    });
    _recordPageState(phase: 'onlineLoading');
    try {
      final snapshot = await ref
          .read(userSettingsQueryReaderProvider)
          .getPrivacySettings();
      if (!mounted) return;
      setState(() {
        _keywords
          ..clear()
          ..addAll(snapshot.blockedKeywords);
        _rawError = null;
      });
      _recordPageState(
        phase: _keywords.isEmpty ? 'emptyState' : 'onlineSuccess',
        itemCount: _keywords.length,
      );
    } catch (error) {
      if (mounted) setState(() => _rawError = error);
      _recordPageState(phase: 'blockingFailure', error: error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _recordPageState(phase: 'exit', itemCount: _keywords.length);
    super.dispose();
  }

  Future<void> _addKeyword() async {
    if (_saving) return;
    final controller = TextEditingController();
    try {
      final keyword = await showAppCupertinoDialog<String>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(ContentText.blockedKeywordsAddTitle),
          content: Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
            child: CupertinoTextField(
              controller: controller,
              autofocus: true,
              placeholder: ContentText.blockedKeywordsAddHint,
              textInputAction: TextInputAction.done,
              onSubmitted: (value) =>
                  Navigator.of(dialogContext).pop(value.trim()),
            ),
          ),
          actions: <Widget>[
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () =>
                  Navigator.of(dialogContext).pop(controller.text.trim()),
              child: const Text(CommunityText.done),
            ),
          ],
        ),
      );
      if (keyword == null || keyword.isEmpty || !mounted) return;
      if (_keywords.contains(keyword)) return;
      await _save(
        <String>[..._keywords, keyword],
        action: 'add_blocked_keyword',
        successMessage: ContentText.blockedKeywordsAddSuccess,
      );
    } finally {
      controller.dispose();
    }
  }

  Future<void> _confirmRemove(String keyword) async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(ContentText.blockedKeywordsRemoveConfirmTitle),
        content: const Text(ContentText.blockedKeywordsRemoveConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(ContentText.blockedKeywordsRemove),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _save(
      _keywords.where((candidate) => candidate != keyword).toList(),
      action: 'remove_blocked_keyword',
      successMessage: ContentText.blockedKeywordsRemoveSuccess,
    );
  }

  Future<void> _save(
    List<String> next, {
    required String action,
    required String successMessage,
  }) async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      await ref
          .read(userSettingsCommandWriterProvider)
          .updatePrivacySettings(
            UpdatePrivacySettingsCommand(blockedKeywords: next),
          );
      if (!mounted) return;
      setState(() {
        _keywords
          ..clear()
          ..addAll(next);
      });
      ref.read(blockedKeywordSnapshotCacheProvider).replace(next);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'content_preference',
              action: action,
              pageName: 'BlockedKeywordsPage',
              payload: <String, Object?>{
                'result': 'success',
                'keywordCount': next.length,
              },
            ),
      );
      AppToast.show(context, successMessage);
    } catch (error) {
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (errorAction) async {
          if (errorAction.type == UiErrorActionType.retry ||
              errorAction.type == UiErrorActionType.resubmit) {
            await _save(next, action: action, successMessage: successMessage);
          }
        },
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _requestLogin() {
    return requireLogin(
      ref,
      context,
      AuthGateReason.settingsAccount,
      redirect: AppRoutePaths.blockedKeywords,
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
        if (next && previous != true && _keywords.isEmpty) {
          unawaited(_load());
        }
      },
    );
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: ContentText.blockedKeywordsTitle,
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
              : _buildLoginRequired(),
        ),
      ),
    );
  }

  Widget _buildAuthenticatedBody(bool isDark) {
    if (_loading && _keywords.isEmpty) {
      return AppRequestFeedback.section();
    }
    if (_rawError case final error? when _keywords.isEmpty) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load();
            return _rawError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
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
          child: SettingsInsetCenteredActionRow(
            isDark: isDark,
            label: ContentText.blockedKeywordsAdd,
            onTap: _addKeyword,
          ),
        ),
        SizedBox(height: SettingsSemanticConstants.insetFormSectionVerticalGap),
        if (_keywords.isEmpty)
          const _BlockedKeywordsEmptyState()
        else
          SettingsInsetGroupedSection(
            isDark: isDark,
            density: SettingsInsetSectionDensity.compact,
            child: Column(
              children: <Widget>[
                for (var index = 0; index < _keywords.length; index += 1) ...[
                  _BlockedKeywordRow(
                    keyword: _keywords[index],
                    busy: _saving,
                    onRemove: () => _confirmRemove(_keywords[index]),
                  ),
                  if (index != _keywords.length - 1)
                    SettingsInsetFormSectionDivider(isDark: isDark),
                ],
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildLoginRequired() {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.text_badge_minus,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              ContentText.blockedKeywordsLoginTitle,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContentText.blockedKeywordsLoginSubtitle,
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

class _BlockedKeywordRow extends StatelessWidget {
  const _BlockedKeywordRow({
    required this.keyword,
    required this.busy,
    required this.onRemove,
  });

  final String keyword;
  final bool busy;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
      ),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.text_badge_minus,
            size: SettingsSemanticConstants.insetFormRowIconSize,
            color: AppColors.iosSecondaryLabel(context),
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Text(
              keyword,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosBody,
              ),
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            onPressed: busy ? null : onRemove,
            child: const Text(ContentText.blockedKeywordsRemove),
          ),
        ],
      ),
    );
  }
}

class _BlockedKeywordsEmptyState extends StatelessWidget {
  const _BlockedKeywordsEmptyState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupLg),
      child: Column(
        children: <Widget>[
          Text(
            ContentText.blockedKeywordsEmptyTitle,
            style: TextStyle(
              color: AppColors.iosLabel(context),
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            ContentText.blockedKeywordsEmptySubtitle,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.iosSubheadline,
            ),
          ),
        ],
      ),
    );
  }
}
