import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_sheet.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/runtime/di/chat_content_presentation_slots.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_upload_queue.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/conversation_page_scaffold.dart';
import 'package:quwoquan_app/design_system/chat/conversation_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/message_action_menu_overlay.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/message_receipt_sheet.dart';
import 'package:quwoquan_app/design_system/chat/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/runtime/di/rtc_call_entry_dependencies.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/semantics/design_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/permissions/microphone_permission_guard.dart';
import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_conversation_performance_observability_provider.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_conversation_lifecycle.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_send_outbox_control.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_mention_picker.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_bubble.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_voice_recorder.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ChatGetMessageReceiptsQuery,
        ChatListConversationMembersQuery,
        ChatMessageReceipt;
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';

part 'chat_conversation_page_actions.dart';
part 'chat_conversation_page_media_actions.part.dart';
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
    ref
        .read(chatConversationPerformanceObservabilityProvider)
        .markConversationOpened(widget.conversationId);
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
    final notifier = ref.read(
      chatMessageTimelineControllerProvider(conversationId),
    );
    final telemetryTracker = ref.read(chatInteractionTelemetryTrackerProvider);
    await notifier.loadMessages();
    if (mounted) {
      ref
          .read(chatConversationPerformanceObservabilityProvider)
          .markFirstTimelineReady(
            conversationId,
            messageCount: ref
                .read(chatMessageTimelineProvider(conversationId))
                .messages
                .length,
          );
    }
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
      refreshConversationMessageReadState(ref, conversationId);
    });
  }

  void _onTimelineScroll() {
    if (!_scrollController.hasClients || !mounted) return;
    final position = _scrollController.position;
    if (position.extentBefore > AppSpacing.xl * 2) return;
    final messageState = ref.read(
      chatMessageTimelineProvider(widget.conversationId),
    );
    if (!messageState.hasMore || messageState.isLoadingOlder) return;
    final previousMaxExtent = position.maxScrollExtent;
    final previousOffset = position.pixels;
    unawaited(() async {
      final added = await ref
          .read(chatMessageTimelineControllerProvider(widget.conversationId))
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
    final chatListBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.chatListBackground,
    );
    final messageState = ref.watch(
      chatMessageTimelineProvider(widget.conversationId),
    );
    final mediaEndpointConfig = ref.watch(mediaEndpointConfigProvider);
    final displayMessages = messageState.messages
        .map(
          (dto) => dto.toDisplayItem(
            currentUserId: currentUserId,
            mediaEndpointConfig: mediaEndpointConfig,
            peerReadSeq: messageState.peerReadSeq,
          ),
        )
        .toList();
    final voiceSendState = ref.watch(
      chatVoiceSendStateProvider(widget.conversationId),
    );
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
            receiptEnabled: _conversationDto?.receiptEnabled ?? false,
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
        // 离线只读来源必须与刷新失败可区分并驱动展示（reliability REQ-003）。
        if (messageState.source == ChatTimelineContentSource.offlineReadOnly)
          _OfflineReadOnlyBanner(isDark: isDark),
        Expanded(
          child: messageState.isLoading && displayMessages.isEmpty
              ? const AppSkeletonListRows(rowCount: 6)
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
                            chatMessageTimelineControllerProvider(
                              widget.conversationId,
                            ),
                          )
                          .loadMessages();
                      final refreshed = ref.read(
                        chatMessageTimelineProvider(widget.conversationId),
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
                        if (msg.replyToMessageId case final quotedId?)
                          _QuotedMessageBlock(
                            quoted: _findDisplayMessage(
                              displayMessages,
                              quotedId,
                            ),
                            isRight: msg.isSelf,
                            isDark: isDark,
                          ),
                        ChatMessageBubble(
                          message: msg,
                          isRight: msg.isSelf,
                          bubbleColor: msg.isSelf
                              ? AppColors.chatBubbleOutgoing
                              : AppColorsFunctional.getColor(
                                  isDark,
                                  ColorType.chatBubbleIncoming,
                                ),
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
                              : msg.type == 'file'
                              ? () => unawaited(_openFileMessage(msg))
                              : msg.type == 'video'
                              ? () => _openVideoMessage(msg)
                              : msg.type == 'image'
                              ? () => _openImageMessage(msg)
                              : null,
                          hideAvatarAndName: msg.type == 'system_call_log',
                          useFullWidth: msg.type == 'system_call_log',
                          receiptEnabled:
                              _conversationDto?.receiptEnabled ?? false,
                          memberCount: _memberCount,
                          mentionDisplayNames: mentionDisplayNames,
                          onMentionTap: _openMentionProfile,
                          onRetrySend: msg.status == 'failed'
                              ? () => unawaited(_retryFailedMessage(msg))
                              : null,
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
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.chatToolbarBackground,
          ),
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
                  if (_replyToTarget case final replyTarget?)
                    _ReplyComposerPreviewBar(
                      target: replyTarget,
                      isDark: isDark,
                      onCancel: () => setState(() => _replyToTarget = null),
                    ),
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
    // 交集常驻只在 1v1 会话头；群会话头部不得展示交集
    //（intersection-native-messaging REQ-003 / header REQ-001）。
    // 破冰快照优先；非破冰会话回退云侧常驻交集摘要首条（≤2 条读面事实）。
    var intersectionText = _isGroupChat
        ? null
        : _conversationDto?.originIntersectionSnapshot?.primaryText.trim();
    if (!_isGroupChat &&
        (intersectionText == null || intersectionText.isEmpty)) {
      final facts = _conversationDto?.intersectionFacts;
      if (facts != null && facts.isNotEmpty) {
        intersectionText = facts.first.primaryText.trim();
      }
    }
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

ChatMessageDisplayItem? _findDisplayMessage(
  List<ChatMessageDisplayItem> messages,
  String messageId,
) {
  for (final message in messages) {
    if (message.id == messageId) {
      return message;
    }
  }
  return null;
}

/// 被引用消息的单行摘要：文本取内容，媒体走既有类型占位文案。
String _quotedMessageSummary(ChatMessageDisplayItem? quoted) {
  if (quoted == null) {
    return ChatText.chatReplyOriginalUnavailable;
  }
  if (quoted.status == 'recalled') {
    return ChatText.chatReplyOriginalUnavailable;
  }
  return switch (quoted.type) {
    'image' => ChatText.chatPreviewImage,
    'video' => ChatText.chatPreviewVideo,
    'audio' => ChatText.chatPreviewVoice,
    _ => quoted.content,
  };
}

/// 输入栏上方的引用回复预览条（可取消）。
class _ReplyComposerPreviewBar extends StatelessWidget {
  const _ReplyComposerPreviewBar({
    required this.target,
    required this.isDark,
    required this.onCancel,
  });

  final ChatMessageDisplayItem target;
  final bool isDark;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final summary = _quotedMessageSummary(target);
    return Padding(
      key: const ValueKey<String>('chat-reply-composer-preview'),
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fgSecondary.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Row(
            children: [
              Icon(
                CupertinoIcons.arrowshape_turn_up_left,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  target.senderName.isEmpty
                      ? summary
                      : '${target.senderName}: $summary',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                ),
              ),
              CupertinoButton(
                key: const ValueKey<String>('chat-reply-composer-cancel'),
                padding: EdgeInsets.zero,
                minimumSize: Size.square(AppSpacing.iconMedium),
                onPressed: onCancel,
                child: Icon(
                  CupertinoIcons.xmark_circle_fill,
                  size: AppSpacing.iconSmall,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 气泡上方的被引用消息块：只展示单行摘要，原消息不可用时诚实占位。
class _QuotedMessageBlock extends StatelessWidget {
  const _QuotedMessageBlock({
    required this.quoted,
    required this.isRight,
    required this.isDark,
  });

  final ChatMessageDisplayItem? quoted;
  final bool isRight;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final summary = _quotedMessageSummary(quoted);
    final label = quoted == null || quoted!.senderName.isEmpty
        ? summary
        : '${quoted!.senderName}: $summary';
    return Padding(
      padding: EdgeInsets.only(
        left: isRight ? 0 : AppSpacing.xl * 2,
        right: isRight ? AppSpacing.xl * 2 : 0,
        bottom: AppSpacing.two,
      ),
      child: Row(
        mainAxisAlignment: isRight
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        children: [
          Flexible(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: fgSecondary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
              ),
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.intraGroupSm,
                  vertical: AppSpacing.two,
                ),
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
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

/// 离线只读提示条：时间线内容来自本机副本且本次远端刷新失败时展示。
class _OfflineReadOnlyBanner extends StatelessWidget {
  const _OfflineReadOnlyBanner({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      key: const ValueKey<String>('chat-timeline-offline-readonly-banner'),
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fgSecondary.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Icon(
                CupertinoIcons.wifi_slash,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Expanded(
                child: Text(
                  ChatText.chatTimelineOfflineReadOnlyHint,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
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
