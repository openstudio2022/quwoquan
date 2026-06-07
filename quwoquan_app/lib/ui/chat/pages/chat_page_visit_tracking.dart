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
    ref.read(visitRecorderServiceProvider).recordVisit(
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
            1 => 'chat_messages_at_me',
            2 => 'chat_messages_at_xiaoqu',
            3 => 'chat_messages_unread',
            4 => 'chat_messages_reminders',
            _ => 'chat_messages_secret',
          }
        : switch (subTabIndex) {
            0 => 'chat_contacts_all',
            1 => 'chat_contacts_circles',
            2 => 'chat_contacts_mutual',
            _ => 'chat_contacts_groups',
          };
  }

  static const List<String> _messageSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.atMe,
    UITextConstants.atXiaoqu,
    UITextConstants.unread,
    UITextConstants.reminders,
    UITextConstants.secretMessage,
  ];

  static const List<String> _contactsSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.contactsTabCircles,
    UITextConstants.contactsTabMutualFollow,
    UITextConstants.contactsTabFunGroup,
  ];
}
