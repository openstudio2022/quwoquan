import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_personalization_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantPersonalizationFacet
    implements AssistantPersonalizationFacade {
  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    return PageContextReceipt(
      accepted: true,
      contextKey:
          'fixture:${assistantPageTypeForSource(context.source).wireName}',
      expiresAt: DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 5))
          .toIso8601String(),
    );
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) async {
    final pageType = assistantPageTypeForSource(context.source);
    final welcome = switch (pageType) {
      AssistantPageContextType.chat => '我可以结合当前会话帮你整理话题、找资料或写回复。',
      AssistantPageContextType.search => '我可以把站内结果、网页线索和你的上下文串起来。',
      AssistantPageContextType.create => '我可以帮你找灵感、配文案或整理发布计划。',
      AssistantPageContextType.home => '我可以结合当前主页、关系和交集帮你解释信息。',
      _ => '有什么想让我帮忙的？',
    };
    return AssistantEntryResponse(
      welcomeMessage: welcome,
      suggestionLines: const <String>['说一句你想做的事，或选上面的推荐试试'],
      chips: const <AssistantEntryChip>[
        AssistantEntryChip(
          chipId: 'find',
          label: '帮我找',
          actionType: 'command',
          value: 'find',
        ),
        AssistantEntryChip(
          chipId: 'remember',
          label: '帮我记',
          actionType: 'command',
          value: 'remember',
        ),
        AssistantEntryChip(
          chipId: 'share',
          label: '帮我分享',
          actionType: 'command',
          value: 'share',
        ),
      ],
      actions: const <AssistantEntryAction>[],
      personalized: false,
    );
  }
}
