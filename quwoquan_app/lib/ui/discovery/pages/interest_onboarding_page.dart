import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/content/onboarding/interest_onboarding.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/interest_onboarding_provider.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

/// 独立于资料编辑的首启兴趣采集；只确认推荐行为，不修改 Profile。
class InterestOnboardingPage extends ConsumerStatefulWidget {
  const InterestOnboardingPage({super.key});

  @override
  ConsumerState<InterestOnboardingPage> createState() =>
      _InterestOnboardingPageState();
}

class _InterestOnboardingPageState
    extends ConsumerState<InterestOnboardingPage> {
  static const int _maxLeafChoicesPerDimension = 32;

  final Map<String, List<TagChild>> _options = <String, List<TagChild>>{};
  final Set<String> _selected = <String>{};
  InterestOnboardingDraft? _draft;
  bool _loading = true;
  bool _submitting = false;
  Object? _loadError;
  late final ProviderSubscription<AuthSessionState> _authSubscription;

  OnboardingInterestCatalogConfig get _catalog =>
      ContentUIConfig.onboardingInterestCatalog;

  @override
  void initState() {
    super.initState();
    _authSubscription = ref.listenManual<AuthSessionState>(
      authSessionControllerProvider,
      (_, state) {
        if (state.isAuthenticated) unawaited(_resumeAfterLogin());
      },
    );
    unawaited(_load());
  }

  @override
  void dispose() {
    _authSubscription.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final coordinator = ref.read(interestOnboardingCoordinatorProvider);
      final query = ref.read(tagCatalogQueryProvider);
      final options = <String, List<TagChild>>{};
      for (final dimension in _catalog.dimensions) {
        options[dimension.id] = await _loadLeafChoices(query, dimension.tagRef);
      }
      final draft = await coordinator.load();
      if (!mounted) return;
      setState(() {
        _draft = draft;
        if (draft?.status != InterestOnboardingStatus.submitted &&
            draft?.status != InterestOnboardingStatus.skipped) {
          _selected
            ..clear()
            ..addAll(draft?.tagRefs ?? const <String>[]);
        }
        _options
          ..clear()
          ..addAll(options);
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = error;
      });
    }
  }

  /// The catalog root contains categories as well as terminal tags. The
  /// confirmed server contract accepts only active leaves, so flattening just
  /// one direct-child level would make the UI submit categories that it is
  /// guaranteed to reject.
  ///
  /// Keep the discovery bounded for first-run latency, but traverse the live
  /// catalog rather than carrying a client-side tag allowlist.
  Future<List<TagChild>> _loadLeafChoices(
    TagCatalogQuery query,
    String rootTagRef,
  ) async {
    final queue = <String>[rootTagRef.trim()];
    final visited = <String>{};
    final leaves = <TagChild>[];
    var cursor = 0;

    while (cursor < queue.length &&
        leaves.length < _maxLeafChoicesPerDimension) {
      final parentTagRef = queue[cursor++].trim();
      if (parentTagRef.isEmpty || !visited.add(parentTagRef)) continue;
      final children = await query.listChildren(parentTagRef);
      for (final child in children) {
        final tagRef = child.tagRef.trim();
        if (tagRef.isEmpty) continue;
        if (child.hasChildren) {
          queue.add(tagRef);
        } else {
          leaves.add(child);
          if (leaves.length >= _maxLeafChoicesPerDimension) break;
        }
      }
    }

    if (leaves.isEmpty) {
      throw StateError('onboarding catalog root has no selectable leaves');
    }
    return List<TagChild>.unmodifiable(leaves);
  }

  Future<void> _resumeAfterLogin() async {
    if (!mounted || _submitting) return;
    final continuation = ref
        .read(authContinuationProvider.notifier)
        .take<SubmitOnboardingInterestContinuation>();
    if (continuation == null) return;
    try {
      final draft = await ref
          .read(interestOnboardingCoordinatorProvider)
          .select(
            catalogVersion: continuation.catalogVersion,
            taxonomyReleaseId: continuation.taxonomyReleaseId,
            tagRefs: continuation.tagRefs,
            previous: InterestOnboardingDraft(
              catalogVersion: continuation.catalogVersion,
              taxonomyReleaseId: continuation.taxonomyReleaseId,
              clientEventId: continuation.clientEventId,
              tagRefs: continuation.tagRefs,
              status: InterestOnboardingStatus.unseen,
            ),
          );
      if (!mounted) return;
      setState(() => _draft = draft);
      await _submit(draft);
    } catch (error) {
      if (!mounted) return;
      await _showActionError(error, category: UiErrorCategory.submit);
    }
  }

  Future<void> _submit([InterestOnboardingDraft? restored]) async {
    if (_submitting) return;
    final selectedCount = restored?.tagRefs.length ?? _selected.length;
    if (selectedCount < _catalog.minSelectionCount) {
      _showMessage(UITextConstants.interestOnboardingSelectionRequiredMessage);
      return;
    }
    var continuationRegistered = false;
    try {
      final coordinator = ref.read(interestOnboardingCoordinatorProvider);
      final draft =
          restored ??
          await coordinator.select(
            catalogVersion: _catalog.version,
            taxonomyReleaseId: _catalog.taxonomyReleaseId,
            tagRefs: _selected,
            previous: _draft,
          );
      if (!mounted) return;
      setState(() {
        _draft = draft;
        _submitting = true;
      });
      if (!ref.read(authSessionControllerProvider).isAuthenticated) {
        final accepted = ref
            .read(authContinuationProvider.notifier)
            .set(
              SubmitOnboardingInterestContinuation(
                catalogVersion: draft.catalogVersion,
                taxonomyReleaseId: draft.taxonomyReleaseId,
                clientEventId: draft.clientEventId,
                tagRefs: draft.tagRefs,
              ),
            );
        if (!accepted) throw StateError('continuation slot unavailable');
        continuationRegistered = true;
        final allowed = await requireLogin(
          ref,
          context,
          AuthGateReason.generic,
          dismissFallback: AppRoutePaths.home,
          dismissPolicy: LoginDismissPolicy.safeFallback,
        );
        if (!allowed) {
          // requireLogin 打开登录页后立即返回 false，并不代表用户关闭登录。
          // continuation 留给 _resumeAfterLogin；游客关闭由登录页 clear。
          if (mounted) setState(() => _submitting = false);
          return;
        }
        // 竞态：引导期间已登录，继续走下方提交。
        _takeOnboardingContinuation();
        continuationRegistered = false;
      }
      final submitted = await coordinator.submit(draft);
      if (!mounted) return;
      setState(() {
        _draft = submitted;
        _submitting = false;
      });
      // 保留当前 feedSession；失效同一会话缓存后让 TagRecall 立即重读。
      ref.invalidate(discoveryFeedMapProvider);
      context.go(AppRoutePaths.home);
    } catch (error) {
      if (continuationRegistered) _takeOnboardingContinuation();
      if (!mounted) return;
      setState(() => _submitting = false);
      await _showActionError(error, category: UiErrorCategory.submit);
    }
  }

  Future<void> _skip() async {
    try {
      await ref
          .read(interestOnboardingCoordinatorProvider)
          .skip(
            catalogVersion: _catalog.version,
            taxonomyReleaseId: _catalog.taxonomyReleaseId,
            previous: _draft,
          );
    } catch (error) {
      if (!mounted) return;
      await _showActionError(
        error,
        category: UiErrorCategory.submit,
        allowRetry: false,
      );
    }
    if (mounted) context.go(AppRoutePaths.home);
  }

  void _takeOnboardingContinuation() {
    ref
        .read(authContinuationProvider.notifier)
        .take<SubmitOnboardingInterestContinuation>();
  }

  Future<void> _showActionError(
    Object error, {
    required UiErrorCategory category,
    bool allowRetry = true,
  }) {
    return AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: category,
        scope: UiErrorScope.global,
        allowRetry: allowRetry,
        sourceSurfaceId: AppUiSurfaces.interestOnboarding.id,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _submit();
        }
      },
    );
  }

  void _toggle(TagChild option, OnboardingInterestDimensionConfig dimension) {
    final tagRef = option.tagRef.trim();
    if (tagRef.isEmpty) return;
    setState(() {
      if (_selected.remove(tagRef)) return;
      final inDimension = (_options[dimension.id] ?? const <TagChild>[])
          .where((option) => _selected.contains(option.tagRef))
          .length;
      if (inDimension >= dimension.maxSelections ||
          _selected.length >= _catalog.maxSelectionCount) {
        _showMessage(UITextConstants.interestOnboardingSelectionLimit);
        return;
      }
      _selected.add(tagRef);
    });
  }

  void _showMessage(String message) {
    if (!mounted) return;
    showCupertinoDialog<void>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        content: Text(message),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text(UITextConstants.confirm),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      key: const ValueKey<String>('interest-onboarding-page'),
      navigationBar: CupertinoNavigationBar(
        middle: const Text(UITextConstants.interestOnboardingTitle),
        trailing: CupertinoButton(
          key: const ValueKey<String>('interest-onboarding-skip'),
          padding: EdgeInsets.zero,
          onPressed: _submitting ? null : () => unawaited(_skip()),
          child: const Text(UITextConstants.interestOnboardingSkip),
        ),
      ),
      child: SafeArea(child: _buildBody(context)),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) return const Center(child: CupertinoActivityIndicator());
    final loadError = _loadError;
    if (loadError != null) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: loadError,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.global,
          sourceSurfaceId: AppUiSurfaces.interestOnboarding.id,
        ),
        onAction: (_) => _load(),
      );
    }
    final colors = CupertinoTheme.of(context);
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.containerLg),
      children: <Widget>[
        Text(
          UITextConstants.interestOnboardingSubtitle,
          style: colors.textTheme.textStyle.copyWith(
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
        const SizedBox(height: AppSpacing.containerXl),
        for (final dimension in _catalog.dimensions) ...<Widget>[
          Text(
            dimension.displayLabel,
            style: colors.textTheme.navTitleTextStyle,
          ),
          const SizedBox(height: AppSpacing.intraGroupMd),
          Wrap(
            spacing: AppSpacing.intraGroupMd,
            runSpacing: AppSpacing.intraGroupMd,
            children: <Widget>[
              for (final option in _options[dimension.id] ?? const <TagChild>[])
                CupertinoButton(
                  key: ValueKey<String>(
                    'interest-onboarding-option-${option.tagRef}',
                  ),
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.intraGroupLg,
                    vertical: AppSpacing.intraGroupSm,
                  ),
                  color: _selected.contains(option.tagRef)
                      ? AppColors.iosAccent(context)
                      : AppColors.iosSecondaryFill(context),
                  onPressed: _submitting
                      ? null
                      : () => _toggle(option, dimension),
                  child: Text(
                    option.displayLabel.trim().isEmpty
                        ? option.label
                        : option.displayLabel,
                    style: TextStyle(
                      color: _selected.contains(option.tagRef)
                          ? AppColors.white
                          : AppColors.iosLabel(context),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.containerXl),
        ],
        CupertinoButton.filled(
          key: const ValueKey<String>('interest-onboarding-submit'),
          onPressed: _submitting ? null : () => unawaited(_submit()),
          child: Text(
            _submitting
                ? UITextConstants.interestOnboardingSubmitting
                : UITextConstants.interestOnboardingSubmit,
          ),
        ),
      ],
    );
  }
}
