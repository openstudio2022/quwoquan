// ignore_for_file: unnecessary_underscores

import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/services/notification/app_message_navigation.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/greeting_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/notification_inbox_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppMessage, NotificationType;
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page_visit_recorder.dart';
import 'package:quwoquan_app/ui/chat/utils/chat_contact_initials.dart';
part 'chat_page_state.dart';

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ContactsListWithIndex extends StatefulWidget {
  const _ContactsListWithIndex({
    required this.items,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.borderColor,
    required this.rowBackgroundColor,
    required this.rowDividerColor,
    required this.sectionBandColor,
  });

  final List<ChatContactsRow> items;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color borderColor;
  final Color rowBackgroundColor;
  final Color rowDividerColor;
  final Color sectionBandColor;

  @override
  State<_ContactsListWithIndex> createState() => _ContactsListWithIndexState();
}

String _getInitial(String name) => chatContactInitial(name);

const double _kSectionHeaderHeight = AppSpacing.twenty;
const double _kContactRowHeight = AppSpacing.chatContactRowHeight;
const double _kContactAvatarSize = ChatConversationAvatarTokens.listSize;
const int _kContactIndexThreshold = 20;

class _ContactsListWithIndexState extends State<_ContactsListWithIndex> {
  final Map<String, GlobalKey> _sectionKeys = {};
  final ScrollController _scrollController = ScrollController();
  String? _activeLetter;
  Map<String, double> _sectionOffsets = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _onScroll();
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients || _sectionOffsets.isEmpty) return;
    final offset = _scrollController.offset;
    final ordered = _sectionOffsets.keys.toList()
      ..sort((a, b) => _sectionOffsets[a]!.compareTo(_sectionOffsets[b]!));
    String? current;
    for (final letter in ordered) {
      if (_sectionOffsets[letter]! <= offset + 40) current = letter;
    }
    if (current != null && current != _activeLetter && mounted) {
      setState(() => _activeLetter = current);
    }
  }

  @override
  Widget build(BuildContext context) {
    final sorted = List<ChatContactsRow>.from(widget.items);
    sorted.sort((a, b) {
      final starA = a.isStarred ? 1 : 0;
      final starB = b.isStarred ? 1 : 0;
      if (starB != starA) return starB.compareTo(starA);
      final ia = _getInitial(a.displayName);
      final ib = _getInitial(b.displayName);
      if (ia != ib) return ia.compareTo(ib);
      return a.displayName.compareTo(b.displayName);
    });
    final withInitial = <(ChatContactsRow row, String initial)>[];
    for (final row in sorted) {
      withInitial.add((row, _getInitial(row.displayName)));
    }
    final initials = <String>{};
    for (final (_, ini) in withInitial) {
      initials.add(ini);
    }
    final hasStarred = sorted.any((r) => r.isStarred);
    final allInitials = <String>[];
    if (hasStarred) allInitials.add('★');
    allInitials.addAll(initials.toList()..sort());
    for (final letter in allInitials) {
      _sectionKeys.putIfAbsent(letter, () => GlobalKey());
    }

    final listIsDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final activeIndexLetterColor = AppColorsFunctional.getColor(
      listIsDark,
      ColorType.selectionForeground,
    );

    final listChildren = <Widget>[];
    final sectionOffsets = <String, double>{};
    double pos = 0;
    String? lastInitial;
    bool lastStarred = false;
    for (final (row, initial) in withInitial) {
      final starred = row.isStarred;
      final isFirstStarred = starred && !lastStarred;
      final isFirstOfInitial = initial != lastInitial;
      if (isFirstStarred) {
        sectionOffsets['★'] = pos;
        pos += _kSectionHeaderHeight;
        final key = _sectionKeys['★'];
        if (key != null) {
          listChildren.add(
            Container(
              key: key,
              height: _kSectionHeaderHeight,
              alignment: Alignment.centerLeft,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              color: widget.sectionBandColor,
              child: Text(
                key: const ValueKey<String>('chat-contact-section-label-star'),
                ChatText.starredFriends,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
                  color: widget.fgSecondary,
                ),
              ),
            ),
          );
        }
      }
      if (!starred && isFirstOfInitial) {
        sectionOffsets[initial] = pos;
        pos += _kSectionHeaderHeight;
        final key = _sectionKeys[initial];
        if (key != null) {
          listChildren.add(
            Container(
              key: key,
              height: _kSectionHeaderHeight,
              alignment: Alignment.centerLeft,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              color: widget.sectionBandColor,
              child: Text(
                key: ValueKey<String>('chat-contact-section-label-$initial'),
                initial,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
                  color: widget.fgSecondary,
                ),
              ),
            ),
          );
        }
      }
      lastInitial = initial;
      lastStarred = starred;
      pos += _kContactRowHeight;
      final title = row.displayName;
      final avatar = row.avatarUrl;
      final subtitle = row.subtitle;
      listChildren.add(
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          onPressed: () => row.open(context),
          child: Container(
            key: ValueKey<String>('chat-contact-row-${row.id}'),
            color: widget.rowBackgroundColor,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: Column(
              children: [
                Padding(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.sm + AppSpacing.xs,
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      RoundedSquareAvatar(
                        size: _kContactAvatarSize,
                        imageUrl: avatar,
                        name: title,
                      ),
                      SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosBody,
                                      fontWeight: AppTypography.regular,
                                      color: widget.fgPrimary,
                                      height: AppTypography.lineHeightTight,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            if (subtitle.isNotEmpty) ...[
                              SizedBox(height: AppSpacing.xs),
                              Text(
                                subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: widget.fgSecondary.withValues(
                                    alpha: 0.9,
                                  ),
                                  height: AppTypography.lineHeightCompact,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: EdgeInsets.only(
                    left: ChatConversationAvatarTokens.dividerInset(
                      _kContactAvatarSize,
                    ),
                  ),
                  child: Divider(
                    key: ValueKey<String>('chat-contact-row-divider-${row.id}'),
                    height: AppSpacing.one,
                    thickness: AppSpacing.hairline,
                    color: widget.rowDividerColor,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }
    listChildren.add(SizedBox(height: AppSpacing.xl));
    _sectionOffsets = sectionOffsets;

    return Stack(
      children: [
        NotificationListener<ScrollNotification>(
          onNotification: (ScrollNotification n) {
            if (n is ScrollUpdateNotification || n is ScrollEndNotification) {
              _onScroll();
            }
            return false;
          },
          child: ListView(
            controller: _scrollController,
            padding: EdgeInsets.zero,
            children: listChildren,
          ),
        ),
        if (sorted.length > _kContactIndexThreshold)
          Positioned(
            right: 4,
            top: 0,
            bottom: 0,
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: allInitials.map((letter) {
                  final isActive = _activeLetter == letter;
                  return CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    onPressed: () {
                      setState(() => _activeLetter = letter);
                      final offset = _sectionOffsets[letter];
                      if (offset != null && _scrollController.hasClients) {
                        _scrollController.animateTo(
                          offset.clamp(
                            0.0,
                            _scrollController.position.maxScrollExtent,
                          ),
                          duration: const Duration(milliseconds: 250),
                          curve: Curves.easeOut,
                        );
                      } else {
                        final key = _sectionKeys[letter];
                        if (key?.currentContext != null) {
                          Scrollable.ensureVisible(
                            key!.currentContext!,
                            duration: const Duration(milliseconds: 250),
                            alignment: 0,
                          );
                        }
                      }
                    },
                    child: Container(
                      key: ValueKey<String>(
                        'chat-contact-index-letter-$letter',
                      ),
                      width: AppSpacing.twenty,
                      height: AppSpacing.twenty,
                      alignment: Alignment.center,
                      margin: EdgeInsets.symmetric(vertical: AppSpacing.one),
                      child: Text(
                        letter,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          fontWeight: AppTypography.semiBold,
                          color: isActive
                              ? activeIndexLetterColor
                              : widget.fgSecondary,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
      ],
    );
  }
}

class _InboxConversationTile extends StatelessWidget {
  const _InboxConversationTile({
    required this.item,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
    required this.dividerColor,
  });

  final ChatListItemViewModel item;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;
  final Color dividerColor;

  static const double _avatarSize = ChatConversationAvatarTokens.listSize;

  Widget _buildAvatar(BuildContext context) {
    return ConversationAvatar(
      conversationId: item.id,
      conversationType: item.isGroup ? 'group' : 'direct',
      title: item.title,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      size: _avatarSize,
    );
  }

  @override
  Widget build(BuildContext context) {
    final inboxTileIsDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentFg = AppColorsFunctional.getColor(
      inboxTileIsDark,
      ColorType.badgeForeground,
    );
    final subtitleColor = fgSecondary.withValues(alpha: 0.9);
    final timeColor = fgSecondary.withValues(alpha: 0.72);
    final rowBackground = item.isPinned
        ? Color.alphaBlend(fgSecondary.withValues(alpha: 0.04), backgroundColor)
        : backgroundColor;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('chat-inbox-row-${item.id}'),
        color: rowBackground,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      _buildAvatar(context),
                      if (item.hasUnread)
                        Positioned(
                          top: -4,
                          right: -4,
                          child: Container(
                            constraints: const BoxConstraints(
                              minWidth: AppSpacing.twenty,
                              minHeight: AppSpacing.twenty,
                            ),
                            padding: EdgeInsets.symmetric(
                              horizontal: item.unreadCount > 9
                                  ? AppSpacing.xs + AppSpacing.one
                                  : AppSpacing.three,
                              vertical: AppSpacing.two,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.error,
                              borderRadius: BorderRadius.circular(
                                AppSpacing.radiusNinetyNine,
                              ),
                              border: Border.all(
                                color: rowBackground,
                                width: AppSpacing.oneHalf,
                              ),
                            ),
                            child: Text(
                              item.unreadCount > 99
                                  ? '99+'
                                  : '${item.unreadCount}',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.semiBold,
                                color: onAccentFg,
                                height: AppTypography.lineHeightTight,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                item.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosBody,
                                  fontWeight: AppTypography.regular,
                                  color: fgPrimary,
                                  height: AppTypography.lineHeightTight,
                                ),
                              ),
                            ),
                            SizedBox(width: AppSpacing.sm),
                            ConstrainedBox(
                              constraints: const BoxConstraints(minWidth: 64),
                              child: Text(
                                item.timeLabel,
                                textAlign: TextAlign.right,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: timeColor,
                                  height: AppTypography.lineHeightTight,
                                ),
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Row(
                          children: [
                            if (item.previewIcon != null) ...[
                              Icon(
                                item.previewIcon,
                                size: AppSpacing.fourteen,
                                color: subtitleColor,
                              ),
                              SizedBox(width: AppSpacing.xs),
                            ],
                            Expanded(
                              child: Text(
                                item.subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: subtitleColor,
                                  height: AppTypography.lineHeightCompact,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: ChatConversationAvatarTokens.dividerInset(_avatarSize),
              ),
              child: Divider(
                key: ValueKey<String>('chat-inbox-row-divider-${item.id}'),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GreetingInboxTile extends StatelessWidget {
  const _GreetingInboxTile({
    required this.pendingCount,
    required this.latest,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
    required this.dividerColor,
    required this.onTap,
  });

  final int pendingCount;
  final GreetingRequestViewData latest;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;
  final Color dividerColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final message = latest.requestMessage?.trim();
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        color: backgroundColor,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                children: [
                  RoundedSquareAvatar(
                    size: ChatConversationAvatarTokens.listSize,
                    imageUrl: '',
                    name: ChatText.chatGreetingInboxTitle,
                    backgroundColor: AppColors.primaryColor.withValues(
                      alpha: 0.12,
                    ),
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          pendingCount > 1
                              ? '${ChatText.chatGreetingInboxTitle}（$pendingCount）'
                              : ChatText.chatGreetingInboxTitle,
                          style: TextStyle(
                            fontSize: AppTypography.iosBody,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          message != null && message.isNotEmpty
                              ? message
                              : ChatText.chatGreetingDefaultMessage,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    size: AppSpacing.iconSmall,
                    color: fgSecondary,
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: ChatConversationAvatarTokens.dividerInset(
                  ChatConversationAvatarTokens.listSize,
                ),
              ),
              child: Divider(
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 消息页`通知`维度的通知行：只渲染云端 AppMessage inbox 的
/// title/summary/时间/已读态，点击按 target 跳转并推进已读。
class _NotificationInboxTile extends StatelessWidget {
  const _NotificationInboxTile({
    required this.message,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
    required this.dividerColor,
  });

  final AppMessage message;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;
  final Color dividerColor;

  IconData get _typeIcon {
    return switch (message.messageType) {
      NotificationType.content => CupertinoIcons.doc_text,
      NotificationType.social => CupertinoIcons.person_2,
      NotificationType.circle => CupertinoIcons.circle_grid_hex,
      NotificationType.assistant => CupertinoIcons.sparkles,
      NotificationType.system => CupertinoIcons.bell,
    };
  }

  @override
  Widget build(BuildContext context) {
    final subtitleColor = fgSecondary.withValues(alpha: 0.9);
    final timeColor = fgSecondary.withValues(alpha: 0.72);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('chat-notification-row-${message.messageId}'),
        color: backgroundColor,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Container(
                        width: ChatConversationAvatarTokens.listSize,
                        height: ChatConversationAvatarTokens.listSize,
                        decoration: BoxDecoration(
                          color: fgSecondary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.radiusTen,
                          ),
                        ),
                        child: Icon(
                          _typeIcon,
                          size: AppSpacing.twentyEight,
                          color: fgSecondary,
                        ),
                      ),
                      if (!message.read)
                        Positioned(
                          top: -2,
                          right: -2,
                          child: Container(
                            width: AppSpacing.ten,
                            height: AppSpacing.ten,
                            decoration: BoxDecoration(
                              color: AppColors.error,
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: backgroundColor,
                                width: AppSpacing.oneHalf,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                message.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosBody,
                                  fontWeight: message.read
                                      ? AppTypography.regular
                                      : AppTypography.semiBold,
                                  color: fgPrimary,
                                  height: AppTypography.lineHeightTight,
                                ),
                              ),
                            ),
                            SizedBox(width: AppSpacing.sm),
                            Text(
                              ChatTimeFormatter.formatForConversationList(
                                message.createdAt,
                              ),
                              style: TextStyle(
                                fontSize: AppTypography.iosCaption1,
                                color: timeColor,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpacing.two),
                        Text(
                          message.summary,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: subtitleColor,
                            height: AppTypography.lineHeightTight,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Container(
              margin: EdgeInsets.only(
                left:
                    ChatConversationAvatarTokens.listSize +
                    ChatConversationAvatarTokens.leadingGap,
              ),
              height: AppSpacing.hairline,
              color: dividerColor,
            ),
          ],
        ),
      ),
    );
  }
}
