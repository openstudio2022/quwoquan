import 'package:quwoquan_app/cloud/runtime/generated/content/article_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/privacy_policy.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_provider.dart';

class PageContextRetrievalProvider implements AssistantRetrievalProvider {
  const PageContextRetrievalProvider({
    required ContentRepository contentRepository,
    required ChatRepository chatRepository,
    required CircleRepository circleRepository,
  }) : _contentRepository = contentRepository,
       _chatRepository = chatRepository,
       _circleRepository = circleRepository;

  final ContentRepository _contentRepository;
  final ChatRepository _chatRepository;
  final CircleRepository _circleRepository;

  @override
  String get providerId => 'page_context';

  @override
  List<String> get capabilityIds => const <String>[
    AssistantCapabilityCatalog.currentPage,
    AssistantCapabilityCatalog.pageComments,
    AssistantCapabilityCatalog.behaviorTimeline,
  ];

  @override
  Future<AssistantRetrievalResult> retrieve(
    AssistantRetrievalRequest request,
  ) async {
    final scope = request.contextScopeHint;
    final contentAccess =
        (scope['assistantContentAccess'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final contentIndex =
        (scope['assistantContentIndex'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final consentGranted = contentAccess.isEmpty
        ? true
        : contentAccess['granted'] != false;
    final identityIndexEnabled = contentIndex.isEmpty
        ? true
        : contentIndex['enabled'] == true;
    final pageType = (scope['pageType'] as String?)?.trim() ?? 'chat';
    final policy = AssistantPrivacyPolicy.fromInputs(
      privacyProfile: request.privacyProfile,
      contextScopeHint: <String, dynamic>{
        ...scope,
        'privacyPolicy': request.privacyPolicy,
      },
      fallbackCapabilities: request.requestedCapabilities,
    );
    if (!consentGranted) {
      return AssistantRetrievalResult(
        success: false,
        message: '未授权读取创作内容。',
        providersUsed: const <String>['page_context'],
        errorCode: 'assistant_content_access_denied',
      );
    }
    if (!policy.allowsPageType(pageType)) {
      return AssistantRetrievalResult(
        success: false,
        message: '隐私策略不允许读取 $pageType 页面上下文。',
        providersUsed: const <String>['page_context'],
        errorCode: 'privacy_page_blocked',
      );
    }
    final items = await _buildPageItems(
      pageType: pageType,
      scope: scope,
      query: request.query,
      identityIndexEnabled: identityIndexEnabled,
    );
    if (items.isEmpty) {
      return AssistantRetrievalResult(
        success: false,
        message: '当前页面暂未产出可用上下文。',
        providersUsed: const <String>['page_context'],
        degraded: false,
      );
    }
    return AssistantRetrievalResult(
      success: true,
      message: '已提取$pageType 页面上下文。',
      items: items,
      providersUsed: const <String>['page_context'],
      coverageScore: items.length >= 2 ? 0.8 : 0.55,
      conflictScore: 0.0,
    );
  }

  Future<List<AssistantRetrievalItem>> _buildPageItems({
    required String pageType,
    required Map<String, dynamic> scope,
    required String query,
    required bool identityIndexEnabled,
  }) async {
    final results = <AssistantRetrievalItem>[];
    switch (pageType) {
      case 'discovery':
        final moment = await _contentRepository.listDiscoveryFeed(
          category: 'moment',
          limit: 2,
        );
        final article = await _contentRepository.listDiscoveryFeed(
          category: 'article',
          limit: 1,
        );
        final video = await _contentRepository.listDiscoveryFeed(
          category: 'video',
          limit: 1,
        );
        final cards = <PostBaseDto>[...moment, ...article, ...video];
        for (final post in cards) {
          final routed = _buildDiscoveryItemFromPost(
            post,
            query,
            identityIndexEnabled: identityIndexEnabled,
          );
          if (routed == null) continue;
          results.add(routed);
        }
        break;
      case 'circles':
        final circles = await _circleRepository.listCircles(limit: 3);
        for (final circle in circles) {
          final name = circle.name;
          final desc = circle.description ?? '';
          final text = _firstNonEmpty('$name $desc', name);
          if (text.isEmpty) continue;
          results.add(
            AssistantRetrievalItem(
              content: text,
              sourceType: 'page.circles',
              sourceId: circle.id,
              relevance: _relevance(text, query),
            ),
          );
        }
        break;
      case 'create':
        final hints =
            (scope['hints'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final createSummary = <String>[
          '创作页当前状态',
          if (hints['hasAddedMedia'] == true) '已添加媒体',
          if (hints['hasDraft'] == true) '存在草稿',
          if (hints['channelCount'] != null) '已选渠道:${hints['channelCount']}',
          if (hints['optimizeAction'] != null)
            '最近优化:${hints['optimizeAction']}',
        ].join('，');
        results.add(
          AssistantRetrievalItem(
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
          AssistantRetrievalItem(
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
        final chatMessages = await _chatRepository.listMessages(
          conversationId: conversationId,
          limit: 4,
        );
        for (final message in chatMessages) {
          final text = (message.content ?? '').trim();
          if (text.isEmpty) continue;
          results.add(
            AssistantRetrievalItem(
              content: text,
              sourceType: 'page.chat',
              sourceId: message.id.isNotEmpty ? message.id : 'chat_message',
              relevance: _relevance(text, query),
            ),
          );
        }
        break;
    }

    final behaviorTimeline =
        (scope['behaviorTimeline'] as List?)
            ?.whereType<Map>()
            .take(3)
            .map((entry) => entry['action']?.toString() ?? '')
            .where((action) => action.trim().isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (behaviorTimeline.isNotEmpty) {
      results.add(
        AssistantRetrievalItem(
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

  AssistantRetrievalItem? _buildDiscoveryItemFromPost(
    PostBaseDto post,
    String query, {
    required bool identityIndexEnabled,
  }) {
    if (_assistantUsePolicyForPost(post) == 'exclude') {
      return null;
    }
    final text = _firstNonEmpty(post.normalizedBody, post.normalizedTitle);
    if (text.isEmpty) return null;
    final identity = _contentIdentityForPost(post);
    final route = !identityIndexEnabled
        ? 'page_context'
        : (identity == 'moment' ? 'context_memory' : 'knowledge_index');
    final tier = _derivedContentTierFromPost(post);
    return AssistantRetrievalItem(
      content: text,
      sourceType: !identityIndexEnabled
          ? 'page.discovery.page_context'
          : (identity == 'moment'
                ? 'page.discovery.moment_context'
                : 'page.discovery.work_knowledge'),
      sourceId: post.id.isNotEmpty ? post.id : 'discovery_item',
      relevance: _relevance(text, query),
      metadata: <String, dynamic>{
        if (identityIndexEnabled) 'contentIdentity': identity,
        'assistantRoute': route,
        'assistantUsePolicy': _assistantUsePolicyForPost(post),
        'assistantEligible': true,
        if (identityIndexEnabled) 'contentTier': tier,
        'identityIndexEnabled': identityIndexEnabled,
        if (post.normalizedTitle.isNotEmpty) 'title': post.normalizedTitle,
      },
    );
  }

  String _contentIdentityForPost(PostBaseDto post) {
    final id = post.identity.trim().toLowerCase();
    if (id.isNotEmpty) return id;
    final contentType = post.type.trim().toLowerCase();
    switch (contentType) {
      case 'micro':
      case 'moment':
        return 'moment';
      default:
        return 'work';
    }
  }

  String _assistantUsePolicyForPost(PostBaseDto post) {
    final policy = post.assistantUsePolicy.trim();
    return policy.isEmpty ? 'inherit' : policy;
  }

  String _derivedContentTierFromPost(PostBaseDto post) {
    final title = post.normalizedTitle.toLowerCase();
    final body = post.normalizedBody.toLowerCase();
    final summary = post is ArticlePostDto ? post.summary.toLowerCase() : '';
    final joined = '$title $body $summary';
    if (joined.contains('清单')) {
      return 'checklist';
    }
    if (joined.contains('攻略')) {
      return 'guide';
    }
    return 'normal';
  }
}
