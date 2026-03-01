import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

/// Skill Center（V2 原型版）
///
/// 目标：接入真实技能清单与开关，遵循 i18n 与语义 token。
class AssistantSkillCenterPage extends ConsumerStatefulWidget {
  const AssistantSkillCenterPage({
    super.key,
    required this.onBack,
  });

  final VoidCallback onBack;

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

  List<Map<String, dynamic>> _recentSessions = const <Map<String, dynamic>>[];

  @override
  void initState() {
    super.initState();
    _loadRecentSessions();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final pageBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final blockBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final skillsAsync = ref.watch(assistantSkillMarketProvider);

    return CupertinoPageScaffold(
      backgroundColor: pageBg,
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          l10n.assistantSkillCenterTitle,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: widget.onBack,
          child: Icon(CupertinoIcons.back, color: fgPrimary),
        ),
      ),
      child: Stack(
        children: [
          SafeArea(
            child: CustomScrollView(
              slivers: [
                CupertinoSliverRefreshControl(
                  onRefresh: () async {
                    ref.invalidate(assistantSkillMarketProvider);
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
      ),
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
                onChanged: (value) {
                  setState(() => _simpleMode = value);
                  _logSkillCenterEvent(
                    action: 'simple_mode_toggle',
                    meta: <String, dynamic>{'enabled': value},
                  );
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
    required List<PersonalAssistantSkillInfo> skills,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    final packages = <String, List<PersonalAssistantSkillInfo>>{
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
            onChanged: (value) => setState(() => _sceneGates['discovery'] = value),
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
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: fgSecondary,
              ),
            )
          else
            ..._recentSessions.map((item) {
              final sessionId = (item['sessionId'] ?? '').toString();
              final messageCount = (item['messageCount'] ?? 0) as int;
              final lastMessage = (item['lastMessage'] ?? '').toString();
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
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      minSize: 20,
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
    required PersonalAssistantSkillInfo skill,
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
                    skill.manifest.name,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: fgPrimary,
                    ),
                  ),
                  Text(
                    '${skill.category} · ${skill.tier.toUpperCase()} · ${skill.manifest.id}',
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
              onChanged: skill.isDefaultFree
                  ? null
                  : (v) => _toggleSkill(skill.manifest.id, v),
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
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }

  String _packageOf(PersonalAssistantSkillInfo skill) {
    final id = skill.manifest.id;
    final category = skill.category;
    if (id == 'photo.organize' || category == 'media') return 'life';
    if (id == 'reminder.intent' || category == 'productivity') return 'work';
    if (id == 'knowledge_qa' ||
        id == 'web.quick_search' ||
        category == 'knowledge') {
      return 'knowledge';
    }
    return 'companion';
  }

  Future<void> _enableAllSkills() async {
    final skills = await ref.read(assistantGatewayProvider).listSkills();
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await ref
            .read(assistantGatewayProvider)
            .setSkillEnabled(skill.manifest.id, true);
      }
      ref.invalidate(assistantSkillMarketProvider);
      _logSkillCenterEvent(
        action: 'restore_default_all',
        meta: <String, dynamic>{'skillCount': skills.length},
      );
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _togglePackage(
    List<PersonalAssistantSkillInfo> skills,
    bool enabled,
  ) async {
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await ref
            .read(assistantGatewayProvider)
            .setSkillEnabled(skill.manifest.id, enabled);
      }
      ref.invalidate(assistantSkillMarketProvider);
      _logSkillCenterEvent(
        action: 'package_toggle',
        meta: <String, dynamic>{
          'enabled': enabled,
          'skillCount': skills.length,
        },
      );
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _toggleSkill(String skillId, bool enabled) async {
    await _setUpdating(true);
    try {
      await ref.read(assistantGatewayProvider).setSkillEnabled(skillId, enabled);
      ref.invalidate(assistantSkillMarketProvider);
      _logSkillCenterEvent(
        action: 'single_skill_toggle',
        meta: <String, dynamic>{
          'skillId': skillId,
          'enabled': enabled,
        },
      );
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _loadRecentSessions() async {
    if (!mounted) return;
    setState(() => _loadingSessions = true);
    try {
      final sessions = await ref.read(assistantGatewayProvider).listSessions();
      if (!mounted) return;
      setState(() {
        _recentSessions = sessions.take(5).toList(growable: false);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _recentSessions = const <Map<String, dynamic>>[];
      });
    } finally {
      if (!mounted) return;
      setState(() => _loadingSessions = false);
    }
  }

  Future<void> _setUpdating(bool value) async {
    if (!mounted) return;
    setState(() => _updating = value);
  }

  Future<void> _logSkillCenterEvent({
    required String action,
    Map<String, dynamic>? meta,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: trace.newPageVisitId(),
      ),
      payload: <String, dynamic>{
        'event': 'skill_center_action',
        'action': action,
        'meta': meta ?? <String, dynamic>{},
      },
      summaryPayload: <String, dynamic>{
        'event': 'skill_center_action',
        'action': action,
      },
    );
  }
}
/*
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

/// Skill Center（V2 原型版）
///
/// 目标：先打通真实技能清单与开关，承接“默认全订阅 + 可治理”的核心交互。
class AssistantSkillCenterPage extends ConsumerStatefulWidget {
  const AssistantSkillCenterPage({
    super.key,
    required this.onBack,
  });

  final VoidCallback onBack;

  @override
  ConsumerState<AssistantSkillCenterPage> createState() =>
      _AssistantSkillCenterPageState();
}

class _AssistantSkillCenterPageState
    extends ConsumerState<AssistantSkillCenterPage> {
  bool _simpleMode = false;
  bool _updating = false;
  bool _lowRiskAutoRun = true;
  bool _mediumRiskNeedConfirm = true;
  bool _highRiskNeedDoubleConfirm = true;
  final Map<String, bool> _sceneGates = <String, bool>{
    'discovery': true,
    'circle': true,
    'chat': true,
    'system': true,
  };
  final List<Map<String, String>> _recentInvocations = <Map<String, String>>[
    <String, String>{
      'time': '今天 09:41',
      'skill': '知识问答',
      'reason': '用户主动提问',
      'result': '成功',
    },
    <String, String>{
      'time': '今天 08:55',
      'skill': '系统提醒',
      'reason': '群聊待办建议',
      'result': '待确认',
    },
  ];

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final pageBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final blockBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);

    final skillsAsync = ref.watch(assistantSkillMarketProvider);

    return CupertinoPageScaffold(
      backgroundColor: pageBg,
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          '技能中心',
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.semiBold,
            color: fgPrimary,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: widget.onBack,
          child: Icon(CupertinoIcons.back, color: fgPrimary),
        ),
      ),
      child: Stack(
        children: [
          SafeArea(
            child: CustomScrollView(
              slivers: [
                CupertinoSliverRefreshControl(
                  onRefresh: () async {
                    ref.invalidate(assistantSkillMarketProvider);
                  },
                ),
                SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.all(AppSpacing.containerMd),
                    child: _buildDefaultSubscriptionCard(
                      blockBg,
                      fgPrimary,
                      fgSecondary,
                    ),
                  ),
                ),
                SliverToBoxAdapter(child: SizedBox(height: AppSpacing.interGroupMd)),
                SliverToBoxAdapter(
                  child: skillsAsync.when(
                    loading: () => const Padding(
                      padding: EdgeInsets.symmetric(vertical: 48),
                      child: Center(child: CupertinoActivityIndicator()),
                    ),
                    error: (error, _) => Padding(
                      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                      child: Text(
                        '技能加载失败：$error',
                        style: TextStyle(color: fgSecondary),
                      ),
                    ),
                    data: (skills) => Padding(
                      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildPackageSection(
                            title: '能力包',
                            skills: skills,
                            fgPrimary: fgPrimary,
                            fgSecondary: fgSecondary,
                            blockBg: blockBg,
                          ),
                          SizedBox(height: AppSpacing.interGroupMd),
                          _buildRiskPolicySection(
                            fgPrimary: fgPrimary,
                            fgSecondary: fgSecondary,
                            blockBg: blockBg,
                          ),
                          SizedBox(height: AppSpacing.interGroupMd),
                          _buildSceneGatesSection(
                            fgPrimary: fgPrimary,
                            fgSecondary: fgSecondary,
                            blockBg: blockBg,
                          ),
                          SizedBox(height: AppSpacing.interGroupMd),
                          _buildInvocationSection(
                            fgPrimary: fgPrimary,
                            fgSecondary: fgSecondary,
                            blockBg: blockBg,
                          ),
                          SizedBox(height: AppSpacing.interGroupMd),
                          Text(
                            '全部技能',
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
                color: Colors.black.withValues(alpha: 0.08),
                child: const Center(child: CupertinoActivityIndicator()),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildInvocationSection({
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
            '最近调用',
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ..._recentInvocations.map((item) {
            final success = item['result'] == '成功';
            return Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${item['skill']} · ${item['time']}',
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgPrimary,
                          ),
                        ),
                        Text(
                          item['reason'] ?? '',
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    item['result'] ?? '',
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: success ? AppColors.success : AppColors.warning,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    minSize: 20,
                    onPressed: () {},
                    child: Text(
                      '查看',
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

  Widget _buildRiskPolicySection({
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
            '风险策略',
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildSwitchRow(
            label: '低风险自动执行',
            desc: '检索、总结、问答默认执行',
            value: _lowRiskAutoRun,
            onChanged: (value) => setState(() => _lowRiskAutoRun = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: '中风险轻确认',
            desc: '创建提醒、生成待办需确认',
            value: _mediumRiskNeedConfirm,
            onChanged: (value) => setState(() => _mediumRiskNeedConfirm = value),
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSwitchRow(
            label: '高风险二次确认',
            desc: '交易、外部提交等必须二次确认',
            value: _highRiskNeedDoubleConfirm,
            onChanged: (value) async {
              if (!value) {
                await showCupertinoDialog<void>(
                  context: context,
                  builder: (context) => CupertinoAlertDialog(
                    title: const Text('不可关闭'),
                    content: const Text('高风险动作必须保留二次确认'),
                    actions: [
                      CupertinoDialogAction(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('我知道了'),
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
            '场景闸门',
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildSceneGateTile(
            keyName: 'discovery',
            label: '发现页',
            desc: '浏览时仅轻提示，不主动打断',
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSceneGateTile(
            keyName: 'circle',
            label: '圈子',
            desc: '圈内讨论建议按需触发',
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSceneGateTile(
            keyName: 'chat',
            label: '趣聊',
            desc: '默认受邀参与（@小趣或手动点击）',
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          _buildSceneGateTile(
            keyName: 'system',
            label: '系统外场景',
            desc: '剪贴板、图片、外链等跨场景能力',
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        ],
      ),
    );
  }

  Widget _buildSceneGateTile({
    required String keyName,
    required String label,
    required String desc,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return _buildSwitchRow(
      label: label,
      desc: desc,
      value: _sceneGates[keyName] ?? false,
      onChanged: (value) => setState(() => _sceneGates[keyName] = value),
      fgPrimary: fgPrimary,
      fgSecondary: fgSecondary,
    );
  }

  Widget _buildDefaultSubscriptionCard(
    Color blockBg,
    Color fgPrimary,
    Color fgSecondary,
  ) {
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
                '默认全订阅已开启',
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
            '开箱即用全部助理能力；执行时仍受风险策略与场景闸门约束。',
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
                  '恢复默认全订阅',
                  style: TextStyle(
                    color: AppColors.primaryColor,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ),
              const Spacer(),
              Text(
                '极简模式',
                style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
              ),
              CupertinoSwitch(
                value: _simpleMode,
                onChanged: (value) {
                  setState(() => _simpleMode = value);
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPackageSection({
    required String title,
    required List<PersonalAssistantSkillInfo> skills,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blockBg,
  }) {
    final packages = <String, List<PersonalAssistantSkillInfo>>{
      '生活助理': skills.where((s) => _packageOf(s) == 'life').toList(growable: false),
      '工作助理': skills.where((s) => _packageOf(s) == 'work').toList(growable: false),
      '知识助理': skills.where((s) => _packageOf(s) == 'knowledge').toList(growable: false),
      '陪伴助理': skills.where((s) => _packageOf(s) == 'companion').toList(growable: false),
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
            title,
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
              desc: list.isEmpty ? '暂无对应技能' : '包含 ${list.length} 项',
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

  Widget _buildSkillRow({
    required PersonalAssistantSkillInfo skill,
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
                    skill.manifest.name,
                    style: TextStyle(fontSize: AppTypography.base, color: fgPrimary),
                  ),
                  Text(
                    '${skill.category} · ${skill.tier.toUpperCase()} · ${skill.manifest.id}',
                    style: TextStyle(fontSize: AppTypography.xs, color: fgSecondary),
                  ),
                ],
              ),
            ),
            CupertinoSwitch(
              value: skill.enabled,
              onChanged: skill.isDefaultFree
                  ? null
                  : (v) => _toggleSkill(skill.manifest.id, v),
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
                SizedBox(height: 2),
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
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }

  String _packageOf(PersonalAssistantSkillInfo skill) {
    final id = skill.manifest.id;
    final category = skill.category;
    if (id == 'photo.organize' || category == 'media') return 'life';
    if (id == 'reminder.intent' || category == 'productivity') return 'work';
    if (id == 'knowledge_qa' || id == 'web.quick_search' || category == 'knowledge') {
      return 'knowledge';
    }
    return 'companion';
  }

  Future<void> _enableAllSkills() async {
    final skills = await ref.read(assistantGatewayProvider).listSkills();
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await ref.read(assistantGatewayProvider).setSkillEnabled(skill.manifest.id, true);
      }
      ref.invalidate(assistantSkillMarketProvider);
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _togglePackage(List<PersonalAssistantSkillInfo> skills, bool enabled) async {
    await _setUpdating(true);
    try {
      for (final skill in skills) {
        await ref
            .read(assistantGatewayProvider)
            .setSkillEnabled(skill.manifest.id, enabled);
      }
      ref.invalidate(assistantSkillMarketProvider);
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _toggleSkill(String skillId, bool enabled) async {
    await _setUpdating(true);
    try {
      await ref.read(assistantGatewayProvider).setSkillEnabled(skillId, enabled);
      ref.invalidate(assistantSkillMarketProvider);
    } finally {
      await _setUpdating(false);
    }
  }

  Future<void> _setUpdating(bool value) async {
    if (!mounted) return;
    setState(() => _updating = value);
  }
}
*/
