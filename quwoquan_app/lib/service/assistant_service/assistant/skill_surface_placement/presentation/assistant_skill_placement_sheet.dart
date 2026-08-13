import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show
        assistantSkillCatalogFacetProvider,
        assistantSkillSurfacePlacementFacetProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart'
    show ensureRetryUiErrorSemantic, runtimeErrorSemantic;
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/domain/skill_surface_placement_disabled_skills.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

/// Placement 的 surface 身份（provider family 参数）。
@immutable
final class AssistantSkillPlacementSurfaceRef {
  const AssistantSkillPlacementSurfaceRef({
    required this.surfaceKind,
    required this.surfaceId,
  });

  final SkillSurfaceKind surfaceKind;
  final String surfaceId;

  @override
  bool operator ==(Object other) {
    return other is AssistantSkillPlacementSurfaceRef &&
        other.surfaceKind == surfaceKind &&
        other.surfaceId == surfaceId;
  }

  @override
  int get hashCode => Object.hash(surfaceKind, surfaceId);
}

/// 共享放置面板的展示模型：placement 事实 + active package 目录。
final class AssistantSkillPlacementBoard {
  const AssistantSkillPlacementBoard({
    required this.placement,
    required this.catalog,
  });

  final SkillSurfacePlacement placement;
  final List<AssistantSkillCatalogItemView> catalog;

  bool isSkillDisabled(String skillId) =>
      SkillSurfacePlacementDisabledSkills.isDisabled(
        disabledSkillIds: placement.disabledSkillIds,
        skillId: skillId,
      );
}

/// 共享 Skill 放置事实的唯一读取面：服务端 placement + catalog 组合。
final assistantSkillPlacementBoardProvider = FutureProvider.autoDispose
    .family<AssistantSkillPlacementBoard, AssistantSkillPlacementSurfaceRef>((
      ref,
      surface,
    ) async {
      final placementFacet = ref.watch(
        assistantSkillSurfacePlacementFacetProvider,
      );
      final catalogFacet = ref.watch(assistantSkillCatalogFacetProvider);
      final results = await Future.wait<Object>(<Future<Object>>[
        placementFacet.getSkillSurfacePlacement(
          surfaceKind: surface.surfaceKind,
          surfaceId: surface.surfaceId,
        ),
        catalogFacet.listSkillCatalog(),
      ]);
      return AssistantSkillPlacementBoard(
        placement: results[0] as SkillSurfacePlacement,
        catalog: results[1] as List<AssistantSkillCatalogItemView>,
      );
    });

/// 打开群聊/圈子共享 Skill 策略管理面板。
Future<void> showAssistantSkillPlacementSheet({
  required BuildContext context,
  required SkillSurfaceKind surfaceKind,
  required String surfaceId,
}) {
  return showCupertinoModalPopup<void>(
    context: context,
    barrierDismissible: true,
    builder: (context) => AssistantSkillPlacementSheet(
      surface: AssistantSkillPlacementSurfaceRef(
        surfaceKind: surfaceKind,
        surfaceId: surfaceId,
      ),
    ),
  );
}

class AssistantSkillPlacementSheet extends ConsumerStatefulWidget {
  const AssistantSkillPlacementSheet({super.key, required this.surface});

  final AssistantSkillPlacementSurfaceRef surface;

  @override
  ConsumerState<AssistantSkillPlacementSheet> createState() =>
      _AssistantSkillPlacementSheetState();
}

