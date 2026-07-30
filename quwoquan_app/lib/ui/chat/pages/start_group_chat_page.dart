import 'dart:async';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/models/start_group_chat_route_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/chat_interaction_telemetry_tracker.dart';
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
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/group_home_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_member_wizard_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/start_group_from_group_provider.dart';
import 'package:quwoquan_app/ui/chat/utils/chat_contact_initials.dart';
import 'package:quwoquan_app/ui/chat/utils/chat_pinyin_match.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';
import 'package:uuid/uuid.dart';

part 'start_group_chat_page_widgets.dart';
part 'start_group_chat_member_sheet.dart';
part 'start_group_chat_group_picker_sheet.dart';

/// 与云侧 CreateConversation 默认 maxGroupSize 对齐的前置上限；超限由服务端
/// 二次校验并通过结构化错误回传，客户端仅做即时拦截。
const int _kStartGroupChatMaxMembers = 1000;

/// ListGroupCandidates 的 canonical 单页上限。群聊成员容量与候选读取容量是
/// 不同的服务端约束；候选读取不得把 1000 人容量透传为无效 query 参数。
const int _kStartGroupChatCandidatePageLimit = 100;

/// 发起群聊 / 添加成员两种模式的可观测命名（埋点事件属性，非路由/surface 契约）。
const String _kCreateModePageName = PageNames.startGroupChat;
const String _kAddMemberModePageName = PageNames.chatAddMembers;
const String _kStartGroupChatRoute = AppRoutePaths.startGroupChat;
const String _kStartGroupChatJourney = 'start_group_chat';

/// 发起群聊页（图一：创建新群聊 + 相关联系人）
class StartGroupChatPage extends ConsumerStatefulWidget {
  const StartGroupChatPage({
    super.key,
    this.conversationId,
    this.routeExtra,
    required this.onBack,
  });

  final String? conversationId;
  final StartGroupChatRouteExtra? routeExtra;
  final VoidCallback onBack;

  bool get isCreateMode => conversationId == null || conversationId!.isEmpty;

  @override
  ConsumerState<StartGroupChatPage> createState() => _StartGroupChatPageState();
}

