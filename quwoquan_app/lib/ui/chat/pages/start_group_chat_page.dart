import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_member_wizard_provider.dart';

part 'start_group_chat_page_widgets.dart';
part 'start_group_chat_member_sheet.dart';

/// 与云侧 CreateConversation 默认 maxGroupSize 对齐的前置上限；超限由服务端
/// 二次校验并通过结构化错误回传，客户端仅做即时拦截。
const int _kStartGroupChatMaxMembers = 500;

/// 发起群聊 / 添加成员两种模式的可观测命名（埋点事件属性，非路由/surface 契约）。
const String _kCreateModePageName = 'start_group_chat';
const String _kAddMemberModePageName = 'group_add_members';
const String _kStartGroupChatSurface = 'start_group_chat';
const String _kStartGroupChatRoute = '/chat/start-group';
const String _kStartGroupChatJourney = 'start_group_chat';

/// 发起群聊页（图一：创建新群聊 + 相关联系人）
class StartGroupChatPage extends ConsumerStatefulWidget {
  const StartGroupChatPage({
    super.key,
    this.conversationId,
    required this.onBack,
  });

  final String? conversationId;
  final VoidCallback onBack;

  bool get isCreateMode => conversationId == null || conversationId!.isEmpty;

  @override
  ConsumerState<StartGroupChatPage> createState() => _StartGroupChatPageState();
}

