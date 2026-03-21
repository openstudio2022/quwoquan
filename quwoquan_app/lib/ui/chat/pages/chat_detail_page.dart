import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';

/// Backward-compatible entrypoint for IM conversation detail.
///
/// Assistant conversations are now owned by `ui/assistant`.
class ChatDetailPage extends StatelessWidget {
  const ChatDetailPage({
    super.key,
    required this.conversationId,
    required this.onBack,
    this.assistantOpenContext,
    this.embedded = false,
  }) : assert(
         conversationId != AppConceptConstants.assistantConversationId,
         'Assistant conversations must use AssistantConversationPage.',
       );

  final String conversationId;
  final VoidCallback onBack;
  final AssistantOpenContext? assistantOpenContext;
  final bool embedded;

  @override
  Widget build(BuildContext context) {
    return ChatConversationPage(
      conversationId: conversationId,
      onBack: onBack,
      embedded: embedded,
    );
  }
}
