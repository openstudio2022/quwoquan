import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void recordChatPageVisit(
  WidgetRef ref,
  int mainTabIndex,
  int subTabIndex,
) {
  final pageId = mainTabIndex == 0
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
  ref.read(visitRecorderServiceProvider).recordVisit(
        VisitTarget.page(pageId),
      );
}
