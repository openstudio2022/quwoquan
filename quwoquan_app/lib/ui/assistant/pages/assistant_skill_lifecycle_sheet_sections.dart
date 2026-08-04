part of 'assistant_skill_lifecycle_sheet.dart';

extension _AssistantSkillLifecycleSheetSections
    on _AssistantSkillLifecycleSheetState {
  bool get _isDark =>
      MediaQuery.platformBrightnessOf(context) == Brightness.dark;

  Color _semanticColor(ColorType type) =>
      AppColorsFunctional.getColor(_isDark, type);

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AssistantText.assistantSkillLifecycleTitle,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                  color: _semanticColor(ColorType.foregroundPrimary),
                ),
              ),
              Text(
                widget.skillName,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: _semanticColor(ColorType.foregroundSecondary),
                ),
              ),
            ],
          ),
        ),
        Semantics(
          button: true,
          label: FoundationText.close,
          child: CupertinoButton(
            key: const ValueKey<String>('assistant_skill_lifecycle_close'),
            padding: EdgeInsets.zero,
            minimumSize: const Size.square(AppSpacing.minInteractiveSize),
            onPressed: _coordinator.state.isBusy ? null : _close,
            child: const Icon(CupertinoIcons.xmark_circle_fill),
          ),
        ),
      ],
    );
  }

  Widget _buildActivitySection() {
    return _section(
      title: AssistantText.assistantSkillActivityTitle,
      child: switch ((_loadingActivities, _activityError, _activities)) {
        (true, _, _) => const Center(child: CupertinoActivityIndicator()),
        (false, final Object error, _) => AppSectionErrorCard(
          margin: EdgeInsets.zero,
          semantic: ensureRetryUiErrorSemantic(
            runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
            ),
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _loadActivities();
            }
          },
        ),
        (false, null, final SkillActivitySlice slice)
            when slice.items.isNotEmpty =>
          Column(
            children: slice.items
                .take(8)
                .map(_buildActivityRow)
                .toList(growable: false),
          ),
        _ => Text(
          AssistantText.assistantSkillActivityEmpty,
          style: TextStyle(
            fontSize: AppTypography.sm,
            color: _semanticColor(ColorType.foregroundSecondary),
          ),
        ),
      },
    );
  }

  Widget _buildActivityRow(SkillActivityView activity) {
    final occurredAt = DateTime.tryParse(activity.occurredAt)?.toLocal();
    final dataControlRequestId = activity.dataControlRequestId?.trim() ?? '';
    final canResume =
        activity.recoveryAction ==
            SkillActivityRecoveryAction.retryDataControl &&
        dataControlRequestId.isNotEmpty;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
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
                  assistantSkillActivityLabel(activity.displayKey),
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: _semanticColor(ColorType.foregroundPrimary),
                  ),
                ),
                if (occurredAt != null)
                  Text(
                    '${context.l10n.monthDayTemplate(occurredAt.month, occurredAt.day)} '
                    '${TimeOfDay.fromDateTime(occurredAt).format(context)}',
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: _semanticColor(ColorType.foregroundSecondary),
                    ),
                  ),
              ],
            ),
          ),
          if (canResume)
            CupertinoButton(
              key: ValueKey<String>(
                'assistant_skill_activity_resume_${activity.activityId}',
              ),
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(AppSpacing.minInteractiveSize),
              onPressed: _coordinator.state.isBusy
                  ? null
                  : () => _resumeDataControl(dataControlRequestId),
              child: const Text(AssistantText.assistantSkillDataControlResume),
            ),
        ],
      ),
    );
  }

  Widget _buildDataControlSection(SkillDataControlFlowState flow) {
    final request = flow.request;
    return _section(
      title: AssistantText.assistantSkillDataControlChoiceTitle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final action in SkillDataControlAction.values)
            _buildActionChoice(action, flow.isBusy),
          if (request != null) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              assistantSkillDataControlStatusLabel(request.status),
              key: const ValueKey<String>(
                'assistant_skill_data_control_status',
              ),
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: _semanticColor(ColorType.foregroundPrimary),
              ),
            ),
          ],
          SizedBox(height: AppSpacing.intraGroupSm),
          if (flow.phase == SkillDataControlFlowPhase.failed && request == null)
            CupertinoButton.filled(
              key: const ValueKey<String>(
                'assistant_skill_data_control_retry_create',
              ),
              onPressed: _retryCreate,
              child: const Text(
                AssistantText.assistantSkillDataControlUnknownResultRetry,
              ),
            )
          else if (flow.canConfirm)
            CupertinoButton.filled(
              key: const ValueKey<String>(
                'assistant_skill_data_control_resume_confirm',
              ),
              onPressed: () => _confirmCurrent(cancelOnReject: false),
              child: const Text(AssistantText.assistantSkillDataControlResume),
            )
          else
            CupertinoButton.filled(
              key: const ValueKey<String>(
                'assistant_skill_data_control_create',
              ),
              onPressed: flow.isBusy || _selectedActions.isEmpty
                  ? null
                  : _createDataControl,
              child: flow.isBusy
                  ? const CupertinoActivityIndicator(color: AppColors.white)
                  : const Text(AssistantText.assistantSkillDataControlCreate),
            ),
        ],
      ),
    );
  }

  Widget _buildActionChoice(SkillDataControlAction action, bool disabled) {
    final selected = _selectedActions.contains(action);
    return CupertinoButton(
      key: ValueKey<String>('assistant_skill_data_control_${action.wireName}'),
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: disabled
          ? null
          : () => setState(() {
              selected
                  ? _selectedActions.remove(action)
                  : _selectedActions.add(action);
            }),
      child: Row(
        children: [
          Icon(
            selected
                ? CupertinoIcons.check_mark_circled_solid
                : CupertinoIcons.circle,
            size: AppSpacing.iconSmall,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              assistantSkillDataControlActionLabel(action),
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: _semanticColor(ColorType.foregroundPrimary),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _section({required String title, required Widget child}) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: _semanticColor(ColorType.backgroundSecondary),
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
              color: _semanticColor(ColorType.foregroundPrimary),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          child,
        ],
      ),
    );
  }
}