class _StartGroupChatPageState extends ConsumerState<StartGroupChatPage> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _listScrollController = ScrollController();
  final ScrollController _selectedScrollController = ScrollController();
  late final String _wizardId;
  late final PageLifecycleObservability _pageObservability;
  late final JourneyEventTracker _journeyTracker;
  late final ChatInteractionTelemetryTracker _chatTelemetryTracker;
  late final DateTime _enteredAt;

  List<ChatContactRowDto> _contacts = [];
  bool _submitting = false;
  String _query = '';
  bool _isLoading = true;
  UiErrorSemantic? _pageErrorSemantic;
  int _lastSelectedCount = 0;
  String? _createIntentFingerprint;
  String? _createIdempotencyKey;

  String get _analyticsPageName =>
      widget.isCreateMode ? _kCreateModePageName : _kAddMemberModePageName;
  String get _analyticsSurfaceId => widget.isCreateMode
      ? AppUiSurfaces.startGroupChat.id
      : AppUiSurfaces.chatAddMembers.id;

  void _recordPageState({
    required String phase,
    Object? error,
    int? itemCount,
    int? durationMs,
  }) {
    _pageObservability.recordPageState(
      pageName: _analyticsPageName,
      route: _kStartGroupChatRoute,
      surface: _analyticsSurfaceId,
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
    _chatTelemetryTracker = ref.read(chatInteractionTelemetryTrackerProvider);
    _enteredAt = DateTime.now();
    _recordPageState(phase: 'enter');
    _recordCompanionContextEnter();
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
      final chatRepo = ref.read(chatContactRepositoryProvider);
      final contacts = await chatRepo.listGroupCandidates(
        conversationId: widget.conversationId,
        limit: _kStartGroupChatCandidatePageLimit,
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
    _selectedScrollController.dispose();
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
    AppToast.show(context, ChatText.startGroupChatCreatedToast);
    if (conversationId.isEmpty) {
      context.go(AppRoutePaths.chat);
    } else {
      context.go(AppRoutePaths.chatDetail(id: conversationId));
    }
  }

  void _handleAddMembersSuccess(int count) {
    AppToast.show(context, ChatText.startGroupChatMembersAddedCount(count));
    context.pop();
  }

  void _handleSubmitSelectionError(Object error) {
    final semantic = _startGroupSubmitErrorSemantic(
      runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
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

  UiErrorSemantic _startGroupSubmitErrorSemantic(UiErrorSemantic base) {
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: widget.isCreateMode
          ? ChatText.startGroupChatCreateIncompleteTitle
          : ChatText.startGroupChatAddMembersIncompleteTitle,
      message: base.message,
      secondaryMessage: base.secondaryMessage,
      primaryAction:
          base.primaryAction ??
          const UiErrorAction(
            type: UiErrorActionType.dismiss,
            label: FoundationText.confirm,
          ),
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: base.copyKey,
      recoveryAction: base.recoveryAction,
      presentation: UiErrorPresentation.actionDialog,
      tone: base.tone,
      appearanceMode: base.appearanceMode,
      sourceRouteId: base.sourceRouteId,
      sourceSurfaceId: base.sourceSurfaceId,
    );
  }

  Future<void> _refreshChatEntryLists() async {
    await ref.read(chatInboxListProvider.notifier).refresh();
    ref.invalidate(
      chatContactsRowsForSubTabProvider(ChatText.contactsTabGroups),
    );
  }

  void _toggleSelectedMember(StartGroupPickableMember member) {
    if (!_selectionBootstrapReady) {
      return;
    }
    final wizardProvider = startGroupMemberWizardProvider(_wizardId);
    final wasSelected = ref.read(wizardProvider).isSelected(member.userId);
    ref.read(wizardProvider.notifier).toggleMember(member);
    if (!wasSelected) {
      unawaited(
        _chatTelemetryTracker.track(
          action: ChatInteractionAction.candidateSourceSelect,
          outcome: ChatInteractionOutcome.succeeded,
          source: ChatInteractionSource.contacts,
          memberCount: ref.read(wizardProvider).selectedMembers.length,
          pageName: _analyticsPageName,
          surfaceId: _analyticsSurfaceId,
        ),
      );
    }
  }

  /// 打开「从群聊 / 圈子中选择联系人」二级流程（图四 → 图五）。
  ///
  /// 用 Navigator.push(CupertinoPageRoute) 承载，不新增 GoRouter 路由/surface；
  /// wizardId 贯穿，图五选中项直接并入当前向导，返回后选中横向条自动滚到尾部。
  Future<void> _pushSourcePicker(StartGroupSource source) async {
    final isDark = ref.read(isDarkProvider);
    final sourceKey = source == StartGroupSource.circle ? 'circle' : 'group';
    unawaited(
      _chatTelemetryTracker.track(
        action: ChatInteractionAction.candidateSourceOpen,
        outcome: ChatInteractionOutcome.succeeded,
        source: source == StartGroupSource.circle
            ? ChatInteractionSource.circle
            : ChatInteractionSource.group,
        pageName: _analyticsPageName,
        surfaceId: _analyticsSurfaceId,
      ),
    );
    final applied = await Navigator.of(context).push<bool>(
      CupertinoPageRoute<bool>(
        builder: (_) => _GroupPickerSheet(
          key: ValueKey<String>('start-group-$sourceKey-picker-sheet'),
          wizardId: _wizardId,
          isDark: isDark,
          source: source,
          onBack: () => Navigator.of(context).pop(false),
        ),
      ),
    );
    if (!mounted || applied != true) {
      return;
    }
    final selectedCount = ref
        .read(startGroupMemberWizardProvider(_wizardId))
        .selectedMembers
        .length;
    unawaited(
      _chatTelemetryTracker.track(
        action: ChatInteractionAction.candidateSourceSelect,
        outcome: ChatInteractionOutcome.succeeded,
        source: source == StartGroupSource.circle
            ? ChatInteractionSource.circle
            : ChatInteractionSource.group,
        pageName: _analyticsPageName,
        surfaceId: _analyticsSurfaceId,
        memberCount: selectedCount,
      ),
    );
  }

  /// 上报发起群聊 / 添加成员的转化结果到 journey funnel 与页面观测；
  /// 失败时携带结构化错误（sourceCode / failureKind 由观测层统一抽取），
  /// 与上一轮服务端 not_mutual / blocked / size 错误码同源。
  void _recordSubmitOutcome({
    required bool success,
    required int memberCount,
    Object? error,
  }) {
    unawaited(
      _chatTelemetryTracker.track(
        action: widget.isCreateMode
            ? ChatInteractionAction.groupCreate
            : ChatInteractionAction.memberAdd,
        outcome: success
            ? ChatInteractionOutcome.succeeded
            : ChatInteractionOutcome.failed,
        pageName: _analyticsPageName,
        surfaceId: _analyticsSurfaceId,
        memberCount: memberCount,
        error: error,
      ),
    );
    _recordPageState(
      phase: success ? 'submitSuccess' : 'submitFailure',
      error: error,
      itemCount: memberCount,
    );
  }

  /// 从交集「拉群约伴」进来时，新群按共同对象命名（如「老君山 · 约伴」）。
  ///
  /// 这是承接页对上游承诺的兑现：banner 说了「已带入共同对象」，那么建出来的群
  /// 必须确实是关于这个对象的，否则用户只得到一个成员名拼接的普通群。
  /// 拿不到对象名时退回成员名，不用 objectId 当群名。
  String _createGroupTitle(String memberNameTitle) {
    final objectName = widget.routeExtra?.safeTargetObjectName ?? '';
    if (objectName.isEmpty) {
      return memberNameTitle;
    }
    return ChatText.startGroupChatCompanionGroupTitle(objectName);
  }

  void _recordCompanionContextEnter() {
    final extra = widget.routeExtra;
    if (extra == null || !extra.hasCompanionContext) {
      return;
    }
    unawaited(
      _journeyTracker.trackAction(
        journey: _kStartGroupChatJourney,
        action: 'companion_context_enter',
        pageName: _analyticsPageName,
        targetType: extra.safeTargetObjectKind.isEmpty
            ? 'intersection_target'
            : extra.safeTargetObjectKind,
        targetKey: extra.safeTargetObjectId,
        entityType: 'intersection',
        entityId: extra.intersectionId.trim(),
        payload: extra.toAnalyticsPayload(),
      ),
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
      AppToast.show(context, ChatText.startGroupChatMaxMembersReached);
      return;
    }
    setState(() => _submitting = true);
    try {
      final repo = ref.read(chatConversationRepositoryProvider);
      if (widget.isCreateMode) {
        final title = _createGroupTitle(
          wizardState.selectedMembers.values
              .map((member) => member.displayName)
              .where((name) => name.isNotEmpty)
              .take(3)
              .join('、'),
        );
        final ChatConversationCreatedDto created = await repo
            .createConversation(
              type: 'group',
              title: title,
              maxGroupSize: _kStartGroupChatMaxMembers,
              initialMemberIds: selectedIds,
              idempotencyKey: _idempotencyKeyForCreateIntent(
                title: title,
                initialMemberIds: selectedIds,
              ),
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
        await ref
            .read(conversationMembersProvider(widget.conversationId!).notifier)
            .addMembers(selectedIds);
        _recordSubmitOutcome(success: true, memberCount: selectedIds.length);
        await _refreshChatEntryLists();
        ref.invalidate(conversationMembersProvider(widget.conversationId!));
        ref.invalidate(groupHomeProvider(widget.conversationId!));
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

  /// 同一组建群意图的可重试提交必须复用键；一旦命令语义变化则签发新键。
  ///
  /// 标题和成员顺序均在服务端命令摘要中，因此二者都是 intent 的一部分。
  String _idempotencyKeyForCreateIntent({
    required String title,
    required List<String> initialMemberIds,
  }) {
    final fingerprint = <String>[
      'group',
      title,
      _kStartGroupChatMaxMembers.toString(),
      ...initialMemberIds,
    ].join('\u0000');
    if (_createIntentFingerprint != fingerprint ||
        _createIdempotencyKey == null) {
      _createIntentFingerprint = fingerprint;
      _createIdempotencyKey = const Uuid().v4();
    }
    return _createIdempotencyKey!;
  }

  /// 按首字母分组：A-Z, #，返回有序 keys 与 map。
  ///
  /// 首字母真相源为 [chatContactInitial]（百家姓映射），与 chat 联系人列表同源。
  static ({List<String> keys, Map<String, List<StartGroupFriendLetterRow>> map})
  _groupByLetter(List<StartGroupFriendLetterRow> list) {
    final map = <String, List<StartGroupFriendLetterRow>>{};
    for (final m in list) {
      final key = m.letter.isNotEmpty ? m.letter : '#';
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
        ? ChatText.startGroupChat
        : ChatText.addMember;
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
    final rowBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final rowDividerColor =
        SettingsSemanticConstants.conversationSheetDividerColor(
          isDark,
        ).withValues(alpha: 0.9);
    final sectionBandColor =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);
    final friendsWithLetter = _contacts
        .where((contact) {
          final userId = contact.userId;
          if (userId.isEmpty) {
            return false;
          }
          final normalizedQuery = _query.trim().toLowerCase();
          if (normalizedQuery.isEmpty) {
            return true;
          }
          // 拼音搜索（li→李）+ canonical userHandle，与联系人列表同源。
          return pinyinMatches(contact.displayName, normalizedQuery) ||
              contact.userHandle.toLowerCase().contains(normalizedQuery);
        })
        .map((c) {
          final displayName = c.displayName;
          return StartGroupFriendLetterRow(
            displayName: displayName,
            userId: c.userId,
            userHandle: c.userHandle,
            avatarUrl: c.avatarUrl,
            letter: chatContactInitial(displayName),
            metFrom: c.metFrom,
          );
        })
        .toList();
    final grouped = _groupByLetter(friendsWithLetter);
    final indexLetters = ['↑', ...grouped.keys];

    final letterKeys = <String, GlobalKey>{};
    for (final k in grouped.keys) {
      letterKeys[k] = GlobalKey();
    }

    // 选中成员新增时，把横向选择条滚到尾部，确保最新加入者可见。
    if (selectedMembers.length > _lastSelectedCount) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_selectedScrollController.hasClients) {
          return;
        }
        _selectedScrollController.animateTo(
          _selectedScrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        );
      });
    }
    _lastSelectedCount = selectedMembers.length;

    final listChildren = <Widget>[
      if (!selectionReady) ...[
        SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            AppRequestFeedback.inline(),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                ChatText.startGroupChatSyncingMemberState,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          ],
        ),
      ],
      if (widget.routeExtra?.hasCompanionContext ?? false)
        _CompanionContextBanner(
          rowBackground: rowBackground,
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
        ),
      // 「从群聊中选择」入口（图三微信菜单项对齐），仅在无搜索词时展示。
      if (_query.trim().isEmpty)
        _ActionEntryRow(
          icon: CupertinoIcons.group,
          title: ChatText.startGroupChatPickFromGroup,
          rowBackground: rowBackground,
          dividerColor: rowDividerColor,
          fgPrimary: fgPrimary,
          onTap: () => _pushSourcePicker(StartGroupSource.group),
        ),
      if (_query.trim().isEmpty)
        _ActionEntryRow(
          icon: CupertinoIcons.person_3,
          title: ChatText.startGroupChatPickFromCircle,
          rowBackground: rowBackground,
          dividerColor: rowDividerColor,
          fgPrimary: fgPrimary,
          onTap: () => _pushSourcePicker(StartGroupSource.circle),
        ),
      for (final letter in grouped.keys) ...[
        _ContactListSectionBand(
          key: letterKeys[letter],
          title: letter,
          color: fgSecondary,
          bandColor: sectionBandColor,
        ),
        for (var index = 0; index < grouped.map[letter]!.length; index++) ...[
          Builder(
            builder: (context) {
              final m = grouped.map[letter]![index];
              final personaId = m.userId;
              final userHandle = m.userHandle.trim();
              final selected = wizardState.isSelected(personaId);
              final locked = wizardState.isLocked(personaId);
              final pickable = StartGroupPickableMember(
                userId: personaId,
                userHandle: userHandle,
                displayName: m.displayName.isNotEmpty
                    ? m.displayName
                    : personaId,
                avatarUrl: m.avatarUrl,
              );
              return _RelatedFriendRow(
                name: m.displayName,
                memberKey: personaId,
                avatarUrl: m.avatarUrl,
                selected: selected,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                locked: locked,
                rowBackground: rowBackground,
                dividerColor: rowDividerColor,
                // 事实交集证据：认识来源（metFrom），帮助决策要不要拉入群。
                subtitle: m.metFrom,
                onTap: selectionReady && !locked
                    ? () => _toggleSelectedMember(pickable)
                    : null,
                onAvatarTap: userHandle.isEmpty
                    ? null
                    : () => context.push(
                        AppRoutePaths.userProfile(userHandle: userHandle),
                        extra: UserProfileRouteExtra(
                          personaId: personaId,
                          avatar: m.avatarUrl.isNotEmpty ? m.avatarUrl : null,
                          displayName: m.displayName.isNotEmpty
                              ? m.displayName
                              : null,
                        ),
                      ),
              );
            },
          ),
        ],
      ],
      SizedBox(height: AppSpacing.xl),
    ];

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
              placeholder: DiscoveryText.search,
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (selectedMembers.isNotEmpty)
            Padding(
              padding: EdgeInsets.fromLTRB(0, 0, 0, AppSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: listHorizontalPadding,
                    ),
                    child: Text(
                      ChatText.startGroupChatSelectedCount(
                        selectedMembers.length,
                      ),
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        fontWeight: AppTypography.medium,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs),
                  SizedBox(
                    height: AppSpacing.largeButtonSize + AppSpacing.twentyEight,
                    child: ListView.separated(
                      key: const ValueKey<String>('start-group-selected-list'),
                      controller: _selectedScrollController,
                      scrollDirection: Axis.horizontal,
                      padding: EdgeInsets.symmetric(
                        horizontal: listHorizontalPadding,
                      ),
                      itemCount: selectedMembers.length,
                      separatorBuilder: (_, _) =>
                          SizedBox(width: AppSpacing.sm),
                      itemBuilder: (context, index) {
                        final member = selectedMembers[index];
                        final userId = member.userId;
                        return _SelectedMemberAvatar(
                          key: ValueKey<String>(
                            'start-group-selected-avatar-$userId',
                          ),
                          name: member.displayName.isNotEmpty
                              ? member.displayName
                              : userId,
                          avatarUrl: member.avatarUrl,
                          onTap: () {
                            ref
                                .read(
                                  startGroupMemberWizardProvider(
                                    _wizardId,
                                  ).notifier,
                                )
                                .deselectMemberIds(<String>[userId]);
                            AppToast.show(
                              context,
                              ChatText.startGroupChatRemovedMember(
                                member.displayName.isNotEmpty
                                    ? member.displayName
                                    : userId,
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          Expanded(
            child: Stack(
              children: [
                ListView(
                  controller: _listScrollController,
                  padding: EdgeInsets.only(bottom: AppSpacing.lg),
                  children: listChildren,
                ),
                if (_isLoading)
                  Positioned.fill(child: AppRequestFeedback.section()),
                if (_query.trim().isEmpty)
                  Positioned(
                    key: const ValueKey<String>('start-group-letter-index'),
                    right: 4,
                    top: 0,
                    bottom: 0,
                    child: _LetterIndex(
                      letters: indexLetters,
                      onTap: (i) {
                        if (i == 0) {
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
                    ? AppRequestFeedback.inline()
                    : Text(
                        widget.isCreateMode
                            ? ChatText.startGroupChatActionCount(
                                selectedMembers.length,
                              )
                            : '${ChatText.addMember}（${selectedMembers.length}）',
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
