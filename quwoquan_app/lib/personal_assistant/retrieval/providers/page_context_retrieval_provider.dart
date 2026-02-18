import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/privacy_policy.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_models.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_provider.dart';

class PageContextRetrievalProvider implements AssistentRetrievalProvider {
  const PageContextRetrievalProvider(this._repository);

  final AppContentRepository _repository;

  @override
  String get providerId => 'page_context';

  @override
  List<String> get capabilityIds => const <String>[
        AssistentCapabilityCatalog.currentPage,
        AssistentCapabilityCatalog.pageComments,
        AssistentCapabilityCatalog.behaviorTimeline,
      ];

  @override
  Future<AssistentRetrievalResult> retrieve(AssistentRetrievalRequest request) async {
    final scope = request.contextScopeHint;
    final pageType = (scope['pageType'] as String?)?.trim() ?? 'chat';
    final policy = AssistentPrivacyPolicy.fromInputs(
      privacyProfile: request.privacyProfile,
      contextScopeHint: <String, dynamic>{
        ...scope,
        'privacyPolicy': request.privacyPolicy,
      },
      fallbackCapabilities: request.requestedCapabilities,
    );
    if (!policy.allowsPageType(pageType)) {
      return AssistentRetrievalResult(
        success: false,
        message: '隐私策略不允许读取 $pageType 页面上下文。',
        providersUsed: const <String>['page_context'],
        errorCode: 'privacy_page_blocked',
      );
    }
    final items = _buildPageItems(pageType: pageType, scope: scope, query: request.query);
    if (items.isEmpty) {
      return AssistentRetrievalResult(
        success: false,
        message: '当前页面暂未产出可用上下文。',
        providersUsed: const <String>['page_context'],
        degraded: false,
      );
    }
    return AssistentRetrievalResult(
      success: true,
      message: '已提取$pageType 页面上下文。',
      items: items,
      providersUsed: const <String>['page_context'],
      coverageScore: items.length >= 2 ? 0.8 : 0.55,
      conflictScore: 0.0,
    );
  }

  List<AssistentRetrievalItem> _buildPageItems({
    required String pageType,
    required Map<String, dynamic> scope,
    required String query,
  }) {
    final results = <AssistentRetrievalItem>[];
    switch (pageType) {
      case 'discovery':
        final cards = <Map<String, dynamic>>[
          ..._repository.discoveryMomentData.take(2),
          ..._repository.discoveryArticleData.take(1),
          ..._repository.discoveryVideoData.take(1),
        ];
        for (final item in cards) {
          final text = _firstNonEmpty(
            item['content']?.toString(),
            item['title']?.toString(),
            item['caption']?.toString(),
          );
          if (text.isEmpty) continue;
          results.add(
            AssistentRetrievalItem(
              content: text,
              sourceType: 'page.discovery',
              sourceId: item['id']?.toString() ?? 'discovery_item',
              relevance: _relevance(text, query),
            ),
          );
        }
        break;
      case 'circles':
        for (final circle in _repository.circlesMockCircles.take(3)) {
          final name = circle['name']?.toString() ?? '';
          final desc = circle['description']?.toString() ?? '';
          final text = _firstNonEmpty('$name $desc', name);
          if (text.isEmpty) continue;
          results.add(
            AssistentRetrievalItem(
              content: text,
              sourceType: 'page.circles',
              sourceId: circle['id']?.toString() ?? 'circle_item',
              relevance: _relevance(text, query),
            ),
          );
        }
        break;
      case 'create':
        final hints = (scope['hints'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};
        final createSummary = <String>[
          '创作页当前状态',
          if (hints['hasAddedMedia'] == true) '已添加媒体',
          if (hints['hasDraft'] == true) '存在草稿',
          if (hints['channelCount'] != null) '已选渠道:${hints['channelCount']}',
          if (hints['optimizeAction'] != null) '最近优化:${hints['optimizeAction']}',
        ].join('，');
        results.add(
          AssistentRetrievalItem(
            content: createSummary,
            sourceType: 'page.create',
            sourceId: 'create_state',
            relevance: 0.7,
          ),
        );
        break;
      case 'home':
        final homeSummary = <String>[
          '主页实体上下文',
          if (scope['entityId'] != null) '实体:${scope['entityId']}',
          if (scope['tab'] != null) '当前页签:${scope['tab']}',
        ].join('，');
        results.add(
          AssistentRetrievalItem(
            content: homeSummary,
            sourceType: 'page.home',
            sourceId: 'home_state',
            relevance: 0.65,
          ),
        );
        break;
      case 'chat':
      default:
        final conversationId = scope['sessionId']?.toString() ?? 'assistant';
        final chatMessages = _repository.chatMessagesFor(conversationId).take(4);
        for (final message in chatMessages) {
          final text = (message['content'] as String?)?.trim() ?? '';
          if (text.isEmpty) continue;
          results.add(
            AssistentRetrievalItem(
              content: text,
              sourceType: 'page.chat',
              sourceId: message['id']?.toString() ?? 'chat_message',
              relevance: _relevance(text, query),
            ),
          );
        }
        break;
    }

    final behaviorTimeline = (scope['behaviorTimeline'] as List?)
            ?.whereType<Map>()
            .take(3)
            .map((entry) => entry['action']?.toString() ?? '')
            .where((action) => action.trim().isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (behaviorTimeline.isNotEmpty) {
      results.add(
        AssistentRetrievalItem(
          content: '近期行为：${behaviorTimeline.join(' -> ')}',
          sourceType: 'behavior.timeline',
          sourceId: 'behavior_timeline',
          relevance: 0.6,
        ),
      );
    }
    return results;
  }

  String _firstNonEmpty(String? a, [String? b, String? c]) {
    final candidates = <String?>[a, b, c];
    for (final item in candidates) {
      final text = (item ?? '').trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  double _relevance(String text, String query) {
    if (query.trim().isEmpty) return 0.5;
    if (text.contains(query)) return 0.9;
    return 0.6;
  }
}

