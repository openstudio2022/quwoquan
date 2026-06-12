import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

mixin ChatPageVisitTrackingMixin<T extends ConsumerStatefulWidget>
    on ConsumerState<T> {
  int get chatPageMainTabIndex;
  int get chatPageSubTabIndex;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        recordChatPageVisit();
      }
    });
  }

  void recordChatPageVisit() {
    ref
        .read(visitRecorderServiceProvider)
        .recordVisit(
          VisitTarget.page(
            _chatPageVisitTargetId(chatPageMainTabIndex, chatPageSubTabIndex),
          ),
        );
  }

  List<String> chatPageSecondaryTabsFor(int mainTabIndex) =>
      mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;

  String _chatPageVisitTargetId(int mainTabIndex, int subTabIndex) {
    return mainTabIndex == 0
        ? switch (subTabIndex) {
            0 => 'chat_messages_all',
            1 => 'chat_messages_unread',
            2 => 'chat_messages_group',
            3 => 'chat_messages_direct',
            _ => 'chat_messages_notification',
          }
        : switch (subTabIndex) {
            0 => 'chat_contacts_all',
            1 => 'chat_contacts_mutual',
            2 => 'chat_contacts_circles',
            _ => 'chat_contacts_groups',
          };
  }

  static const List<String> _messageSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.unread,
    UITextConstants.groupChat,
    UITextConstants.chatPrivateMessages,
    UITextConstants.chatNotifications,
  ];

  static const List<String> _contactsSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.contactsTabMutualFollow,
    UITextConstants.contactsTabCircles,
    UITextConstants.contactsTabGroups,
  ];
}
