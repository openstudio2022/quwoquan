part of 'assistant_skill_center_page.dart';

// 仅承载技能中心各区块的纯 Widget 构建逻辑。
extension _AssistantSkillCenterSections on _AssistantSkillCenterPageState {
  /// 进入指定云端会话续聊（经 conversationId 透传给对话页）。
  void _openConversation(String conversationId) {
    context.push(
      AppRoutePaths.assistantPersonal,
      extra: AssistantOpenContext(
        source: AssistantSource.chat,
        visitTarget: const VisitTarget.page('assistant_skill_center_recent'),
        experienceLevel: ExperienceLevel.returning,
        conversationId: conversationId,
      ),
    );
  }

  String _conversationUpdatedLabel(AppLocalizations l10n, String updatedAt) {
    final parsed = DateTime.tryParse(updatedAt.trim());
    if (parsed == null) {
      return '';
    }
    final local = parsed.toLocal();
    final delta = DateTime.now().difference(local);
    if (delta.inMinutes < 1) {
      return l10n.justNow;
    }
    if (delta.inMinutes < 60) {
      return l10n.minutesAgoTemplate(delta.inMinutes);
    }
    if (delta.inHours < 24) {
      return l10n.hoursAgoTemplate(delta.inHours);
    }
    if (delta.inDays < 30) {
      return l10n.daysAgoTemplate(delta.inDays);
    }
    return l10n.monthDayTemplate(local.month, local.day);
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
            final subscribed = list
                .where((skill) => skill.hasSubscription)
                .toList(growable: false);
            final enabled =
                subscribed.isNotEmpty &&
                subscribed.every((skill) => skill.enabled);
            return _buildSwitchRow(
              label: entry.key,
              desc: subscribed.isEmpty
                  ? AssistantText.assistantSkillCenterNoSubscribedSkills
                  : l10n.assistantSkillCenterSubscribedCount(subscribed.length),
              value: enabled,
              onChanged: subscribed.isEmpty
                  ? null
                  : (value) => _togglePackage(subscribed, value),
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
            );
          }),
        ],
      ),
    );
  }

  Widget _buildTasksSection({
    required AsyncValue<List<AssistantUserTaskView>> tasksAsync,
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
            AssistantText.assistantSkillCenterOngoingTasksTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          tasksAsync.when(
            loading: () => Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
              child: const CupertinoActivityIndicator(),
            ),
            error: (error, _) => AppSectionErrorCard(
              margin: EdgeInsets.zero,
              semantic: runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.sectionLoad,
                scope: UiErrorScope.section,
              ),
              onAction: (action) async {
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  ref.invalidate(assistantScheduleTasksProvider);
                }
              },
            ),
            data: (tasks) {
              final ongoingTasks = tasks
                  .where(_isOngoingTask)
                  .toList(growable: false);
              if (ongoingTasks.isEmpty) {
                return Text(
                  AssistantText.assistantSkillCenterNoOngoingTasks,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                );
              }
              return Column(
                children: ongoingTasks
                    .map(
                      (task) => Padding(
                        padding: EdgeInsets.only(
                          bottom: AppSpacing.intraGroupSm,
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              CupertinoIcons.clock,
                              size: AppSpacing.iconSmall,
                              color: AppColors.primaryColor,
                            ),
                            SizedBox(width: AppSpacing.intraGroupSm),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    task.title.trim().isEmpty
                                        ? AssistantText.assistantTaskUntitled
                                        : task.title.trim(),
                                    style: TextStyle(
                                      fontSize: AppTypography.sm,
                                      color: fgPrimary,
                                    ),
                                  ),
                                  Text(
                                    _taskDetailLabel(task),
                                    style: TextStyle(
                                      fontSize: AppTypography.xs,
                                      color: fgSecondary,
                                      height: AppTypography.lineHeightCompact,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                    .toList(growable: false),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildSessionsSection({
    required AppLocalizations l10n,
    required AsyncValue<List<AssistantConversationWire>> sessionsAsync,
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
          sessionsAsync.when(
            loading: () => Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
              child: const CupertinoActivityIndicator(),
            ),
            error: (error, _) => AppSectionErrorCard(
              margin: EdgeInsets.zero,
              semantic: runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.sectionLoad,
                scope: UiErrorScope.section,
              ),
              onAction: (action) async {
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  ref.invalidate(assistantRecentSessionsProvider);
                }
              },
            ),
            data: (sessions) {
              if (sessions.isEmpty) {
                return Text(
                  l10n.assistantSkillCenterNoRecentSessions,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                );
              }
              final visibleSessions = _recentSessionsExpanded
                  ? sessions
                  : sessions.take(
                      _AssistantSkillCenterPageState._recentSessionPreviewLimit,
                    );
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ...visibleSessions.map((item) {
                    final topicTitle = item.summary.trim();
                    final updatedLabel = _conversationUpdatedLabel(
                      l10n,
                      item.updatedAt,
                    );
                    return CupertinoButton(
                      key: ValueKey<String>(
                        'assistant_recent_session_${item.conversationId}',
                      ),
                      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
                      minimumSize: const Size.square(
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => _openConversation(item.conversationId),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  topicTitle.isEmpty
                                      ? AssistantText.assistantHistoryUntitled
                                      : topicTitle,
                                  style: TextStyle(
                                    fontSize: AppTypography.sm,
                                    color: fgPrimary,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                Text(
                                  updatedLabel.isEmpty
                                      ? l10n.assistantSkillCenterNoLastMessage
                                      : updatedLabel,
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
                          Icon(
                            CupertinoIcons.chevron_forward,
                            size: AppSpacing.iconSmall,
                            color: fgSecondary,
                          ),
                        ],
                      ),
                    );
                  }),
                  if (sessions.length >
                      _AssistantSkillCenterPageState._recentSessionPreviewLimit)
                    CupertinoButton(
                      key: const ValueKey<String>(
                        'assistant_recent_sessions_toggle',
                      ),
                      padding: EdgeInsets.symmetric(
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      minimumSize: const Size.square(
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: _toggleRecentSessionsExpanded,
                      child: Text(
                        _recentSessionsExpanded ? l10n.collapse : l10n.seeMore,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
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
                    '${_skillCategoryLabel(skill)} · '
                    '${_skillStatusLabel(skill)}',
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
            CupertinoSwitch(
              key: ValueKey<String>('assistant_skill_toggle_${skill.skillId}'),
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
    required ValueChanged<bool>? onChanged,
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
                SizedBox(height: AppSpacing.two),
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
}
