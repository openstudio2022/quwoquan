import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/capabilities/capabilities.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

/// Skill Center（V2 原型版）
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

    final content = Stack(
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
    );

    if (widget.embedded) {
      return Container(
        color: pageBg,
        child: content,
      );
    }

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
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
                activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
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
              activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
              inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(ref.watch(isDarkProvider)),
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
            activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
            inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(ref.watch(isDarkProvider)),
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
      if (mounted) setState(() => _loadingSessions = false);
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
