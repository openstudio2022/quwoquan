import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_candidate_row.dart';

/// 添加联系人搜索结果页：趣我圈号(精确)/昵称(模糊) 查找 + 能力位驱动添加。
class ContactSearchResultPage extends ConsumerStatefulWidget {
  const ContactSearchResultPage({super.key, this.initialQuery = ''});

  final String initialQuery;

  @override
  ConsumerState<ContactSearchResultPage> createState() =>
      _ContactSearchResultPageState();
}

class _ContactSearchResultPageState
    extends ConsumerState<ContactSearchResultPage> {
  static const Duration _followCapabilityTimeout = Duration(seconds: 10);

  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  String _query = '';
  bool _loading = false;
  List<ContactCandidateVm> _results = <ContactCandidateVm>[];
  final Set<String> _pending = <String>{};
  final Map<String, int> _followAttemptByTarget = <String, int>{};
  Object? _rawError;
  int _searchRequestGeneration = 0;
  int _followAttemptSequence = 0;

  @override
  void initState() {
    super.initState();
    if (widget.initialQuery.isNotEmpty) {
      _controller.text = widget.initialQuery;
      _query = widget.initialQuery;
      unawaited(_runSearch(widget.initialQuery));
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    setState(() {
      _query = value;
      _searchRequestGeneration += 1;
      _invalidateFollowAttempts();
    });
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 320), () {
      unawaited(_runSearch(value));
    });
  }

  void _onSubmitted(String value) {
    _debounce?.cancel();
    unawaited(_runSearch(value));
  }

  Future<void> _runSearch(String value) async {
    final query = value.trim();
    final requestGeneration = ++_searchRequestGeneration;
    if (query.isEmpty) {
      setState(() {
        _invalidateFollowAttempts();
        _results = <ContactCandidateVm>[];
        _loading = false;
        _rawError = null;
      });
      return;
    }
    setState(() {
      _invalidateFollowAttempts();
      _loading = true;
      _rawError = null;
    });
    try {
      final items = await ref
          .read(profileQueryProvider(AppUiSurfaces.addContactSearch))
          .searchSocialRelations(query: query);
      if (!mounted ||
          requestGeneration != _searchRequestGeneration ||
          _query.trim() != query) {
        return;
      }
      setState(() {
        _results = items.map(_toCandidate).toList(growable: false);
        _loading = false;
      });
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'contact_discovery',
              action: 'search_contact',
              pageName: 'ContactSearchResultPage',
              payload: <String, Object?>{
                'result': 'success',
                'resultCount': items.length,
              },
            ),
      );
    } catch (error) {
      if (!mounted || requestGeneration != _searchRequestGeneration) {
        return;
      }
      setState(() {
        _rawError = error;
        _loading = false;
      });
    }
  }

  ContactCandidateVm _toCandidate(SocialRelationSearchItemViewData item) {
    final cap = item.relationshipCapability;
    return ContactCandidateVm(
      personaId: item.personaId,
      displayName: item.displayName,
      userHandle: item.userHandle,
      avatarUrl: item.avatarUrl,
      avatarVersion: item.avatarVersion,
      subtitle: item.headline,
      addState: ContactCandidateVm.addStateFromCapability(
        relationState: cap.relationState,
        canFollow: cap.canFollow,
        canUnfollow: cap.canUnfollow,
        isBlocked: cap.isBlocked,
        isBlockedBy: cap.isBlockedBy,
      ),
    );
  }

  void _invalidateFollowAttempts() {
    _followAttemptByTarget.clear();
    _pending.clear();
  }

  Future<void> _add(ContactCandidateVm candidate) async {
    final selectedIndex = _results.indexWhere(
      (item) => item.personaId == candidate.personaId,
    );
    if (selectedIndex < 0) {
      return;
    }
    final selected = _results[selectedIndex];
    if (!selected.addState.canTriggerAdd ||
        _pending.contains(selected.personaId)) {
      return;
    }
    final targetPersonaId = selected.personaId;
    final resultGeneration = _searchRequestGeneration;
    final attempt = ++_followAttemptSequence;
    Object? failure;
    setState(() {
      _pending.add(targetPersonaId);
      _followAttemptByTarget[targetPersonaId] = attempt;
    });
    try {
      final capabilityRepository = ref.read(
        relationshipCapabilityRepositoryForSurfaceProvider(
          AppUiSurfaces.addContactSearch,
        ),
      );
      final preflight = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_followCapabilityTimeout);
      _requireFollowPreflight(preflight, targetPersonaId: targetPersonaId);
      if (!_isCurrentFollowAttempt(
        targetPersonaId,
        attempt,
        resultGeneration,
      )) {
        return;
      }
      await ref
          .read(
            personaRelationshipCommandWriterProvider(
              AppUiSurfaces.addContactSearch,
            ),
          )
          .follow(
            targetPersonaId,
            sourceSurfaceId: AppUiSurfaces.addContactSearch.id,
          );
      if (!_isCurrentFollowAttempt(
        targetPersonaId,
        attempt,
        resultGeneration,
      )) {
        return;
      }
      final confirmed = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_followCapabilityTimeout);
      if (confirmed.targetPersonaId.trim() != targetPersonaId.trim() ||
          !confirmed.viewerFollowsTarget ||
          confirmed.isBlocked ||
          confirmed.isBlockedBy) {
        throw StateError(
          'FollowUser did not converge in authoritative relationship state',
        );
      }
      // 权威确认后回写共享关系投影，其他 watch 该投影的页面即时一致。
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(targetPersonaId, confirmed.viewerFollowsTarget);
      if (!mounted ||
          !_isCurrentFollowAttempt(
            targetPersonaId,
            attempt,
            resultGeneration,
          )) {
        return;
      }
      setState(() {
        _results = _results
            .map(
              (c) => c.personaId == targetPersonaId
                  ? c.copyWith(addState: ContactAddState.added)
                  : c,
            )
            .toList(growable: false);
      });
      AppToast.show(context, ContactText.addContactConfirmedToast);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'follow_contact_from_search',
              pageName: 'ContactSearchResultPage',
              targetType: 'user',
              targetKey: targetPersonaId,
            ),
      );
    } catch (error) {
      if (_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
        failure = error;
      }
    } finally {
      if (_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
        setState(() => _pending.remove(targetPersonaId));
      }
    }
    if (failure == null ||
        !mounted ||
        !_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
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
          await _add(selected);
        }
      },
    );
  }

  void _requireFollowPreflight(
    RelationshipCapabilityViewData capability, {
    required String targetPersonaId,
  }) {
    if (capability.targetPersonaId.trim() != targetPersonaId.trim() ||
        !capability.canFollow ||
        capability.viewerFollowsTarget ||
        capability.isSelf ||
        capability.isBlocked ||
        capability.isBlockedBy) {
      throw StateError('FollowUser is not allowed by current capability');
    }
  }

  bool _isCurrentFollowAttempt(
    String targetPersonaId,
    int attempt,
    int resultGeneration,
  ) =>
      mounted &&
      _followAttemptByTarget[targetPersonaId] == attempt &&
      _searchRequestGeneration == resultGeneration;

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
              context.go(AppRoutePaths.addContact);
            }
          },
        ),
        middle: Text(
          ContactText.addContactSearchTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: EdgeInsets.all(AppSpacing.containerMd),
              child: AppSearchField(
                controller: _controller,
                autofocus: widget.initialQuery.isEmpty,
                placeholder: ContactText.addContactSearchHubPlaceholder,
                onChanged: _onChanged,
                onSubmitted: _onSubmitted,
              ),
            ),
            Expanded(child: _buildResults(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildResults(BuildContext context) {
    if (_loading && _results.isEmpty) {
      return AppRequestFeedback.section();
    }
    if (_rawError case final error?) {
      return AppPageErrorState(
        semantic: ensureRetryUiErrorSemantic(
          runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          ),
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _runSearch(_query);
            return _rawError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    if (_query.trim().isEmpty) {
      return _Hint(text: ContactText.addContactSearchEmptyPrompt);
    }
    if (_results.isEmpty) {
      return _Hint(text: ContactText.addContactSearchNoResult);
    }
    return ListView.builder(
      itemCount: _results.length,
      itemBuilder: (context, index) {
        final candidate = _results[index];
        return ContactCandidateRow(
          candidate: candidate,
          pending: _pending.contains(candidate.personaId),
          onAdd: () => unawaited(_add(candidate)),
          onTap: () => context.push(
            AppRoutePaths.addContactConfirm(
              handle: candidate.userHandle,
              userId: candidate.personaId,
              source: 'search',
            ),
          ),
        );
      },
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.base,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}
