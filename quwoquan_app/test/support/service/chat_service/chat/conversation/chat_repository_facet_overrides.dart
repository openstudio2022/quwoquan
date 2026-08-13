import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';

import 'chat_repository_facets_typed_double.dart';
import 'chat_state_seed_builder.dart';
import 'conversation_state_typed_double.dart';

/// 显式覆盖七个窄 provider；禁止回退到聚合 composition provider。
List<Override> chatTestRepositoryOverrides({
  ChatTestFacets? facets,
  InMemoryChatStateEngine? engine,
  ChatStateSeed? seed,
  List<Map<String, dynamic>>? seedConversations,
  Map<String, List<Map<String, dynamic>>>? seedMembers,
  Map<String, List<Map<String, dynamic>>>? seedMessages,
  ChatInboxRepository? inbox,
  ChatConversationRepository? conversation,
  ChatMessageRepository? message,
  ChatMemberRepository? member,
  ChatContactRepository? contact,
  ChatGroupSelectionRepository? groupSelection,
  ChatGroupAdminRepository? groupAdmin,
}) {
  if (facets != null &&
      (engine != null ||
          seed != null ||
          seedConversations != null ||
          seedMembers != null ||
          seedMessages != null)) {
    throw ArgumentError('facets 不能与 engine/seed 参数同时传入');
  }
  final resolved =
      facets ??
      ChatTestFacets(
        engine: engine,
        seed: seed,
        seedConversations: seedConversations,
        seedMembers: seedMembers,
        seedMessages: seedMessages,
      );
  return <Override>[
    chatInboxRepositoryProvider.overrideWithValue(inbox ?? resolved.inbox),
    chatConversationRepositoryProvider.overrideWithValue(
      conversation ?? resolved.conversation,
    ),
    chatMessageRepositoryProvider.overrideWithValue(message ?? resolved.message),
    chatMemberRepositoryProvider.overrideWithValue(member ?? resolved.member),
    chatContactRepositoryProvider.overrideWithValue(contact ?? resolved.contact),
    chatGroupSelectionRepositoryProvider.overrideWithValue(
      groupSelection ?? resolved.groupSelection,
    ),
    chatGroupAdminRepositoryProvider.overrideWithValue(
      groupAdmin ?? resolved.groupAdmin,
    ),
  ];
}
