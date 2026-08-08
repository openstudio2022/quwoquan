import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show TimeOfDay;
import 'package:quwoquan_app/service/assistant_service/assistant/skill_activity_view/application/public/skill_activity_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/application/skill_data_control_coordinator.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'assistant_skill_lifecycle_sheet_sections.dart';

enum AssistantSkillLifecycleUiAction {
  opened,
  activityRefreshed,
  dataControlCreated,
  dataControlConfirmed,
  dataControlCancelled,
  dataControlResumed,
  closed,
}

Future<void> showAssistantSkillLifecycleSheet({
  required BuildContext context,
  required String skillId,
  required String skillName,
  required AssistantSkillActivityQuery activityQuery,
  required SkillDataControlProcessCommandWriter dataControlCommandWriter,
  required SkillDataControlProcessQuery dataControlQuery,
  required void Function(AssistantSkillLifecycleUiAction action)
  onProductAction,
}) {
  return showCupertinoModalPopup<void>(
    context: context,
    barrierDismissible: false,
    builder: (sheetContext) => _AssistantSkillLifecycleSheet(
      skillId: skillId,
      skillName: skillName,
      activityQuery: activityQuery,
      dataControlCommandWriter: dataControlCommandWriter,
      dataControlQuery: dataControlQuery,
      onProductAction: onProductAction,
    ),
  );
}

final class _AssistantSkillLifecycleSheet extends StatefulWidget {
  const _AssistantSkillLifecycleSheet({
    required this.skillId,
    required this.skillName,
    required this.activityQuery,
    required this.dataControlCommandWriter,
    required this.dataControlQuery,
    required this.onProductAction,
  });

  final String skillId;
  final String skillName;
  final AssistantSkillActivityQuery activityQuery;
  final SkillDataControlProcessCommandWriter dataControlCommandWriter;
  final SkillDataControlProcessQuery dataControlQuery;
  final void Function(AssistantSkillLifecycleUiAction action) onProductAction;

  @override
  State<_AssistantSkillLifecycleSheet> createState() =>
      _AssistantSkillLifecycleSheetState();
}

final class _AssistantSkillLifecycleSheetState
    extends State<_AssistantSkillLifecycleSheet> {
  late final SkillDataControlCoordinator _coordinator;
  final Set<SkillDataControlAction> _selectedActions =
      <SkillDataControlAction>{};
  SkillActivitySlice? _activities;
  Object? _activityError;
  bool _loadingActivities = true;

  void _toggleSelectedAction(SkillDataControlAction action) {
    setState(() {
      if (!_selectedActions.remove(action)) {
        _selectedActions.add(action);
      }
    });
  }

  @override
  void initState() {
    super.initState();
    _coordinator = SkillDataControlCoordinator(
      commandWriter: widget.dataControlCommandWriter,
      query: widget.dataControlQuery,
      onStateChanged: (_) {
        if (mounted) setState(() {});
      },
    );
    widget.onProductAction(AssistantSkillLifecycleUiAction.opened);
    unawaited(_loadActivities());
  }

  @override
  Widget build(BuildContext context) {
    final flow = _coordinator.state;
    final isDark = MediaQuery.platformBrightnessOf(context) == Brightness.dark;
    return SafeArea(
      top: false,
      child: Container(
        height:
            MediaQuery.sizeOf(context).height *
            AppSpacing.modalSheetMaxHeightRatio,
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.intraGroupSm,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
        ),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundPrimary,
          ),
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(AppSpacing.largeBorderRadius),
          ),
        ),
        child: Column(
          children: [
            _buildHeader(context),
            Expanded(
              child: ListView(
                children: [
                  _buildActivitySection(),
                  SizedBox(height: AppSpacing.interGroupMd),
                  _buildDataControlSection(flow),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _loadActivities() async {
    setState(() {
      _loadingActivities = true;
      _activityError = null;
    });
    try {
      final result = await widget.activityQuery.listSkillActivities(
        skillId: widget.skillId,
      );
      if (!mounted) return;
      setState(() => _activities = result);
      widget.onProductAction(AssistantSkillLifecycleUiAction.activityRefreshed);
    } catch (error) {
      if (!mounted) return;
      setState(() => _activityError = error);
    } finally {
      if (mounted) setState(() => _loadingActivities = false);
    }
  }

  Future<void> _createDataControl() async {
    try {
      await _coordinator.create(
        skillId: widget.skillId,
        requestedActions: _selectedActions.toList(growable: false),
      );
      widget.onProductAction(
        AssistantSkillLifecycleUiAction.dataControlCreated,
      );
      if (!mounted) return;
      await _confirmCurrent(cancelOnReject: true);
    } catch (error) {
      // Coordinator 保留 typed 可恢复状态；页面不展示原始错误或敏感标识。
      await _showMutationError(error);
    }
  }

  Future<void> _retryCreate() async {
    try {
      await _coordinator.retryCreate();
      if (!mounted) return;
      await _confirmCurrent(cancelOnReject: true);
    } catch (error) {
      // 保留同一 idempotency intent，等待用户再次显式重试。
      await _showMutationError(error);
    }
  }

  Future<void> _resumeDataControl(String requestId) async {
    try {
      final state = await _coordinator.resume(requestId);
      widget.onProductAction(
        AssistantSkillLifecycleUiAction.dataControlResumed,
      );
      if (!mounted) return;
      if (state.canConfirm) {
        await _confirmCurrent(cancelOnReject: false);
      }
    } catch (error) {
      // Coordinator 保留同一 request 的当前状态。
      await _showMutationError(error);
    }
  }

  Future<void> _confirmCurrent({required bool cancelOnReject}) async {
    if (!_coordinator.state.canConfirm) return;
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(AssistantText.assistantSkillDataControlConfirmTitle),
        content: const Text(AssistantText.assistantSkillDataControlConfirmBody),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(AssistantText.assistantSkillDataControlCancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(AssistantText.assistantSkillDataControlConfirm),
          ),
        ],
      ),
    );
    if (!mounted) return;
    try {
      if (confirmed == true) {
        await _coordinator.confirm();
        widget.onProductAction(
          AssistantSkillLifecycleUiAction.dataControlConfirmed,
        );
      } else if (cancelOnReject) {
        await _coordinator.cancelPending();
        widget.onProductAction(
          AssistantSkillLifecycleUiAction.dataControlCancelled,
        );
      }
      await _loadActivities();
    } catch (error) {
      // 状态仍由 canonical request 表达，允许从同一 request 恢复。
      await _showMutationError(error);
    }
  }

  Future<void> _close() async {
    if (_coordinator.state.request?.status ==
        SkillDataControlRequestStatus.pendingConfirmation) {
      try {
        await _coordinator.cancelPending();
        widget.onProductAction(
          AssistantSkillLifecycleUiAction.dataControlCancelled,
        );
      } catch (error) {
        await _showMutationError(error);
        return;
      }
    }
    if (mounted) {
      widget.onProductAction(AssistantSkillLifecycleUiAction.closed);
      Navigator.of(context).pop();
    }
  }

  Future<void> _showMutationError(Object error) async {
    if (!mounted) return;
    await AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
    );
  }
}
