import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart'
    show runtimeFailureFromError;
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

final assistantHalfSheetPersonalizationProvider = FutureProvider.autoDispose
    .family<AssistantHalfSheetPersonalization, AssistantOpenContext>((
      ref,
      openContext,
    ) async {
      final personalizationFacet = ref.read(
        assistantPersonalizationFacetProvider,
      );
      await personalizationFacet.reportPageContext(
        context: openContext,
        userAction: 'open_assistant_entry',
      );
      final personalization = await personalizationFacet
          .getEntryPersonalization(context: openContext);
      final suggestedActions = await personalizationFacet.getSuggestedActions(
        context: openContext,
      );
      return AssistantHalfSheetPersonalization(
        welcomeMessage: personalization.welcomeMessage.trim(),
        chips: personalization.chips,
        suggestionLines: personalization.suggestionLines
            .map((line) => line.trim())
            .where((line) => line.isNotEmpty)
            .toList(growable: false),
        suggestedActions: suggestedActions.items,
      );
    });

class AssistantHalfSheetPersonalization {
  const AssistantHalfSheetPersonalization({
    required this.welcomeMessage,
    required this.chips,
    required this.suggestionLines,
    required this.suggestedActions,
  });

  final String welcomeMessage;
  final List<AssistantEntryPersonalizationChipView> chips;
  final List<String> suggestionLines;
  final List<SuggestedAction> suggestedActions;
}

/// 私助半弹窗：约 50% 屏高、可拖拽，展示欢迎句、推荐 chips、「当前适合干啥」、输入框与「进入完整对话」。
class AssistantHalfSheet extends ConsumerStatefulWidget {
  const AssistantHalfSheet({super.key, required this.openContext});

  final AssistantOpenContext openContext;

  @override
  ConsumerState<AssistantHalfSheet> createState() => _AssistantHalfSheetState();

  /// 展示半弹窗；调用方需传入已组装的 [AssistantOpenContext]。
  static Future<void> show(
    BuildContext modalContext,
    AssistantOpenContext assistantOpenContext,
  ) async {
    // 半屏助手入口曝光：复用 AppLog pageAccess 通道（telemetry catalog 暂无
    // half sheet 专属事件 id，事件进 catalog 需 metadata codegen 链解锁）。
    final trace = AppTraceContextStore.instance;
    unawaited(
      AppLogService.instance.writeEvent(
        logType: AppLogType.pageAccess,
        level: AppLogLevel.info,
        context: AppLogContext(
          sessionId: trace.sessionId,
          pageVisitId: trace.newPageVisitId(),
        ),
        payload: <String, Object?>{
          'event': 'open',
          'pageName': AppUiSurfaces.assistantHalfSheet.id,
          'sourceSurface': assistantOpenContext.source.name,
        },
        summaryPayload: <String, Object?>{
          'event': 'open',
          'pageName': AppUiSurfaces.assistantHalfSheet.id,
        },
      ),
    );
    if (!modalContext.mounted) {
      return;
    }
    await showModalBottomSheet<void>(
      context: modalContext,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => SizedBox(
        height: MediaQuery.sizeOf(sheetContext).height * 0.55,
        child: AssistantHalfSheet(openContext: assistantOpenContext),
      ),
    );
  }
}

class _AssistantHalfSheetState extends ConsumerState<AssistantHalfSheet> {
  final TextEditingController _inputController = TextEditingController();
  final FocusNode _inputFocusNode = FocusNode();

