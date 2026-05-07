import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/assistant/generated/contracts/skill_subscription.g.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_skill_center_action_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_skill_center_package_toggle_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_skill_center_restore_default_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_skill_center_simple_mode_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_skill_center_single_skill_payload.g.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_gateway_ui_views.dart';

// settings-canonical-exception: Skill Center 原型仪表板布局 CR-20260329-003

class AssistantSkillCenterItem {
  const AssistantSkillCenterItem({required this.catalog, this.subscription});

  final AssistantSkillCatalogItemView catalog;
  final SkillSubscriptionWire? subscription;

  String get skillId => catalog.skillId;
  bool get enabled => subscription != null && subscription!.status == 'active';
  bool get paused => subscription != null && subscription!.status == 'paused';
  String get statusLabel {
    final status = subscription?.status ?? '';
    if (status == 'active') return '已订阅';
    if (status == 'paused') return '已暂停';
    return catalog.requiresConsent ? '需授权' : '可订阅';
  }
}

final assistantSkillCenterProvider =
    FutureProvider<List<AssistantSkillCenterItem>>((ref) async {
      final repo = ref.watch(assistantRepositoryProvider);
      final catalog = await repo.listSkillCatalog(limit: 64);
      final subscriptions = await repo.listSkillSubscriptions(limit: 64);
      final activeSubscriptions = <String, SkillSubscriptionWire>{
        for (final item in subscriptions)
          if (item.status != 'archived') item.skillId: item,
      };
      return catalog
          .map(
            (item) => AssistantSkillCenterItem(
              catalog: item,
              subscription: activeSubscriptions[item.skillId],
            ),
          )
          .toList(growable: false);
    });

/// Skill Center 仪表板（能力入口与统计）
///
/// 目标：接入真实技能清单与开关，遵循 i18n 与语义 token。
class AssistantSkillCenterPage extends ConsumerStatefulWidget {
  const AssistantSkillCenterPage({
    super.key,
    required this.onBack,
    this.embedded = false,
  });

  final VoidCallback onBack;
  final bool embedded;

  @override
  ConsumerState<AssistantSkillCenterPage> createState() =>
      _AssistantSkillCenterPageState();
}

