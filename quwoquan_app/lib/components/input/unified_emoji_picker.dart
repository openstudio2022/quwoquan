// ignore_for_file: unnecessary_underscores

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 统一 Emoji 选择器：最近（为空则不显示）+ 七分类，单页从上到下依次展示，支持上下滑动与 Tab 切换，滚动时 Tab 联动；Tab 无胶囊、中性色，分类间无空行
class UnifiedEmojiPicker extends ConsumerStatefulWidget {
  const UnifiedEmojiPicker({
    super.key,
    required this.onEmojiSelected,
    this.showCloseButton = false,
    this.onClose,
  });

  final void Function(String char) onEmojiSelected;
  final bool showCloseButton;
  final VoidCallback? onClose;

  @override
  ConsumerState<UnifiedEmojiPicker> createState() => _UnifiedEmojiPickerState();
}

class _UnifiedEmojiPickerState extends ConsumerState<UnifiedEmojiPicker> {
  final ScrollController _scrollController = ScrollController();
  int _selectedTabIndex = 0;
  int _lastSectionCount = 8;
  static const int _maxSectionCount = 8;
  final List<double> _sectionOffsets = List.filled(_maxSectionCount, 0);

  static const List<String> _tabLabels = [
    UITextConstants.emojiRecent,
    UITextConstants.emojiCategorySmileys,
    UITextConstants.emojiCategoryTravel,
    UITextConstants.emojiCategoryAnimals,
    UITextConstants.emojiCategoryFood,
    UITextConstants.emojiCategoryDrink,
    UITextConstants.emojiCategoryActivity,
    UITextConstants.emojiCategoryObjects,
  ];

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final offset = _scrollController.offset;
    final n = _lastSectionCount;
    if (n <= 0) return;
    int idx = 0;
    for (int i = 0; i < n; i++) {
      if (offset >= _sectionOffsets[i]) idx = i;
    }
    if (idx != _selectedTabIndex && mounted) {
      setState(() => _selectedTabIndex = idx);
    }
  }

  void _syncTabFromScroll() {
    if (!_scrollController.hasClients || !mounted) return;
    final offset = _scrollController.offset;
    final n = _lastSectionCount;
    if (n <= 0) return;
    int idx = 0;
    for (int i = 0; i < n; i++) {
      if (offset >= _sectionOffsets[i]) idx = i;
    }
    if (idx != _selectedTabIndex) setState(() => _selectedTabIndex = idx);
  }

  void _scrollToSection(int index) {
    if (!_scrollController.hasClients) return;
    final target = _sectionOffsets[index].clamp(0.0, _scrollController.position.maxScrollExtent);
    _scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeInOut,
    );
    setState(() => _selectedTabIndex = index);
  }

  void _onEmojiTap(String char) {
    widget.onEmojiSelected(char);
    ref.read(emojiRepositoryProvider.future).then((repo) => repo.recordEmojiUsed(char));
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgColor = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary).withValues(alpha: 0.3);
    final repoAsync = ref.watch(emojiRepositoryProvider);
    final recentEntries = repoAsync.when(
      data: (r) => r.getRecentEntries(),
      loading: () => <EmojiEntry>[],
      error: (_, __) => <EmojiEntry>[],
    );

    final showRecent = recentEntries.isNotEmpty;
    final effectiveLabels = showRecent ? _tabLabels : _tabLabels.sublist(1);
    final sectionCount = effectiveLabels.length;
    _lastSectionCount = sectionCount;

    final horizontalPadding = SettingsSemanticConstants.blockHorizontalPadding;
    final spacing = SettingsSemanticConstants.emojiGridSpacing;
    final crossCount = 7;

    // 顺序与 _tabLabels 一致：表情、出行、动物、食物、饮料、活动、物体
    final sectionData = <List<EmojiEntry>>[
      if (showRecent) recentEntries,
      EmojiCatalog.getByCategory(emojiCategoryIds[0]), // smiley
      EmojiCatalog.getByCategory(emojiCategoryIds[5]), // travel
      EmojiCatalog.getByCategory(emojiCategoryIds[1]), // animal
      EmojiCatalog.getByCategory(emojiCategoryIds[2]), // food
      EmojiCatalog.getByCategory(emojiCategoryIds[3]), // drink
      EmojiCatalog.getByCategory(emojiCategoryIds[4]), // activity
      EmojiCatalog.getByCategory(emojiCategoryIds[6]), // object
    ];

    if (_selectedTabIndex >= sectionCount && sectionCount > 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _selectedTabIndex = 0);
      });
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncTabFromScroll());

    return Container(
      height: SettingsSemanticConstants.emojiPanelHeight,
      decoration: BoxDecoration(
        color: bg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: SettingsSemanticConstants.emojiTabBarHeight,
            child: Row(
              children: [
                Expanded(
                  child: ListView.builder(
                    scrollDirection: Axis.horizontal,
                    padding: EdgeInsets.only(
                      left: SettingsSemanticConstants.emojiTabPaddingHorizontal,
                      right: SettingsSemanticConstants.emojiTabPaddingHorizontal,
                    ),
                    itemCount: sectionCount,
                    itemBuilder: (context, i) {
                      final selected = _selectedTabIndex == i;
                      return Padding(
                        padding: EdgeInsets.only(
                          right: i < sectionCount - 1
                              ? SettingsSemanticConstants.emojiTabSpacing
                              : 0,
                        ),
                        child: GestureDetector(
                          onTap: () => _scrollToSection(i),
                          child: Center(
                            child: Text(
                              effectiveLabels[i],
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.normal,
                                color: selected
                                    ? fgColor
                                    : fgColor.withValues(alpha: 0.55),
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
                if (widget.showCloseButton)
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.square(AppSpacing.minInteractiveSize),
                    onPressed: widget.onClose,
                    child: const Icon(CupertinoIcons.xmark),
                  ),
              ],
            ),
          ),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth - horizontalPadding * 2;
                final cellSize = (width - (crossCount - 1) * spacing) / crossCount;
                final titleHeight = SettingsSemanticConstants.emojiSectionTitleHeight;
                final sectionGap = SettingsSemanticConstants.emojiSectionGap;

                double offset = 0;
                for (int i = 0; i < sectionCount; i++) {
                  _sectionOffsets[i] = offset;
                  final count = sectionData[i].length;
                  final rows = (count / crossCount).ceil();
                  final gridHeight = rows * (cellSize + spacing) - (rows > 0 ? spacing : 0);
                  offset += (i > 0 ? sectionGap : 0) + titleHeight + gridHeight;
                }

                return ListView.builder(
                  controller: _scrollController,
                  padding: EdgeInsets.only(
                    left: horizontalPadding,
                    right: horizontalPadding,
                    bottom: AppSpacing.sm,
                  ),
                  itemCount: sectionCount,
                  itemBuilder: (context, sectionIndex) {
                    final entries = sectionData[sectionIndex];
                    return Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (sectionIndex > 0) SizedBox(height: sectionGap),
                        SizedBox(
                          height: titleHeight,
                          child: Align(
                            alignment: Alignment.topLeft,
                            child: Text(
                              effectiveLabels[sectionIndex],
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: fgSecondary,
                                height: 1.0,
                              ),
                            ),
                          ),
                        ),
                        GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: crossCount,
                            childAspectRatio: 1,
                            crossAxisSpacing: spacing,
                            mainAxisSpacing: spacing,
                          ),
                          itemCount: entries.length,
                          itemBuilder: (context, index) {
                            final entry = entries[index];
                            return GestureDetector(
                              onTap: () => _onEmojiTap(entry.char),
                              child: Center(
                                child: Text(
                                  entry.char,
                                  style: TextStyle(
                                    fontSize: SettingsSemanticConstants.emojiIconFontSize,
                                    color: fgColor,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ],
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
