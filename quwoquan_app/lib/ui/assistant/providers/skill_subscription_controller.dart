import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class P0SkillSubscriptionPreset {
  const P0SkillSubscriptionPreset({
    required this.skillId,
    required this.displayName,
    required this.domainId,
    required this.tagRefs,
    required this.rawText,
    required this.queries,
    required this.cron,
  });

  final String skillId;
  final String displayName;
  final String domainId;
  final List<String> tagRefs;
  final String rawText;
  final List<String> queries;
  final String cron;
}

const p0SkillSubscriptionPresets = <P0SkillSubscriptionPreset>[
  P0SkillSubscriptionPreset(
    skillId: 'daily_assistant',
    displayName: '每日助手',
    domainId: 'assistant',
    tagRefs: <String>['life', 'work', 'study'],
    rawText: '每天早上提醒我今天的生活、工作和学习计划',
    queries: <String>['今日待办', '会议安排', '学习计划'],
    cron: '0 8 * * *',
  ),
  P0SkillSubscriptionPreset(
    skillId: 'news_briefing',
    displayName: '新闻简报',
    domainId: 'content',
    tagRefs: <String>['technology', 'news'],
    rawText: '每天早上给我人工智能和半导体新闻摘要',
    queries: <String>['人工智能新闻', '半导体产业'],
    cron: '0 8 * * *',
  ),
  P0SkillSubscriptionPreset(
    skillId: 'stock_sentinel',
    displayName: '股票哨兵',
    domainId: 'finance',
    tagRefs: <String>['investment', 'stock'],
    rawText: '每天开盘前提醒我关注的股票重大消息',
    queries: <String>['比亚迪 重大消息', '新能源车 行情'],
    cron: '0 9 * * *',
  ),
  P0SkillSubscriptionPreset(
    skillId: 'travel_journey_manager',
    displayName: '出行旅程管家',
    domainId: 'travel',
    tagRefs: <String>['travel', 'weather', 'traffic'],
    rawText: '每天出发前提醒我行程天气、路况和景点拥堵',
    queries: <String>['杭州 西湖 天气', '杭州 景区拥堵', '高铁出行提醒'],
    cron: '0 7 * * *',
  ),
];

class SkillSubscriptionState {
  const SkillSubscriptionState({
    this.items = const <SkillSubscriptionWire>[],
    this.loading = false,
    this.errorMessage = '',
  });

  final List<SkillSubscriptionWire> items;
  final bool loading;
  final String errorMessage;

  SkillSubscriptionState copyWith({
    List<SkillSubscriptionWire>? items,
    bool? loading,
    String? errorMessage,
  }) {
    return SkillSubscriptionState(
      items: items ?? this.items,
      loading: loading ?? this.loading,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }
}

class SkillSubscriptionController extends Notifier<SkillSubscriptionState> {
  @override
  SkillSubscriptionState build() {
    return const SkillSubscriptionState();
  }

  Future<void> refresh() async {
    state = state.copyWith(loading: true, errorMessage: '');
    try {
      final items = await ref
          .read(assistantRepositoryProvider)
          .listSkillSubscriptions();
      state = state.copyWith(items: items, loading: false, errorMessage: '');
    } catch (_) {
      state = state.copyWith(loading: false, errorMessage: '订阅列表暂时不可用，请稍后再试。');
    }
  }

  Future<void> createMorningBriefing() async {
    return createP0Skill(p0SkillSubscriptionPresets[1]);
  }

  Future<void> createP0Skill(P0SkillSubscriptionPreset preset) async {
    state = state.copyWith(loading: true, errorMessage: '');
    try {
      await ref
          .read(assistantRepositoryProvider)
          .createSkillSubscription(
            skillId: preset.skillId,
            domainId: preset.domainId,
            tagRefs: preset.tagRefs,
            rawText: preset.rawText,
            queries: preset.queries,
            cron: preset.cron,
          );
      await refresh();
    } catch (_) {
      state = state.copyWith(loading: false, errorMessage: '创建订阅失败，请稍后再试。');
    }
  }

  Future<void> pause(String subscriptionId) {
    return _updateStatus(subscriptionId, 'paused');
  }

  Future<void> resume(String subscriptionId) {
    return _updateStatus(subscriptionId, 'active');
  }

  Future<void> archive(String subscriptionId) {
    return _updateStatus(subscriptionId, 'archived');
  }

  Future<void> _updateStatus(String subscriptionId, String status) async {
    state = state.copyWith(loading: true, errorMessage: '');
    try {
      await ref
          .read(assistantRepositoryProvider)
          .updateSkillSubscriptionStatus(
            subscriptionId: subscriptionId,
            status: status,
          );
      await refresh();
    } catch (_) {
      state = state.copyWith(loading: false, errorMessage: '更新订阅状态失败，请稍后再试。');
    }
  }
}

final skillSubscriptionControllerProvider =
    NotifierProvider<SkillSubscriptionController, SkillSubscriptionState>(
      SkillSubscriptionController.new,
    );