class _AssistantSkillCenterPageState
    extends ConsumerState<AssistantSkillCenterPage> {
  bool _simpleMode = false;
  bool _updating = false;
  bool _loadingSessions = false;
  bool _lowRiskAutoRun = true;
  bool _mediumRiskNeedConfirm = true;
  bool _highRiskNeedDoubleConfirm = true;

  final Map<String, bool> _sceneGates = <String, bool>{
    'discovery': true,
    'circle': true,
    'chat': true,
    'system': true,
  };

  List<AssistantLocalSessionSummaryView> _recentSessions =
      const <AssistantLocalSessionSummaryView>[];

  @override
  void initState() {
    super.initState();
    _loadRecentSessions();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final pageBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final blockBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final skillsAsync = ref.watch(assistantSkillCenterProvider);

    final content = Stack(
      children: [
        SafeArea(
          child: CustomScrollView(
            slivers: [
              CupertinoSliverRefreshControl(
                onRefresh: () async {
                  ref.invalidate(assistantSkillCenterProvider);
                  await _loadRecentSessions();
                },
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  child: _buildDefaultSubscriptionCard(
                    l10n: l10n,
                    blockBg: blockBg,
                    fgPrimary: fgPrimary,
                    fgSecondary: fgSecondary,
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  child: skillsAsync.when(
                    loading: () => const Padding(
                      padding: EdgeInsets.symmetric(vertical: 48),
                      child: Center(child: CupertinoActivityIndicator()),
                    ),
                    error: (error, _) => Padding(
                      padding: EdgeInsets.symmetric(
                        vertical: AppSpacing.interGroupMd,
                      ),
                      child: Text(
                        '${l10n.loadFailed}: $error',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                    data: (skills) => Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildPackageSection(
                          l10n: l10n,
                          skills: skills,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          blockBg: blockBg,
                        ),
                        SizedBox(height: AppSpacing.interGroupMd),
                        _buildRiskPolicySection(
                          l10n: l10n,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          blockBg: blockBg,
                        ),
                        SizedBox(height: AppSpacing.interGroupMd),
                        _buildSceneGatesSection(
                          l10n: l10n,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          blockBg: blockBg,
                        ),
                        SizedBox(height: AppSpacing.interGroupMd),
                        _buildSessionsSection(
                          l10n: l10n,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          blockBg: blockBg,
                        ),
                        SizedBox(height: AppSpacing.interGroupMd),
                        Text(
                          l10n.assistantSkillCenterAllSkillsTitle,
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupSm),
                        ...skills.map(
                          (skill) => _buildSkillRow(
                            skill: skill,
                            fgPrimary: fgPrimary,
                            fgSecondary: fgSecondary,
                            blockBg: blockBg,
                          ),
                        ),
                        SizedBox(height: AppSpacing.interGroupLg),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        if (_updating)
          Positioned.fill(
            child: Container(
              color: CupertinoColors.black.withValues(alpha: 0.08),
              child: const Center(child: CupertinoActivityIndicator()),
            ),
          ),
      ],
    );

    if (widget.embedded) {
      return Container(color: pageBg, child: content);
    }

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        middle: Text(
          l10n.assistantSkillCenterTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
      ),
      child: content,
    );
  }

  Widget _buildDefaultSubscriptionCard({
    required AppLocalizations l10n,
    required Color blockBg,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.iconSmall,
                color: AppColors.primaryColor,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                l10n.assistantSkillCenterDefaultAllSubscribedTitle,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                  color: fgPrimary,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            l10n.assistantSkillCenterDefaultAllSubscribedDesc,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: fgSecondary,
              height: AppTypography.bodyLineHeight,
            ),
          ),
          SizedBox(height: AppSpacing.interGroupSm),
          Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: _enableAllSkills,
                child: Text(
                  l10n.assistantSkillCenterRestoreDefaultAll,
                  style: TextStyle(
                    color: AppColors.primaryColor,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ),
              const Spacer(),
              Text(
                l10n.assistantSkillCenterSimpleMode,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
              CupertinoSwitch(
                value: _simpleMode,
                activeTrackColor:
                    SettingsSemanticConstants.switchActiveTrackColor,
                onChanged: (value) {
                  setState(() => _simpleMode = value);
                  unawaited(_logSkillCenterSimpleMode(value));
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPackageSection({
    required AppLocalizations l10n,
    required List<AssistantSkillCenterItem> skills,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    final packages = <String, List<AssistantSkillCenterItem>>{
      l10n.assistantSkillCenterPackageLife: skills
          .where((s) => _packageOf(s) == 'life')
          .toList(growable: false),
      l10n.assistantSkillCenterPackageWork: skills
          .where((s) => _packageOf(s) == 'work')
          .toList(growable: false),
      l10n.assistantSkillCenterPackageKnowledge: skills
          .where((s) => _packageOf(s) == 'knowledge')
          .toList(growable: false),
      l10n.assistantSkillCenterPackageCompanion: skills
          .where((s) => _packageOf(s) == 'companion')
          .toList(growable: false),
    };

    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.assistantSkillCenterPackagesTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...packages.entries.map((entry) {
            final list = entry.value;
            final enabled = list.isNotEmpty && list.every((s) => s.enabled);
            return _buildSwitchRow(
              label: entry.key,
              desc: list.isEmpty
                  ? l10n.assistantSkillCenterNoMappedSkills
                  : l10n.assistantSkillCenterContainsCount(list.length),
              value: enabled,
              onChanged: list.isEmpty ? (_) {} : (v) => _togglePackage(list, v),
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
            );
          }),
        ],
      ),
    );
  }

  Widget _buildRiskPolicySection({
    required AppLocalizations l10n,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.assistantSkillCenterRiskPolicyTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterLowRiskAuto,
            desc: l10n.assistantSkillCenterLowRiskDesc,
            value: _lowRiskAutoRun,
            onChanged: (value) => setState(() => _lowRiskAutoRun = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterMediumRiskConfirm,
            desc: l10n.assistantSkillCenterMediumRiskDesc,
            value: _mediumRiskNeedConfirm,
            onChanged: (value) =>
                setState(() => _mediumRiskNeedConfirm = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterHighRiskDoubleConfirm,
            desc: l10n.assistantSkillCenterHighRiskDesc,
            value: _highRiskNeedDoubleConfirm,
            onChanged: (value) async {
              if (!value) {
                await showCupertinoDialog<void>(
                  context: context,
                  builder: (context) => CupertinoAlertDialog(
                    title: Text(l10n.cancel),
                    content: Text(l10n.assistantSkillCenterHighRiskRequired),
                    actions: [
                      CupertinoDialogAction(
                        onPressed: () => Navigator.of(context).pop(),
                        child: Text(l10n.confirm),
                      ),
                    ],
                  ),
                );
                return;
              }
              setState(() => _highRiskNeedDoubleConfirm = value);
            },
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        ],
      ),
    );
  }

  Widget _buildSceneGatesSection({
    required AppLocalizations l10n,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.assistantSkillCenterSceneGateTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterSceneDiscovery,
            desc: l10n.assistantSkillCenterSceneDiscoveryDesc,
            value: _sceneGates['discovery'] ?? false,
            onChanged: (value) =>
                setState(() => _sceneGates['discovery'] = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterSceneCircle,
            desc: l10n.assistantSkillCenterSceneCircleDesc,
            value: _sceneGates['circle'] ?? false,
            onChanged: (value) => setState(() => _sceneGates['circle'] = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterSceneChat,
            desc: l10n.assistantSkillCenterSceneChatDesc,
            value: _sceneGates['chat'] ?? false,
            onChanged: (value) => setState(() => _sceneGates['chat'] = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: l10n.assistantSkillCenterSceneSystem,
            desc: l10n.assistantSkillCenterSceneSystemDesc,
            value: _sceneGates['system'] ?? false,
            onChanged: (value) => setState(() => _sceneGates['system'] = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        ],
      ),
    );
  }

  Widget _buildSessionsSection({
    required AppLocalizations l10n,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l10n.assistantSkillCenterRecentSessionsTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          if (_loadingSessions)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: CupertinoActivityIndicator(),
            )
          else if (_recentSessions.isEmpty)
            Text(
              l10n.assistantSkillCenterNoRecentSessions,
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            )
          else
            ..._recentSessions.map((item) {
              final sessionId = item.sessionId;
              final messageCount = item.messageCount;
              final lastMessage = item.lastMessage;
              return Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${sessionId.isEmpty ? l10n.unknown : sessionId} · ${l10n.assistantSkillCenterMessagesCount(messageCount)}',
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: fgPrimary,
                            ),
                          ),
                          Text(
                            lastMessage.isEmpty
                                ? l10n.assistantSkillCenterNoLastMessage
                                : lastMessage,
                            style: TextStyle(
                              fontSize: AppTypography.xs,
                              color: fgSecondary,
                              height: AppTypography.lineHeightCompact,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(20, 20),
                      onPressed: () {},
                      child: Text(
                        l10n.seeMore,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildSkillRow({
    required AssistantSkillCenterItem skill,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
      decoration: BoxDecoration(
        color: blockBg,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.intraGroupSm),
        child: Row(
          children: [
            Icon(
              CupertinoIcons.cube_box,
              size: AppSpacing.iconSmall,
              color: skill.enabled ? AppColors.primaryColor : fgSecondary,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    skill.catalog.displayName,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: fgPrimary,
                    ),
                  ),
                  Text(
                    '${skill.catalog.category ?? 'assistant'} · ${skill.statusLabel} · ${skill.skillId}',
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
            CupertinoSwitch(
              value: skill.enabled,
              activeTrackColor:
                  SettingsSemanticConstants.switchActiveTrackColor,
              inactiveTrackColor:
                  SettingsSemanticConstants.switchInactiveTrackColor(
                    ref.watch(isDarkProvider),
                  ),
              onChanged: (v) => _toggleSkill(skill, v),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSwitchRow({
    required String label,
    required String desc,
    required bool value,
    required ValueChanged<bool> onChanged,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgPrimary,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  desc,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
          CupertinoSwitch(
            value: value,
            activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
            inactiveTrackColor:
                SettingsSemanticConstants.switchInactiveTrackColor(
                  ref.watch(isDarkProvider),
                ),
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }

  String _packageOf(AssistantSkillCenterItem skill) {
    final id = skill.skillId;
    final category = skill.catalog.category ?? '';
    if (id == 'daily_assistant' || category == 'life') return 'life';
    if (id == 'assistant_navigation' || category == 'productivity')
      return 'work';
    if (id == 'news_briefing' ||
        id == 'stock_sentinel' ||
        id == 'knowledge_qa' ||
        category == 'knowledge' ||
        category == 'content' ||
        category == 'finance') {
      return 'knowledge';
    }
    return 'companion';
  }

  List<String> _tagRefsForSkill(AssistantSkillCenterItem skill) {
    final category = skill.catalog.category?.trim();
    return <String>[
      if (category != null && category.isNotEmpty) category,
      skill.skillId,
    ];
  }

  List<String> _queriesForSkill(AssistantSkillCenterItem skill) {
    switch (skill.skillId) {
      case 'stock_sentinel':
        return const <String>['比亚迪 重大消息', '新能源车 行情'];
      case 'travel_journey_manager':
        return const <String>['杭州 西湖 天气', '杭州 景区拥堵', '高铁出行提醒'];
      case 'news_briefing':
        return const <String>['人工智能新闻', '半导体产业'];
      case 'daily_assistant':
        return const <String>['今日待办', '会议安排', '学习计划'];
      default:
        return <String>[skill.catalog.displayName];
    }
  }

  String _rawTextForSkill(AssistantSkillCenterItem skill) {
    switch (skill.skillId) {
      case 'stock_sentinel':
        return '每天开盘前提醒我关注的股票重大消息';
      case 'travel_journey_manager':
        return '每天出发前提醒我行程天气、路况和景点拥堵';
      case 'news_briefing':
        return '每天早上给我人工智能和半导体新闻摘要';
      case 'daily_assistant':
        return '每天早上提醒我今天的生活、工作和学习计划';
      default:
        final description = skill.catalog.description?.trim();
        return description == null || description.isEmpty
            ? '订阅 ${skill.catalog.displayName}'
            : description;
    }
  }

  String _cronForSkill(AssistantSkillCenterItem skill) {
    switch (skill.skillId) {
      case 'stock_sentinel':
        return '0 9 * * *';
      case 'travel_journey_manager':
        return '0 7 * * *';
      default:
        return '0 8 * * *';
    }
  }

  Future<void> _enableAllSkills() async {
    final cached = ref
        .read(assistantSkillCenterProvider)
        .maybeWhen<List<AssistantSkillCenterItem>?>(
          data: (items) => items,
          orElse: () => null,
        );
    var skills = cached ?? const <AssistantSkillCenterItem>[];
    if (cached == null) {
      skills = await ref.refresh(assistantSkillCenterProvider.future);
    }
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        if (!skill.enabled) {
          await _setSkillEnabled(skill, true);
        }
      }
      ref.invalidate(assistantSkillCenterProvider);
      await _logSkillCenterRestoreDefault(skills.length);
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _togglePackage(
    List<AssistantSkillCenterItem> skills,
    bool enabled,
  ) async {
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await _setSkillEnabled(skill, enabled);
      }
      ref.invalidate(assistantSkillCenterProvider);
      await _logSkillCenterPackageToggle(
        enabled: enabled,
        skillCount: skills.length,
      );
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _toggleSkill(
    AssistantSkillCenterItem skill,
    bool enabled,
  ) async {
    await _setUpdating(true);
    try {
      await _setSkillEnabled(skill, enabled);
      ref.invalidate(assistantSkillCenterProvider);
      await _logSkillCenterSingleSkillToggle(
        skillId: skill.skillId,
        enabled: enabled,
      );
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _setSkillEnabled(
    AssistantSkillCenterItem skill,
    bool enabled,
  ) async {
    final repo = ref.read(assistantRepositoryProvider);
    final subscription = skill.subscription;
    if (enabled) {
      if (subscription == null) {
        await repo.createSkillSubscription(
          skillId: skill.skillId,
          domainId: skill.catalog.category ?? 'assistant',
          tagRefs: _tagRefsForSkill(skill),
          rawText: _rawTextForSkill(skill),
          queries: _queriesForSkill(skill),
          cron: _cronForSkill(skill),
        );
        return;
      }
      await repo.updateSkillSubscriptionStatus(
        subscriptionId: subscription.subscriptionId,
        status: 'active',
      );
      return;
    }
    if (subscription != null) {
      await repo.updateSkillSubscriptionStatus(
        subscriptionId: subscription.subscriptionId,
        status: 'paused',
      );
    }
  }

  Future<void> _loadRecentSessions() async {
    if (!mounted) return;
    setState(() => _loadingSessions = true);
    try {
      final manager = AssistantSessionManager();
      await manager.load();
      final sessions = manager.listSessionDescriptors();
      if (!mounted) return;
      setState(() {
        _recentSessions = sessions
            .take(5)
            .map(AssistantLocalSessionSummaryView.fromDescriptor)
            .toList(growable: false);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _recentSessions = const <AssistantLocalSessionSummaryView>[];
      });
    } finally {
      if (mounted) setState(() => _loadingSessions = false);
    }
  }

  Future<void> _setUpdating(bool value) async {
    if (!mounted) return;
    setState(() => _updating = value);
  }

  Future<void> _logSkillCenterSimpleMode(bool enabled) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: AppLogSkillCenterSimpleModePayload(
        event: 'skill_center_action',
        action: 'simple_mode_toggle',
        enabled: enabled,
      ).toMap(),
      summaryPayload: AppLogSkillCenterActionSummaryPayload(
        event: 'skill_center_action',
        action: 'simple_mode_toggle',
      ).toMap(),
    );
  }

  Future<void> _logSkillCenterRestoreDefault(int skillCount) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: AppLogSkillCenterRestoreDefaultPayload(
        event: 'skill_center_action',
        action: 'restore_default_all',
        skillCount: skillCount,
      ).toMap(),
      summaryPayload: AppLogSkillCenterActionSummaryPayload(
        event: 'skill_center_action',
        action: 'restore_default_all',
      ).toMap(),
    );
  }

  Future<void> _logSkillCenterPackageToggle({
    required bool enabled,
    required int skillCount,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: AppLogSkillCenterPackageTogglePayload(
        event: 'skill_center_action',
        action: 'package_toggle',
        enabled: enabled,
        skillCount: skillCount,
      ).toMap(),
      summaryPayload: AppLogSkillCenterActionSummaryPayload(
        event: 'skill_center_action',
        action: 'package_toggle',
      ).toMap(),
    );
  }

  Future<void> _logSkillCenterSingleSkillToggle({
    required String skillId,
    required bool enabled,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: AppLogSkillCenterSingleSkillPayload(
        event: 'skill_center_action',
        action: 'single_skill_toggle',
        skillId: skillId,
        enabled: enabled,
      ).toMap(),
      summaryPayload: AppLogSkillCenterActionSummaryPayload(
        event: 'skill_center_action',
        action: 'single_skill_toggle',
      ).toMap(),
    );
  }
}
