part of 'career_interest_page.dart';

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: TextStyle(
        color: AppColors.iosSecondaryLabel(context),
        fontSize: AppTypography.iosCallout,
        height: AppTypography.lineHeightTight,
        fontWeight: AppTypography.medium,
      ),
    );
  }
}

class _OccupationRow extends StatelessWidget {
  const _OccupationRow({
    required this.label,
    required this.isPlaceholder,
    required this.onTap,
  });

  final String label;
  final bool isPlaceholder;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        constraints: const BoxConstraints(minHeight: AppSpacing.buttonHeight),
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        decoration: _CareerInterestPageState._cardDecoration(context),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: isPlaceholder
                      ? AppColors.iosSecondaryLabel(context)
                      : AppColors.iosLabel(context),
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.regular,
                  height: AppTypography.lineHeightCompact,
                ),
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }
}

enum _TagTileMode { add, remove }

class _InterestTagTile extends StatefulWidget {
  const _InterestTagTile({
    required this.label,
    required this.mode,
    required this.onAction,
    this.onTap,
    this.wiggle = false,
    this.isDragging = false,
  });

  final String label;
  final _TagTileMode mode;
  final VoidCallback onAction;
  final VoidCallback? onTap;
  final bool wiggle;
  final bool isDragging;

  @override
  State<_InterestTagTile> createState() => _InterestTagTileState();
}

