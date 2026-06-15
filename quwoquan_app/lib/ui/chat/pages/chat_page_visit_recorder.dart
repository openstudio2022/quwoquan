import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void recordChatPageVisit(WidgetRef ref, int mainTabIndex, int subTabIndex) {
  final pageId = mainTabIndex == 0
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
  ref.read(visitRecorderServiceProvider).recordVisit(VisitTarget.page(pageId));
}