class _StartGroupChatPageState extends ConsumerState<StartGroupChatPage> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _listScrollController = ScrollController();
  late final String _wizardId;
  late final PageLifecycleObservability _pageObservability;
  late final JourneyEventTracker _journeyTracker;
  late final DateTime _enteredAt;

  List<ChatContactRowDto> _contacts = [];
  bool _selectedExpanded = false;
  bool _submitting = false;
  String _query = '';
  bool _isLoading = true;
  UiErrorSemantic? _pageErrorSemantic;

  String get _analyticsPageName =>
      widget.isCreateMode ? _kCreateModePageName : _kAddMemberModePageName;

  void _recordPageState({
    required String phase,
    Object? error,
    int? itemCount,
    int? durationMs,
  }) {
    _pageObservability.recordPageState(
      pageName: _analyticsPageName,
      route: _kStartGroupChatRoute,
      surface: _kStartGroupChatSurface,
      phase: phase,
      error: error,
      itemCount: itemCount,
      durationMs: durationMs,
    );
  }

  @override
  void initState() {
    super.initState();
    _wizardId =
        '${widget.conversationId ?? 'create'}_${DateTime.now().microsecondsSinceEpoch}';
    _pageObservability = ref.read(pageLifecycleObservabilityProvider);
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _enteredAt = DateTime.now();
    _recordPageState(phase: 'enter');
    Future<void>.microtask(() {
      if (!mounted) {
        return;
      }
      final wizard = ref.read(
        startGroupMemberWizardProvider(_wizardId).notifier,
      );
      if (widget.isCreateMode) {
        wizard.completeBootstrap(const <String>{});
      } else {
        wizard.setBootstrapLoading();
      }
    });
    _loadData();
  }

  Future<void> _loadData() async {
    _recordPageState(phase: 'onlineLoading');
    try {
      final chatRepo = ref.read(chatRepositoryProvider);
      final contacts = await chatRepo.listGroupCandidates(
        conversationId: widget.conversationId,
        limit: _kStartGroupChatMaxMembers,
      );
      if (mounted) {
        ref
            .read(startGroupMemberWizardProvider(_wizardId).notifier)
            .completeBootstrap(const <String>{});
        setState(() {
          _contacts = contacts;
          _isLoading = false;
          _pageErrorSemantic = null;
        });
      }
      _recordPageState(
        phase: contacts.isEmpty ? 'emptyState' : 'onlineSuccess',
        itemCount: contacts.length,
      );
    } catch (error) {
      if (mounted && !widget.isCreateMode) {
        ref
            .read(startGroupMemberWizardProvider(_wizardId).notifier)
            .completeBootstrap(const <String>{});
      }
      _recordPageState(phase: 'blockingFailure', error: error);
      if (!mounted) {
        return;
      }
      setState(() {
        _isLoading = false;
        _pageErrorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    }
  }

  @override
  void dispose() {
    _recordPageState(
      phase: 'exit',
      durationMs: DateTime.now().difference(_enteredAt).inMilliseconds,
    );
    _searchController.dispose();
    _listScrollController.dispose();
    super.dispose();
  }

  bool get _selectionBootstrapReady {
    if (widget.isCreateMode) {
      return true;
    }
    return ref
        .read(startGroupMemberWizardProvider(_wizardId))
        .isBootstrapLoaded;
  }

  void _handleCreateConversationSuccess(String conversationId) {
    AppToast.show(context, UITextConstants.startGroupChatCreatedToast);
    if (conversationId.isEmpty) {
      context.go(AppRoutePaths.chat);
    } else {
      context.go(AppRoutePaths.chatDetail(id: conversationId));
    }
  }

  void _handleAddMembersSuccess(int count) {
    AppToast.show(
      context,
      UITextConstants.startGroupChatMembersAddedCount(count),
    );
    context.pop();
  }

  void _handleSubmitSelectionError(Object error) {
    final semantic = UiErrorSemantic(
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
      title: widget.isCreateMode
          ? UITextConstants.startGroupChatCreateIncompleteTitle
          : UITextConstants.startGroupChatAddMembersIncompleteTitle,
      message: runtimeErrorDisplayMessage(error),
      primaryAction: const UiErrorAction(
        type: UiErrorActionType.retry,
        label: UITextConstants.tryAgain,
      ),
      dismissible: true,
    );
    unawaited(
      AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitSelection();
          }
        },
      ),
    );
  }

  Future<void> _refreshChatEntryLists() async {
    await ref.read(chatInboxListProvider.notifier).refresh();
    ref.invalidate(
      chatContactsRowsForSubTabProvider(UITextConstants.contactsTabGroups),
    );
  }

  void _toggleSelectedMember(StartGroupPickableMember member) {
    if (!_selectionBootstrapReady) {
      return;
    }
    ref
        .read(startGroupMemberWizardProvider(_wizardId).notifier)
        .toggleMember(member);
  }

  /// 上报发起群聊 / 添加成员的转化结果到 journey funnel 与页面观测；
  /// 失败时携带结构化错误（sourceCode / failureKind 由观测层统一抽取），
  /// 与上一轮服务端 not_mutual / blocked / size 错误码同源。
  void _recordSubmitOutcome({
    required bool success,
    required int memberCount,
    Object? error,
  }) {
    final action = widget.isCreateMode
        ? (success ? 'create_success' : 'create_failed')
        : (success ? 'add_members_success' : 'add_members_failed');
    unawaited(
      _journeyTracker.trackAction(
        journey: _kStartGroupChatJourney,
        action: action,
        pageName: _analyticsPageName,
        targetType: 'conversation',
        targetKey: widget.conversationId ?? '',
        entityType: 'conversation',
        payload: <String, dynamic>{
          'isCreateMode': widget.isCreateMode,
          'memberCount': memberCount,
        },
      ),
    );
    _recordPageState(
      phase: success ? 'submitSuccess' : 'submitFailure',
      error: error,
      itemCount: memberCount,
    );
  }

  Future<void> _submitSelection() async {
    final wizardState = ref.read(startGroupMemberWizardProvider(_wizardId));
    if (_submitting || wizardState.selectedMembers.isEmpty) {
      return;
    }
    final selectedIds = wizardState.selectedMembers.keys.toList(
      growable: false,
    );
    if (widget.isCreateMode &&
        selectedIds.length >= _kStartGroupChatMaxMembers) {
      AppToast.show(context, UITextConstants.startGroupChatMaxMembersReached);
      return;
    }
    setState(() => _submitting = true);
    try {
      final repo = ref.read(chatRepositoryProvider);
      if (widget.isCreateMode) {
        final ChatConversationCreatedDto created = await repo
            .createConversation(
              type: 'group',
              title: wizardState.selectedMembers.values
                  .map((member) => member.displayName)
                  .where((name) => name.isNotEmpty)
                  .take(3)
                  .join('、'),
              maxGroupSize: _kStartGroupChatMaxMembers,
              initialMemberIds: selectedIds,
            );
        final conversationId = created.conversationId;
        _recordSubmitOutcome(success: true, memberCount: selectedIds.length);
        if (!context.mounted) {
          return;
        }
        await _refreshChatEntryLists();
        if (!context.mounted) {
          return;
        }
        _handleCreateConversationSuccess(conversationId);
      } else {
        await repo.addMembers(
          conversationId: widget.conversationId!,
          userIds: selectedIds,
        );
        _recordSubmitOutcome(success: true, memberCount: selectedIds.length);
        await _refreshChatEntryLists();
        if (!context.mounted) {
          return;
        }
        _handleAddMembersSuccess(selectedIds.length);
      }
    } catch (error) {
      _recordSubmitOutcome(
        success: false,
        memberCount: selectedIds.length,
        error: error,
      );
      if (!context.mounted) {
        return;
      }
      _handleSubmitSelectionError(error);
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  /// 按首字母分组：A-Z, #，返回有序 keys 与 map
  static ({List<String> keys, Map<String, List<StartGroupFriendLetterRow>> map})
  _groupByLetter(List<StartGroupFriendLetterRow> list) {
    final map = <String, List<StartGroupFriendLetterRow>>{};
    for (final m in list) {
      final name = m.displayName;
      final letter = m.letter.isNotEmpty
          ? m.letter
          : (name.isNotEmpty ? name.substring(0, 1).toUpperCase() : '#');
      final key = RegExp(r'[A-Za-z]').hasMatch(letter)
          ? letter.toUpperCase()
          : '#';
      map.putIfAbsent(key, () => []).add(m);
    }
    for (final key in map.keys) {
      map[key]!.sort((a, b) => a.displayName.compareTo(b.displayName));
    }
    final keys = map.keys.toList()..sort();
    if (keys.contains('#')) {
      keys.remove('#');
      keys.add('#');
    }
    return (keys: keys, map: map);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageTitle = widget.isCreateMode
        ? UITextConstants.startGroupChat
        : UITextConstants.addMember;
    if (_pageErrorSemantic != null && !_isLoading) {
      return SettingsInsetMemberPickerPageScaffold(
        isDark: isDark,
        title: pageTitle,
        onBack: widget.onBack,
        body: AppPageErrorState(
          semantic: _pageErrorSemantic!,
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              setState(() {
                _isLoading = true;
                _pageErrorSemantic = null;
              });
              await _loadData();
            }
          },
        ),
      );
    }
    final wizardState = ref.watch(startGroupMemberWizardProvider(_wizardId));
    final selectionReady = widget.isCreateMode || wizardState.isBootstrapLoaded;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final listHorizontalPadding =
        SettingsSemanticConstants.insetFormListHorizontalPadding;
    final selectedMembers = wizardState.selectedMembers.values.toList(
      growable: false,
    );
    final visibleSelectedCount = _selectedExpanded
        ? selectedMembers.length
        : (selectedMembers.length > 12 ? 12 : selectedMembers.length);
    final friendsWithLetter = _contacts
        .where((contact) {
          final userId = contact.userId;
          if (userId.isEmpty) {
            return false;
          }
          final displayName = contact.displayName;
          final normalizedQuery = _query.trim().toLowerCase();
          if (normalizedQuery.isEmpty) {
            return true;
          }
          return displayName.toLowerCase().contains(normalizedQuery) ||
              userId.toLowerCase().contains(normalizedQuery);
        })
        .map((c) {
          final displayName = c.displayName;
          return StartGroupFriendLetterRow(
            displayName: displayName,
            userId: c.userId,
            avatarUrl: c.avatarUrl,
            letter: displayName.isNotEmpty
                ? displayName.substring(0, 1).toUpperCase()
                : '#',
          );
        })
        .toList();
    final grouped = _groupByLetter(friendsWithLetter);
    final indexLetters = ['↑', '☆', ...grouped.keys];

    final letterKeys = <String, GlobalKey>{};
    for (final k in grouped.keys) {
      letterKeys[k] = GlobalKey();
    }

    final topChildren = <Widget>[
      if (!selectionReady) ...[
        SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            const CupertinoActivityIndicator(),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                UITextConstants.startGroupChatSyncingMemberState,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          ],
        ),
      ],
      _SelectionSectionLabel(
        title: UITextConstants.relatedMutualFollow,
        color: fgSecondary,
      ),
      SizedBox(height: AppSpacing.xs),
    ];

    final relatedChildren = <Widget>[];
    for (final letter in grouped.keys) {
      final membersForLetter = grouped.map[letter]!;
      relatedChildren.add(
        Column(
          key: letterKeys[letter],
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _SelectionSectionLabel(title: letter, color: fgSecondary),
            SizedBox(height: AppSpacing.xs),
            _SelectionCard(
              isDark: isDark,
              child: Column(
                children: [
                  for (
                    var index = 0;
                    index < membersForLetter.length;
                    index++
                  ) ...[
                    Builder(
                      builder: (context) {
                        final m = membersForLetter[index];
                        final username = m.userId;
                        final selected = wizardState.isSelected(username);
                        final locked = wizardState.isLocked(username);
                        final pickable = StartGroupPickableMember(
                          userId: username,
                          displayName: m.displayName.isNotEmpty
                              ? m.displayName
                              : username,
                          avatarUrl: m.avatarUrl,
                        );
                        return _RelatedFriendRow(
                          name: m.displayName,
                          username: username,
                          avatarUrl: m.avatarUrl,
                          selected: selected,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          locked: locked,
                          onTap: selectionReady && !locked
                              ? () => _toggleSelectedMember(pickable)
                              : null,
                          onAvatarTap: () => context.push(
                            AppRoutePaths.userProfile(username: username),
                            extra: UserProfileRouteExtra(
                              subAccountId: username,
                              avatar: m.avatarUrl.isNotEmpty
                                  ? m.avatarUrl
                                  : null,
                              displayName: m.displayName.isNotEmpty
                                  ? m.displayName
                                  : null,
                            ),
                          ),
                        );
                      },
                    ),
                    if (index < membersForLetter.length - 1)
                      _SelectionListDivider(
                        isDark: isDark,
                        leadingInset:
                            AppSpacing.minInteractiveSize +
                            AppSpacing.avatarSize +
                            AppSpacing.sm,
                      ),
                  ],
                ],
              ),
            ),
            SizedBox(height: AppSpacing.sm),
          ],
        ),
      );
    }

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: pageTitle,
      onBack: widget.onBack,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              listHorizontalPadding,
              AppSpacing.sm,
              listHorizontalPadding,
              AppSpacing.sm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.search,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (selectedMembers.isNotEmpty)
            Padding(
              padding: EdgeInsets.fromLTRB(
                listHorizontalPadding,
                0,
                listHorizontalPadding,
                AppSpacing.sm,
              ),
              child: _SelectionCard(
                isDark: isDark,
                padding: EdgeInsets.all(
                  SettingsSemanticConstants.blockHorizontalPadding,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          UITextConstants.startGroupChatSelectedCount(
                            selectedMembers.length,
                          ),
                          style: TextStyle(
                            fontSize: AppTypography.md,
                            fontWeight: FontWeight.w600,
                            color: fgPrimary,
                          ),
                        ),
                        const Spacer(),
                        if (selectedMembers.length > 12)
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            onPressed: () => setState(
                              () => _selectedExpanded = !_selectedExpanded,
                            ),
                            child: Text(
                              _selectedExpanded
                                  ? UITextConstants.collapse
                                  : UITextConstants.moreMembers,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: AppColors.primaryColor,
                              ),
                            ),
                          ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.sm,
                      children: List.generate(visibleSelectedCount, (index) {
                        final member = selectedMembers[index];
                        final userId = member.userId;
                        return _SelectedMemberAvatar(
                          name: member.displayName.isNotEmpty
                              ? member.displayName
                              : userId,
                          avatarUrl: member.avatarUrl,
                          isDark: isDark,
                          onRemove: () => ref
                              .read(
                                startGroupMemberWizardProvider(
                                  _wizardId,
                                ).notifier,
                              )
                              .deselectMemberIds(<String>[userId]),
                        );
                      }),
                    ),
                  ],
                ),
              ),
            ),
          Expanded(
            child: Stack(
              children: [
                ListView(
                  controller: _listScrollController,
                  padding: EdgeInsets.only(
                    left: listHorizontalPadding,
                    right: listHorizontalPadding + 28,
                    bottom: AppSpacing.lg,
                  ),
                  children: [...topChildren, ...relatedChildren],
                ),
                if (_isLoading)
                  const Positioned.fill(
                    child: Center(child: CupertinoActivityIndicator()),
                  ),
                Positioned(
                  right: AppSpacing.sm,
                  top: 0,
                  bottom: 0,
                  child: _LetterIndex(
                    letters: indexLetters,
                    onTap: (i) {
                      if (i <= 1) {
                        _listScrollController.animateTo(
                          0,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                        );
                        return;
                      }
                      final letter = indexLetters[i];
                      final key = letterKeys[letter];
                      if (key?.currentContext != null) {
                        Scrollable.ensureVisible(
                          key!.currentContext!,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                          alignment: 0,
                        );
                      }
                    },
                  ),
                ),
              ],
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                listHorizontalPadding,
                AppSpacing.sm,
                listHorizontalPadding,
                AppSpacing.sm,
              ),
              child: CupertinoButton(
                padding: EdgeInsets.symmetric(
                  vertical:
                      SettingsSemanticConstants.actionButtonPaddingVertical,
                ),
                color: SettingsSemanticConstants.actionButtonPrimaryBackground,
                disabledColor:
                    SettingsSemanticConstants.actionButtonDisabledBackground(
                      isDark,
                    ),
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.actionButtonBorderRadius,
                ),
                onPressed: selectedMembers.isEmpty || _submitting
                    ? null
                    : _submitSelection,
                child: _submitting
                    ? const CupertinoActivityIndicator()
                    : Text(
                        widget.isCreateMode
                            ? UITextConstants.startGroupChatActionCount(
                                selectedMembers.length,
                              )
                            : '${UITextConstants.addMember}（${selectedMembers.length}）',
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w600,
                          color: selectedMembers.isEmpty
                              ? SettingsSemanticConstants.actionButtonDisabledForeground(
                                  isDark,
                                )
                              : SettingsSemanticConstants
                                    .actionButtonPrimaryForeground,
                        ),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