  @override
  void dispose() {
    _inputController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  /// chip 点击真实分发：按 actionType 落地真实指令或跳转。
  /// command → 进入会话页并携带指令；route → 跳转目标路由；setting → 打开设置。
  /// 仅在用户主动打开半弹窗时出现，无自动弹窗骚扰（克制出现）。
  void _dispatchChip(
    BuildContext context,
    AssistantEntryPersonalizationChipView chip,
  ) {
    switch (chip.actionType) {
      case 'route':
        switch (chip.value) {
          case 'circles':
            return _closeAndPush(AppRoutePaths.circles);
          case 'create':
            return _closeAndPush(AppRoutePaths.create());
        }
        return _closeAndPush(
          AppRoutePaths.assistantPersonal,
          extra: widget.openContext,
        );
      case 'setting':
        return _closeAndPush(AppRoutePaths.settings);
      case 'command':
      default:
        return _closeAndPush(
          AppRoutePaths.assistantPersonal,
          extra: widget.openContext.copyWith(
            hints: <String, dynamic>{
              ...widget.openContext.hints,
              'autoSendQuery': chip.label,
            },
          ),
        );
    }
  }

  void _dispatchSuggestedAction(SuggestedAction action) {
    _closeAndPush(
      AppRoutePaths.assistantPersonal,
      extra: widget.openContext.copyWith(
        hints: <String, dynamic>{
          ...widget.openContext.hints,
          'autoSendQuery': action.label,
          'suggestedActionId': action.actionId,
        },
      ),
    );
  }

  void _openFullConversation() {
    final query = _inputController.text.trim();
    final targetContext = query.isEmpty
        ? widget.openContext
        : widget.openContext.copyWith(
            hints: <String, dynamic>{
              ...widget.openContext.hints,
              'autoSendQuery': query,
            },
          );
    _closeAndPush(AppRoutePaths.assistantPersonal, extra: targetContext);
  }

  void _closeAndPush(String location, {Object? extra}) {
    final router = GoRouter.of(context);
    Navigator.of(context).pop();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(router.push(location, extra: extra));
    });
  }

  Future<void> _handlePersonalizationErrorAction(UiErrorAction action) async {
    switch (action.type) {
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        ref.invalidate(
          assistantHalfSheetPersonalizationProvider(widget.openContext),
        );
        return;
      case UiErrorActionType.openSettings:
        _closeAndPush(AppRoutePaths.assistantSkills);
        return;
      case UiErrorActionType.login:
        _closeAndPush(
          AppRoutePaths.login(redirect: AppRoutePaths.assistantPersonal),
        );
        return;
      case UiErrorActionType.openUpdate:
        return;
      case UiErrorActionType.dismiss:
        Navigator.of(context).pop();
        return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final containerMd =
        AppSpacing.semantic[DesignSemanticConstants
            .container]?[DesignSemanticConstants.md] ??
        AppSpacing.containerMd;
    final intraSm =
        AppSpacing.semantic[DesignSemanticConstants
            .intraGroup]?[DesignSemanticConstants.sm] ??
        AppSpacing.intraGroupSm;

    final personalizationAsync = ref.watch(
      assistantHalfSheetPersonalizationProvider(widget.openContext),
    );
    final personalization = personalizationAsync.maybeWhen(
      data: (value) => value,
      orElse: () => null,
    );
    final showLoadingSkeleton =
        personalizationAsync.isLoading && !personalizationAsync.hasValue;
    final welcome = personalization?.welcomeMessage ?? '';
    final chips =
        personalization?.chips ??
        const <AssistantEntryPersonalizationChipView>[];
    final suggestionLines =
        personalization?.suggestionLines ?? const <String>[];
    final suggestedActions =
        personalization?.suggestedActions ?? const <SuggestedAction>[];
    final personalizationError = personalizationAsync.hasError
        ? personalizationAsync.error
        : null;
    final personalizationFailure = personalizationError == null
        ? null
        : runtimeFailureFromError(personalizationError);
    final permissionRequired =
        personalizationFailure?.kind == RuntimeFailureKind.permission;
    final errorSemantic = personalizationError == null
        ? null
        : runtimeErrorSemantic(
            context,
            error: personalizationError,
            category: permissionRequired
                ? UiErrorCategory.permissionRequired
                : UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
            allowOpenSettings: permissionRequired,
            presentation: UiErrorPresentation.transientNotice,
            sourceSurfaceId: AppUiSurfaces.assistantHalfSheet.id,
          );

    return Container(
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.borderRadius * 2),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(height: intraSm),
            Container(
              width: AppSpacing.createEntrySheetHandleWidth,
              height: AppSpacing.createEntrySheetHandleHeight,
              decoration: BoxDecoration(
                color: fgSecondary.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
              ),
            ),
            SizedBox(height: containerMd),
            Row(
              children: [
                SizedBox(width: containerMd),
                AssistantAvatar(radius: AppSpacing.avatarUserSm / 2),
                SizedBox(width: intraSm),
                Expanded(
                  child: Text(
                    AppConceptConstants.assistantLabel,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                ),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                  onPressed: () => Navigator.of(context).pop(),
                  child: Icon(
                    CupertinoIcons.xmark,
                    color: fgSecondary,
                    size: AppSpacing.iconMedium,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
              ],
            ),
            SizedBox(height: containerMd),
            if (welcome.isNotEmpty)
              Padding(
                padding: EdgeInsets.symmetric(horizontal: containerMd),
                child: Text(
                  welcome,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: fgPrimary,
                  ),
                ),
              ),
            if (errorSemantic != null) ...[
              SizedBox(height: intraSm),
              AppTransientErrorNotice(
                margin: EdgeInsets.symmetric(horizontal: containerMd),
                semantic: errorSemantic,
                onAction: _handlePersonalizationErrorAction,
              ),
            ],
            if (showLoadingSkeleton) ...[
              SizedBox(height: containerMd),
              _AssistantHalfSheetLoadingSkeleton(
                color: fgSecondary.withValues(alpha: 0.18),
              ),
            ] else if (chips.isNotEmpty) ...[
              SizedBox(height: containerMd),
              Wrap(
                spacing: intraSm,
                runSpacing: intraSm,
                children: chips
                    .map(
                      (c) => ActionChip(
                        label: c.label,
                        onPressed: () => _dispatchChip(context, c),
                      ),
                    )
                    .toList(),
              ),
            ],
            if (suggestedActions.isNotEmpty || suggestionLines.isNotEmpty) ...[
              SizedBox(height: containerMd),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: containerMd),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    AssistantText.assistantHalfSheetSuggestionTitle,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                      color: fgSecondary,
                    ),
                  ),
                ),
              ),
              SizedBox(height: intraSm),
              if (suggestedActions.isNotEmpty)
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: containerMd),
                  child: Wrap(
                    spacing: intraSm,
                    runSpacing: intraSm,
                    children: suggestedActions
                        .map(
                          (action) => ActionChip(
                            label: action.label,
                            onPressed: () => _dispatchSuggestedAction(action),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ),
              ...suggestionLines.map(
                (s) => Padding(
                  padding: EdgeInsets.symmetric(horizontal: containerMd),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      s,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                ),
              ),
            ],
            const Spacer(),
            Padding(
              padding: EdgeInsets.fromLTRB(
                containerMd,
                intraSm,
                containerMd,
                containerMd,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _inputController,
                      focusNode: _inputFocusNode,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _openFullConversation(),
                      decoration: InputDecoration(
                        hintText:
                            AssistantText.assistantHalfSheetInputPlaceholder,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.borderRadius,
                          ),
                        ),
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: containerMd,
                          vertical: intraSm,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: intraSm),
                  CupertinoButton.filled(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.sm,
                    ),
                    onPressed: _openFullConversation,
                    child: Text(AssistantText.assistantHalfSheetEnterFullChat),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AssistantHalfSheetLoadingSkeleton extends StatelessWidget {
  const _AssistantHalfSheetLoadingSkeleton({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Column(
        children: <Widget>[
          for (final widthFactor in <double>[0.92, 0.68])
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
              child: FractionallySizedBox(
                widthFactor: widthFactor,
                alignment: Alignment.centerLeft,
                child: Container(
                  height: AppSpacing.intraGroupSm,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class ActionChip extends StatelessWidget {
  const ActionChip({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm + AppSpacing.xs,
          vertical: AppSpacing.xs,
        ),
        minimumSize: Size.zero,
        onPressed: onPressed,
        child: Text(
          label,
          style: TextStyle(fontSize: AppTypography.sm, color: fgPrimary),
        ),
      ),
    );
  }
}