class _AssistantSkillPlacementSheetState
    extends ConsumerState<AssistantSkillPlacementSheet> {
  /// 本地编辑中的禁用集合；null 表示尚未从服务端 placement 初始化。
  Set<String>? _disabledSkillIds;
  bool _saving = false;
  bool _saveFailed = false;

  @override
  Widget build(BuildContext context) {
    final theme = CupertinoTheme.of(context);
    final primary = theme.textTheme.textStyle.color ?? CupertinoColors.label;
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final grouped = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final boardAsync = ref.watch(
      assistantSkillPlacementBoardProvider(widget.surface),
    );
    return CupertinoPopupSurface(
      isSurfacePainted: true,
      child: Container(
        key: const ValueKey<String>('assistant_skill_placement_sheet'),
        height:
            MediaQuery.sizeOf(context).height *
            AppSpacing.modalSheetMaxHeightRatio,
        color: background,
        child: SafeArea(
          top: false,
          child: Column(
            children: [
              _buildHeader(context, primary, secondary),
              Expanded(
                child: boardAsync.when(
                  loading: AppRequestFeedback.section,
                  error: (error, _) => AppSectionErrorCard(
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
                        ref.invalidate(
                          assistantSkillPlacementBoardProvider(widget.surface),
                        );
                      }
                    },
                  ),
                  data: (board) => _buildBoard(
                    board,
                    primary: primary,
                    secondary: secondary,
                    grouped: grouped,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, Color primary, Color secondary) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm + AppSpacing.xs,
        AppSpacing.sm + AppSpacing.xs,
        AppSpacing.sm,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              AssistantText.assistantSkillPlacementTitle,
              style: CupertinoTheme.of(context).textTheme.navLargeTitleTextStyle
                  .copyWith(color: primary, fontSize: AppTypography.iosTitle2),
            ),
          ),
          CupertinoButton(
            key: const ValueKey<String>('assistant_skill_placement_close'),
            padding: const EdgeInsets.all(AppSpacing.sm),
            minimumSize: const Size.square(AppSpacing.minInteractiveSize),
            onPressed: () => Navigator.of(context).pop(),
            child: Icon(CupertinoIcons.xmark_circle_fill, color: secondary),
          ),
        ],
      ),
    );
  }

  Widget _buildBoard(
    AssistantSkillPlacementBoard board, {
    required Color primary,
    required Color secondary,
    required Color grouped,
  }) {
    final disabled =
        _disabledSkillIds ??
        board.placement.disabledSkillIds.toSet();
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.twenty,
        AppSpacing.sm,
        AppSpacing.twenty,
        AppSpacing.twentyEight,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(AppSpacing.fourteen),
            decoration: BoxDecoration(
              color: grouped,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  AssistantText.assistantSkillPlacementPolicyAllShared,
                  style: TextStyle(
                    color: primary,
                    fontSize: AppTypography.smPlus,
                    height: AppTypography.bodyLineHeight,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  AssistantText.assistantSkillPlacementAdminHint,
                  style: TextStyle(
                    color: secondary,
                    fontSize: AppTypography.sm,
                    height: AppTypography.bodyLineHeight,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.eighteen),
          ...board.catalog.map(
            (item) => Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.six),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          item.displayName,
                          style: TextStyle(color: primary),
                        ),
                        if ((item.description ?? '').trim().isNotEmpty)
                          Text(
                            item.description!.trim(),
                            style: TextStyle(
                              color: secondary,
                              fontSize: AppTypography.sm,
                              height: AppTypography.bodyLineHeight,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                      ],
                    ),
                  ),
                  CupertinoSwitch(
                    key: ValueKey<String>(
                      'assistant_skill_placement_toggle_${item.skillId}',
                    ),
                    value: !disabled.contains(item.skillId),
                    onChanged: _saving
                        ? null
                        : (enabled) => setState(() {
                            _disabledSkillIds =
                                SkillSurfacePlacementDisabledSkills.toggle(
                                  disabled: disabled,
                                  skillId: item.skillId,
                                  enabled: enabled,
                                );
                          }),
                  ),
                ],
              ),
            ),
          ),
          if (_saveFailed) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              AssistantText.assistantSkillPlacementSaveFailed,
              key: const ValueKey<String>('assistant_skill_placement_error'),
              style: TextStyle(
                color: CupertinoColors.systemRed.resolveFrom(context),
                fontSize: AppTypography.smPlus,
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.sm),
          CupertinoButton.filled(
            key: const ValueKey<String>('assistant_skill_placement_save'),
            onPressed: _saving || _disabledSkillIds == null
                ? null
                : () => _save(board),
            child: _saving
                ? AppRequestFeedback.inline()
                : const Text(AssistantText.assistantSkillPlacementSave),
          ),
        ],
      ),
    );
  }

  Future<void> _save(AssistantSkillPlacementBoard board) async {
    final edited = _disabledSkillIds;
    if (edited == null) {
      return;
    }
    setState(() {
      _saving = true;
      _saveFailed = false;
    });
    final normalized = SkillSurfacePlacementDisabledSkills.normalizeForSubmit(
      edited: edited,
      activeSkillIds: board.catalog.map((item) => item.skillId).toSet(),
    );
    try {
      await ref
          .read(assistantSkillSurfacePlacementFacetProvider)
          .putSkillSurfacePlacement(
            surfaceKind: widget.surface.surfaceKind,
            surfaceId: widget.surface.surfaceId,
            policy: board.placement.policy,
            disabledSkillIds: normalized,
            status: board.placement.status,
            expectedRevision: board.placement.revision,
            clientRequestId: const Uuid().v4(),
          );
      ref.invalidate(assistantSkillPlacementBoardProvider(widget.surface));
      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (_) {
      // 服务端是唯一状态源：失败后重新读取当前 placement 再让用户重试。
      ref.invalidate(assistantSkillPlacementBoardProvider(widget.surface));
      if (!mounted) {
        return;
      }
      setState(() {
        _saving = false;
        _saveFailed = true;
        _disabledSkillIds = null;
      });
    }
  }
}
