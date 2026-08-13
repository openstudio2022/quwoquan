import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/layout/ios_selection_page_components.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show TagChildView;

/// creator_chip 采集通道的候选轴。
///
/// 真相源是 quwoquan_data taxonomy 中 `collectionChannel=creator_chip` 的节点
/// 分布（由 `quwoquan_ops/gate/verify_tag_collection_wiring.py` 按通道计数）；
/// 此处只声明创作者可见的分组入口，叶子标签经 tag-service `listChildren`
/// 实时拉取，标签树本身不进 App 包。分组标题取 tagRef 尾段，不复制第二份文案。
const List<String> kCreatorChipAxes = <String>[
  'Topic/旅行/同行人',
  'Topic/旅行/预算档次',
  'Topic/旅行/体能强度',
  'Format/视觉风格/后期风格',
  'Topic/摄影',
];

/// 单次发布可声明的内容标签上限（与 contentTagsPickerHint 文案一致）。
const int kCreatorChipSelectionLimit = 5;

/// 创作页打标 chip（creator_chip 采集通道的生产写入点）。
///
/// 创作者在发布确认阶段主动声明内容语义标签（同行人/预算/体能/后期风格/
/// 摄影主题），选中结果写入 `PublishSettings.tagRefs` 并随发布 payload 进入
/// 推荐召回与交集消费。某一轴加载失败只降级该分组，不阻断其余轴与发布。
class PublishTagChipPickerPage extends ConsumerStatefulWidget {
  const PublishTagChipPickerPage({super.key, required this.initialTagRefs});

  final List<String> initialTagRefs;

  @override
  ConsumerState<PublishTagChipPickerPage> createState() =>
      _PublishTagChipPickerPageState();
}

class _AxisChips {
  const _AxisChips({required this.axisTagRef, required this.chips, this.failed = false});

  final String axisTagRef;
  final List<TagChildView> chips;
  final bool failed;

  String get title => axisTagRef.split('/').last;
}

class _PublishTagChipPickerPageState
    extends ConsumerState<PublishTagChipPickerPage> {
  late Set<String> _selected;
  List<_AxisChips>? _axes;

  @override
  void initState() {
    super.initState();
    _selected = Set<String>.from(widget.initialTagRefs);
    _loadAxes();
  }

  Future<void> _loadAxes() async {
    final catalog = ref.read(tagCatalogQueryProvider);
    final loaded = await Future.wait(
      kCreatorChipAxes.map((axis) async {
        try {
          final children = await catalog.listChildren(axis);
          return _AxisChips(axisTagRef: axis, chips: children);
        } catch (_) {
          // 单轴失败只降级该分组（网络/标签树覆盖问题不阻断发布流程）。
          return _AxisChips(
            axisTagRef: axis,
            chips: const <TagChildView>[],
            failed: true,
          );
        }
      }),
    );
    if (!mounted) return;
    setState(() {
      _axes = loaded;
    });
  }

  void _toggle(String tagRef) {
    setState(() {
      if (_selected.contains(tagRef)) {
        _selected.remove(tagRef);
      } else if (_selected.length < kCreatorChipSelectionLimit) {
        _selected.add(tagRef);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final axes = _axes;
    return IosSelectionPageScaffold(
      pageKey: const ValueKey<String>('publish-tag-chip-picker-page'),
      title: CreationText.contentTagsPickerTitle,
      onBack: () => Navigator.of(context).pop(),
      backgroundColor: AppColors.iosPageBackground(context),
      body: axes == null
          ? AppRequestFeedback.page()
          : ListView(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerSm,
                AppSpacing.containerMd,
                AppSpacing.interGroupLg,
              ),
              children: <Widget>[
                Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.interGroupSm),
                  child: Text(
                    CreationText.contentTagsPickerHint,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ),
                for (final axis in axes) ...<Widget>[
                  IosSelectionSectionHeader(title: axis.title),
                  if (axis.failed)
                    Padding(
                      padding: EdgeInsets.only(
                        bottom: AppSpacing.interGroupSm,
                      ),
                      child: Text(
                        CreationText.contentTagsAxisLoadFailed,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    )
                  else
                    Padding(
                      padding: EdgeInsets.only(
                        bottom: AppSpacing.interGroupSm,
                      ),
                      child: Wrap(
                        spacing: AppSpacing.sm,
                        runSpacing: AppSpacing.sm,
                        children: <Widget>[
                          for (final chip in axis.chips)
                            _TagChip(
                              label: chip.label,
                              selected: _selected.contains(chip.tagRef),
                              onTap: () => _toggle(chip.tagRef),
                            ),
                        ],
                      ),
                    ),
                ],
              ],
            ),
      bottomBar: IosSelectionBottomBar(
        confirmButtonKey: const ValueKey<String>(
          'publish-tag-chip-picker-confirm',
        ),
        confirmLabel: CreationText.contentTagsConfirm,
        onConfirm: () =>
            Navigator.of(context).pop(_selected.toList(growable: false)),
      ),
    );
  }
}

class _TagChip extends StatelessWidget {
  const _TagChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: AppSpacing.minInteractiveSize,
          minWidth: AppSpacing.minInteractiveSize,
        ),
        child: Container(
          alignment: Alignment.center,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: selected
                ? AppColors.primaryColor
                : AppColors.iosGroupedSurface(context),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(
              color: selected
                  ? AppColors.primaryColor
                  : AppColors.iosSeparator(context),
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: selected ? AppColors.white : AppColors.iosLabel(context),
            ),
          ),
        ),
      ),
    );
  }
}