class _InterestTagTileState extends State<_InterestTagTile>
    with SingleTickerProviderStateMixin {
  AnimationController? _controller;

  // SingleTickerProviderStateMixin creates tickers via ancestor lookups, so the
  // controller must only be created while this element is still active.
  AnimationController _ensureWiggleController() =>
      _controller ??= AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1500),
      );

  void _startWiggle() {
    final controller = _ensureWiggleController();
    if (!controller.isAnimating) {
      controller.repeat(reverse: true);
    }
  }

  void _stopWiggle() {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    controller.stop();
    controller.value = 0;
  }

  @override
  void initState() {
    super.initState();
    if (widget.wiggle) {
      _startWiggle();
    }
  }

  @override
  void didUpdateWidget(covariant _InterestTagTile oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.wiggle) {
      _startWiggle();
    } else {
      _stopWiggle();
    }
  }

  @override
  void dispose() {
    final controller = _controller;
    _controller = null;
    controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final child = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: widget.mode == _TagTileMode.add
              ? AppColors.iosSystemBackground(context)
              : AppColors.iosTintedFill(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
          border: Border.all(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.42),
          ),
          boxShadow: widget.isDragging
              ? <BoxShadow>[
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.16),
                    blurRadius: AppSpacing.containerLg,
                    offset: const Offset(0, 8),
                  ),
                ]
              : null,
        ),
        child: Stack(
          children: <Widget>[
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                ),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Padding(
                    padding: const EdgeInsets.only(
                      right: AppSpacing.containerMd,
                    ),
                    child: Text(
                      widget.label,
                      maxLines: 1,
                      style: TextStyle(
                        color: AppColors.iosLabel(context),
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.regular,
                        height: AppTypography.lineHeightTight,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              top: 0,
              right: 0,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: widget.onAction,
                child: SizedBox(
                  width: AppSpacing.iconButtonMinSizeSm,
                  height: AppSpacing.iconButtonMinSizeSm,
                  child: Align(
                    alignment: Alignment.topRight,
                    child: Padding(
                      padding: const EdgeInsets.only(
                        top: AppSpacing.containerXs,
                        right: AppSpacing.containerXs,
                      ),
                      child: Icon(
                        widget.mode == _TagTileMode.add
                            ? CupertinoIcons.plus
                            : CupertinoIcons.xmark,
                        size: AppSpacing.iconSmall,
                        color: widget.mode == _TagTileMode.add
                            ? AppColors.iosAccent(context)
                            : AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
    if (!widget.wiggle) {
      return child;
    }
    final controller = _controller;
    if (controller == null) {
      return child;
    }
    return AnimatedBuilder(
      animation: controller,
      builder: (context, child) {
        final angle = math.sin(controller.value * math.pi * 2) * 0.014;
        return Transform.rotate(angle: angle, child: child);
      },
      child: child,
    );
  }
}

class _OccupationPickerPage extends StatelessWidget {
  const _OccupationPickerPage({
    required this.options,
    required this.selectedTagRef,
  });

  final List<_CareerTagOption> options;
  final String selectedTagRef;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final groups = _occupationGroups(options);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.careerInterestOccupationPickerTitle,
      onBack: () => Navigator.of(context).maybePop(),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerXl,
        ),
        children: <Widget>[
          SettingsInsetGroupedSection(
            isDark: isDark,
            density: SettingsInsetSectionDensity.compact,
            child: Column(
              children: <Widget>[
                for (var i = 0; i < groups.length; i++) ...<Widget>[
                  _OccupationCategoryRow(
                    group: groups[i],
                    selectedOption: _selectedOptionIn(
                      groups[i].options,
                      selectedTagRef,
                    ),
                  ),
                  if (i != groups.length - 1)
                    SettingsInsetFormSectionDivider(isDark: isDark),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _OccupationCategoryRow extends StatelessWidget {
  const _OccupationCategoryRow({
    required this.group,
    required this.selectedOption,
  });

  final _OccupationCategoryGroup group;
  final _CareerTagOption? selectedOption;

  Future<void> _openChildren(BuildContext context) async {
    final selected = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _OccupationLeafPickerPage(
          group: group,
          selectedTagRef: selectedOption?.tagRef ?? '',
        ),
      ),
    );
    if (selected != null && context.mounted) {
      Navigator.of(context).pop(selected);
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = selectedOption;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => unawaited(_openChildren(context)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppSpacing.buttonHeight),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                group.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.regular,
                  height: AppTypography.lineHeightCompact,
                ),
              ),
            ),
            if (selected != null)
              Flexible(
                child: Padding(
                  padding: const EdgeInsets.only(left: AppSpacing.containerSm),
                  child: Text(
                    selected.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.right,
                    style: TextStyle(
                      color: AppColors.iosSecondaryLabel(context),
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.regular,
                      height: AppTypography.lineHeightCompact,
                    ),
                  ),
                ),
              ),
            const SizedBox(width: AppSpacing.containerXs),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }
}

class _OccupationLeafPickerPage extends StatelessWidget {
  const _OccupationLeafPickerPage({
    required this.group,
    required this.selectedTagRef,
  });

  final _OccupationCategoryGroup group;
  final String selectedTagRef;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: group.label,
      onBack: () => Navigator.of(context).maybePop(),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerXl,
        ),
        children: <Widget>[
          SettingsInsetGroupedSection(
            isDark: isDark,
            density: SettingsInsetSectionDensity.compact,
            child: Column(
              children: <Widget>[
                for (var i = 0; i < group.options.length; i++) ...<Widget>[
                  _OccupationLeafRow(
                    option: group.options[i],
                    selected: group.options[i].tagRef == selectedTagRef,
                  ),
                  if (i != group.options.length - 1)
                    SettingsInsetFormSectionDivider(isDark: isDark),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _OccupationLeafRow extends StatelessWidget {
  const _OccupationLeafRow({required this.option, required this.selected});

  final _CareerTagOption option;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => Navigator.of(context).pop(option.tagRef),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppSpacing.buttonHeight),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                option.label,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.regular,
                  height: AppTypography.lineHeightCompact,
                ),
              ),
            ),
            if (selected)
              Icon(
                CupertinoIcons.check_mark,
                size: AppSpacing.iconSmall,
                color: AppColors.iosAccent(context),
              ),
          ],
        ),
      ),
    );
  }
}

class _OccupationCategoryGroup {
  const _OccupationCategoryGroup({
    required this.tagRef,
    required this.label,
    required this.options,
  });

  final String tagRef;
  final String label;
  final List<_CareerTagOption> options;
}

List<_OccupationCategoryGroup> _occupationGroups(
  List<_CareerTagOption> options,
) {
  final parentRefs = <String>[];
  final parentLabels = <String, String>{};
  final grouped = <String, List<_CareerTagOption>>{};
  for (final option in options) {
    final parentRef = option.parentTagRef;
    if (!grouped.containsKey(parentRef)) {
      parentRefs.add(parentRef);
      parentLabels[parentRef] = option.parentLabel;
      grouped[parentRef] = <_CareerTagOption>[];
    }
    grouped[parentRef]!.add(option);
  }
  return <_OccupationCategoryGroup>[
    for (final parentRef in parentRefs)
      _OccupationCategoryGroup(
        tagRef: parentRef,
        label: parentLabels[parentRef] ?? _leafLabel(parentRef),
        options: grouped[parentRef] ?? const <_CareerTagOption>[],
      ),
  ];
}

_CareerTagOption? _selectedOptionIn(
  List<_CareerTagOption> options,
  String selectedTagRef,
) {
  for (final option in options) {
    if (option.tagRef == selectedTagRef) {
      return option;
    }
  }
  return null;
}

String _tagLabel(String label, String displayLabel) {
  final display = displayLabel.trim();
  if (display.isNotEmpty) {
    return display;
  }
  return label.trim();
}

String _categoryLabel(UserCareerInterestCategoryConfig category) {
  switch (category.labelKey) {
    case 'career_interest_category_all':
      return UITextConstants.careerInterestCategoryAll;
    case 'career_interest_category_travel_photo':
      return UITextConstants.careerInterestCategoryTravelPhoto;
    case 'career_interest_category_campus':
      return UITextConstants.careerInterestCategoryCampus;
    case 'career_interest_category_life':
      return UITextConstants.careerInterestCategoryLife;
    case 'career_interest_category_art':
      return UITextConstants.careerInterestCategoryArt;
    case 'career_interest_category_tech':
      return UITextConstants.careerInterestCategoryTech;
    case 'career_occupation_category_product_ops':
      return UITextConstants.careerOccupationCategoryProductOps;
    case 'career_occupation_category_engineering':
      return UITextConstants.careerOccupationCategoryEngineering;
    case 'career_occupation_category_design':
      return UITextConstants.careerOccupationCategoryDesign;
    case 'career_occupation_category_student':
      return UITextConstants.careerOccupationCategoryStudent;
    case 'career_occupation_category_freelance':
      return UITextConstants.careerOccupationCategoryFreelance;
    default:
      return category.id;
  }
}

String _parentRef(String tagRef) {
  final parts = tagRef.split('/');
  if (parts.length <= 1) {
    return '';
  }
  return parts.take(parts.length - 1).join('/');
}

String _leafLabel(String tagRef) {
  final parts = tagRef.split('/').where((part) => part.trim().isNotEmpty);
  return parts.isEmpty ? tagRef : parts.last;
}

List<String> _dedupe(Iterable<String> values) {
  final seen = <String>{};
  final result = <String>[];
  for (final value in values) {
    final trimmed = value.trim();
    if (trimmed.isEmpty || !seen.add(trimmed)) {
      continue;
    }
    result.add(trimmed);
  }
  return result;
}

List<_CareerTagOption> _dedupeOptions(Iterable<_CareerTagOption> options) {
  final seen = <String>{};
  final result = <_CareerTagOption>[];
  for (final option in options) {
    if (seen.add(option.tagRef)) {
      result.add(option);
    }
  }
  return result;
}

bool _sameOrderedList(List<String> left, List<String> right) {
  if (left.length != right.length) {
    return false;
  }
  for (var i = 0; i < left.length; i++) {
    if (left[i] != right[i]) {
      return false;
    }
  }
  return true;
}
