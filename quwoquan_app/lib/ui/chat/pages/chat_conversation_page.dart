import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/conversation/conversation_page_scaffold.dart';
import 'package:quwoquan_app/components/conversation/conversation_timeline.dart';
import 'package:quwoquan_app/components/conversation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/components/input/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/rtc/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/microphone_permission_guard.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_send_outbox.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_player_manager.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/chat/models/chat_message_media_view_data.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_mention_picker.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';

part 'chat_conversation_page_actions.dart';
part 'chat_conversation_page_selection_actions.dart';

String formatChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  return raw;
}

final RouteObserver<ModalRoute<Object?>> chatRouteObserver =
    RouteObserver<ModalRoute<Object?>>();

class ChatConversationPage extends ConsumerStatefulWidget {
  const ChatConversationPage({
    super.key,
    required this.conversationId,
    required this.onBack,
    this.searchAnchorContext,
    this.embedded = false,
  });

  final String conversationId;
  final VoidCallback onBack;
  final SearchConversationAnchorContext? searchAnchorContext;
  final bool embedded;

  @override
  ConsumerState<ChatConversationPage> createState() =>
      _ChatConversationPageState();
}

class _ChatConversationPageState extends _ChatConversationPageActionsState
    with RouteAware {
  @override
  void initState() {
    super.initState();
    _inputController.addListener(_onInputChanged);
    _scrollController.addListener(_onTimelineScroll);
    _realtimeNotifier = ref.read(realtimeConnectionManagerProvider.notifier);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_bootstrapConversation(widget.conversationId));
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _subscribeRouteAware();
  }

  @override
  void dispose() {
    final route = _subscribedRoute;
    if (route != null) {
      chatRouteObserver.unsubscribe(this);
      _subscribedRoute = null;
    }
    _detachRealtime();
    AppToast.dismiss();
    unawaited(_voiceRecorder.dispose());
    _inputController.removeListener(_onInputChanged);
    _scrollController.removeListener(_onTimelineScroll);
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  Future<void> _bootstrapConversation(String conversationId) async {
    final notifier = ref.read(chatMessageProvider(conversationId).notifier);
    final telemetryTracker = ref.read(chatInteractionTelemetryTrackerProvider);
    await notifier.loadMessages();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    });
    final marked = await notifier.markConversationRead();
    unawaited(
      telemetryTracker.track(
        action: ChatInteractionAction.readWatermark,
        outcome: marked
            ? ChatInteractionOutcome.succeeded
            : ChatInteractionOutcome.failed,
        watermarkResult: marked
            ? ChatWatermarkResult.advanced
            : ChatWatermarkResult.failed,
        pageName: PageNames.chatDetail,
        surfaceId: AppUiSurfaces.chatDetail.id,
      ),
    );
    if (!marked || !mounted) {
      return;
    }
    // 会话列表页 keepAlive 仍在树上；已读回写须在当前帧结束后执行。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      refreshMessageReadState(ref, conversationId);
    });
  }

  void _onTimelineScroll() {
    if (!_scrollController.hasClients || !mounted) return;
    final position = _scrollController.position;
    if (position.extentBefore > AppSpacing.xl * 2) return;
    final messageState = ref.read(chatMessageProvider(widget.conversationId));
    if (!messageState.hasMore || messageState.isLoadingOlder) return;
    final previousMaxExtent = position.maxScrollExtent;
    final previousOffset = position.pixels;
    unawaited(() async {
      final added = await ref
          .read(chatMessageProvider(widget.conversationId).notifier)
          .loadOlderMessages();
      if (!mounted || added <= 0) return;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scrollController.hasClients) return;
        final delta =
            _scrollController.position.maxScrollExtent - previousMaxExtent;
        _scrollController.jumpTo(
          (previousOffset + delta).clamp(
            _scrollController.position.minScrollExtent,
            _scrollController.position.maxScrollExtent,
          ),
        );
      });
    }());
  }

  void _subscribeRouteAware() {
    if (widget.embedded || !mounted) {
      return;
    }
    final route = ModalRoute.of(context);
    if (route == null || _subscribedRoute == route) {
      return;
    }
    final previousRoute = _subscribedRoute;
    if (previousRoute != null) {
      chatRouteObserver.unsubscribe(this);
    }
    _subscribedRoute = route;
    chatRouteObserver.subscribe(this, route);
  }

  void _attachRealtime() {
    if (_realtimeAttached) {
      return;
    }
    final notifier = _realtimeNotifier;
    if (notifier == null) {
      return;
    }
    _realtimeAttached = true;
    scheduleMicrotask(
      () => notifier.onEnterConversation(widget.conversationId),
    );
  }

  void _detachRealtime() {
    if (!_realtimeAttached) {
      return;
    }
    _realtimeAttached = false;
    final notifier = _realtimeNotifier;
    if (notifier == null) {
      return;
    }
    scheduleMicrotask(notifier.onLeaveConversation);
  }

  @override
  void didPush() {
    _attachRealtime();
  }

  @override
  void didPopNext() {
    _attachRealtime();
  }

  @override
  void didPushNext() {
    _detachRealtime();
  }

  @override
  void didPop() {
    _detachRealtime();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final memberState = _isGroupChat
        ? ref.watch(conversationMembersProvider(widget.conversationId))
        : null;
    final mentionDisplayNames = <String, String>{
      if (memberState != null)
        for (final member in memberState.members)
          member.userId: member.displayName,
    };
    final currentUserId = ref.watch(currentUserIdProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final chatListBg = isDark ? bgColor : AppColors.chatBackground;
    final messageState = ref.watch(chatMessageProvider(widget.conversationId));
    final mediaEndpointConfig = ref.watch(mediaEndpointConfigProvider);
    final displayMessages = messageState.messages
        .map(
          (dto) => dto.toDisplayItem(
            currentUserId: currentUserId,
            mediaEndpointConfig: mediaEndpointConfig,
          ),
        )
        .toList();
    final voiceSendState = ref.watch(voiceSendProvider(widget.conversationId));
    final timelinePadding = EdgeInsets.symmetric(
      horizontal:
          AppSpacing.semantic[DesignSemanticConstants
              .container]?[DesignSemanticConstants.sm] ??
          AppSpacing.containerSm,
      vertical: AppSpacing.md,
    );
    final actionMenuOverlay =
        _actionMenuMessage != null && _actionMenuPosition != null
        ? ConversationMessageActionMenuOverlay(
            message: _actionMenuMessage!,
            position: _actionMenuPosition!,
            onAction: _onMessageAction,
            onClose: () => setState(() {
              _actionMenuMessage = null;
              _actionMenuPosition = null;
            }),
          )
        : null;

    // 时间分隔降噪：仅首条与「距上次展示时间 ≥ 阈值」处居中显示，避免连续
    // 消息每分钟都插一条时间，导致密集分隔（深浅色与移动端一致）。
    final showTimeFlags = _computeTimeSeparatorFlags(displayMessages);

    final bodyContent = Column(
      children: [
        if (widget.searchAnchorContext case final anchor?)
          _SearchAnchorBanner(sourceQuery: anchor.sourceQuery, isDark: isDark),
        Expanded(
          child: messageState.isLoading && displayMessages.isEmpty
              ? AppRequestFeedback.section()
              : messageState.error != null && displayMessages.isEmpty
              ? AppPageErrorState(
                  semantic: runtimeErrorSemantic(
                    context,
                    error: messageState.error!,
                    category: UiErrorCategory.pageLoad,
                    scope: UiErrorScope.page,
                  ),
                  onRecovery: (action) async {
                    if (action.type == UiErrorActionType.retry ||
                        action.type == UiErrorActionType.resubmit) {
                      await ref
                          .read(
                            chatMessageProvider(widget.conversationId).notifier,
                          )
                          .loadMessages();
                      final refreshed = ref.read(
                        chatMessageProvider(widget.conversationId),
                      );
                      return refreshed.error == null
                          ? UiRecoveryOutcome.recovered
                          : UiRecoveryOutcome.stillBlocked;
                    }
                    return UiRecoveryOutcome.cancelled;
                  },
                )
              : displayMessages.isEmpty
              ? Center(
                  child: Padding(
                    padding: EdgeInsets.all(AppSpacing.xl),
                    child: Text(
                      ChatText.chatConversationNoMessages,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        color: fgPrimary.withValues(alpha: 0.65),
                      ),
                    ),
                  ),
                )
              : ConversationTimeline(
                  controller: _scrollController,
                  backgroundColor: chatListBg,
                  padding: timelinePadding,
                  itemCount: displayMessages.length,
                  itemBuilder: (context, index) {
                    final msg = displayMessages[index];
                    final showTime = showTimeFlags[index];
                    final timeStr = formatChatTime(msg.timestampLabel);
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (showTime && timeStr.isNotEmpty)
                          Padding(
                            padding: EdgeInsets.only(
                              bottom:
                                  AppSpacing.semantic[DesignSemanticConstants
                                      .intraGroup]?[DesignSemanticConstants
                                      .sm] ??
                                  AppSpacing.intraGroupSm,
                            ),
                            child: Center(
                              child: Text(
                                timeStr,
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: fgPrimary.withValues(alpha: 0.5),
                                ),
                              ),
                            ),
                          ),
                        ChatMessageBubble(
                          message: msg,
                          isRight: msg.isSelf,
                          bubbleColor: msg.isSelf
                              ? AppColors.chatBubbleOutgoing
                              : AppColors.chatBubbleIncoming,
                          textColor: msg.isSelf ? AppColors.white : fgPrimary,
                          isSelectionMode: _isSelectionMode,
                          isSelected: _selectedIds.contains(msg.id),
                          onLongPressStart: (details) =>
                              _onLongPressMessage(msg, details.globalPosition),
                          onTap: _isSelectionMode
                              ? () => _toggleSelect(msg.id)
                              : msg.type == 'system_call_log'
                              ? () => unawaited(
                                  _initiateCall(_callTypeFromLog(msg)),
                                )
                              : null,
                          hideAvatarAndName: msg.type == 'system_call_log',
                          useFullWidth: msg.type == 'system_call_log',
                          receiptEnabled: false,
                          memberCount: _memberCount,
                          mentionDisplayNames: mentionDisplayNames,
                          onMentionTap: _openMentionProfile,
                          onAvatarTap: () {
                            final senderId = msg.senderId;
                            if (msg.isSelf) {
                              final currentUser = ref.read(userDataProvider);
                              final userHandle =
                                  currentUser?.userHandle?.trim() ?? '';
                              if (userHandle.isNotEmpty) {
                                context.push(
                                  AppRoutePaths.userProfile(
                                    userHandle: userHandle,
                                  ),
                                );
                              }
                            } else if (senderId.isNotEmpty) {
                              final userHandle = _memberUserHandle(senderId);
                              if (userHandle.isNotEmpty) {
                                context.push(
                                  AppRoutePaths.userProfile(
                                    userHandle: userHandle,
                                  ),
                                  extra: UserProfileRouteExtra(
                                    personaId: senderId,
                                  ),
                                );
                              }
                            }
                          },
                        ),
                      ],
                    );
                  },
                ),
        ),
        ColoredBox(
          color: isDark ? bgColor : AppColors.chatToolbarBackground,
          child: SafeArea(
            top: false,
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.semantic[DesignSemanticConstants
                        .container]?[DesignSemanticConstants.sm] ??
                    AppSpacing.containerSm,
                AppSpacing.chatInputToolbarVerticalPadding,
                AppSpacing.semantic[DesignSemanticConstants
                        .container]?[DesignSemanticConstants.sm] ??
                    AppSpacing.containerSm,
                AppSpacing.chatInputToolbarVerticalPadding,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_isBlockedConversation)
                    _buildBlockedConversationHintBar(),
                  if (!_isGroupChat &&
                      !_isBlockedConversation &&
                      _relationshipCapability?.isMutual != true &&
                      _relationshipCapability?.isBlocked != true &&
                      _relationshipCapability?.isBlockedBy != true &&
                      _otherParticipantId != null)
                    _buildMutualFollowRtcHintBar(),
                  _buildVoiceSendStatusBar(voiceSendState),
                  CustomizableChatInputBar(
                    controller: _inputController,
                    focusNode: _inputFocusNode,
                    textFieldKey: TestKeys.chatInputTextField,
                    sendButtonKey: TestKeys.chatInputSendButton,
                    maxTextLength: 5000,
                    maxVisibleLines: 5,
                    onPickImages: _pickChatImages,
                    onCapturePhoto: _captureChatPhoto,
                    onPickFiles: _pickChatFiles,
                    onRequestMicPermission: _requestMicPermissionForChat,
                    onStartRecord: _startVoiceRecordForChat,
                    onStopRecord: _stopVoiceRecordForChat,
                    onCancelRecord: _cancelVoiceRecordForChat,
                    voiceAmplitudeStream: _voiceRecorder.onAmplitude,
                    onSend: _submitChatInput,
                    onMentionRequested: _requestChatMention,
                    enableVoiceInput: true,
                    showEmojiButton: true,
                    showXiaoquMentionButton: _isGroupChat,
                    disabled: _shouldDisableComposer,
                    extraPanelItems: _buildCallPanelItems(),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );

    return ConversationPageScaffold(
      embedded: widget.embedded,
      backgroundColor: bgColor,
      navigationBar: widget.embedded
          ? null
          : AppNavigationBar(
              backgroundColor: bgColor,
              leading: AppNavigationBarIconButton(
                icon: _isSelectionMode
                    ? CupertinoIcons.xmark
                    : CupertinoIcons.back,
                onPressed: _isSelectionMode ? _cancelSelection : widget.onBack,
              ),
              middle: _buildConversationHeader(isDark),
              trailing: _isSelectionMode
                  ? AppNavigationBarTextAction(
                      label: ChatText.messageActionForward,
                      onPressed: () async {
                        final selectedMessages = displayMessages
                            .where((item) => _selectedIds.contains(item.id))
                            .toList(growable: false);
                        await _shareMessages(selectedMessages);
                        _cancelSelection();
                      },
                    )
                  : AppNavigationBarIconButton(
                      icon: CupertinoIcons.ellipsis,
                      onPressed: () => context.push(
                        AppRoutePaths.chatSettings(id: widget.conversationId),
                      ),
                    ),
            ),
      body: WebPageMaxWidthFrame(sideColor: bgColor, child: bodyContent),
      overlays: actionMenuOverlay == null
          ? const <Widget>[]
          : <Widget>[actionMenuOverlay],
    );
  }

  Widget _buildConversationHeader(bool isDark) {
    if (_isSelectionMode) {
      return Text(
        ChatText.selectedMessagesCount(_selectedIds.length),
        style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
      );
    }
    final intersectionText = _conversationDto
        ?.originIntersectionSnapshot
        ?.primaryText
        .trim();
    if (intersectionText == null || intersectionText.isEmpty) {
      return Text(
        _conversationTitle,
        style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          _conversationTitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        Text(
          intersectionText,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }

  /// 计算每条消息是否需要在其上方居中展示时间分隔。
  ///
  /// 规则：首条恒展示；其余仅当与「上一次展示时间的消息」间隔 ≥ [_timeSeparatorGap]
  /// 时展示。缺少可解析 ISO 时间戳时回退到旧的「标签变化」规则，保证健壮。
  List<bool> _computeTimeSeparatorFlags(List<ChatMessageDisplayItem> items) {
    final flags = List<bool>.filled(items.length, false, growable: false);
    DateTime? lastShown;
    String? lastLabel;
    for (var i = 0; i < items.length; i++) {
      final item = items[i];
      final sentAt = DateTime.tryParse(item.sentAtIso);
      if (sentAt == null) {
        final changed = i == 0 || item.timestampLabel != lastLabel;
        flags[i] = changed;
        if (changed) {
          lastLabel = item.timestampLabel;
        }
        continue;
      }
      if (lastShown == null ||
          (sentAt.difference(lastShown)).abs() >= _timeSeparatorGap) {
        flags[i] = true;
        lastShown = sentAt;
        lastLabel = item.timestampLabel;
      }
    }
    return flags;
  }

  static const Duration _timeSeparatorGap = Duration(minutes: 5);
}

class _SearchAnchorBanner extends StatelessWidget {
  const _SearchAnchorBanner({required this.sourceQuery, required this.isDark});

  final String? sourceQuery;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primaryColor.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(
            color: AppColors.primaryColor.withValues(alpha: 0.18),
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Icon(
                CupertinoIcons.scope,
                size: AppSpacing.iconSmall,
                color: AppColors.primaryColor,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  sourceQuery == null || sourceQuery!.isEmpty
                      ? ChatText.searchEntry
                      : ChatText.searchEntryForQuery(sourceQuery!),
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: fgPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
