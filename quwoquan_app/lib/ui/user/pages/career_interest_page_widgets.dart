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
        fontSize: AppTypography.iosTitle3,
        height: 1.2,
        fontWeight: AppTypography.bold,
      ),
    );
  }
}

class _OccupationRow extends StatelessWidget {
  const _OccupationRow({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: 62,
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
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.medium,
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
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1500),
  );

  @override
  void initState() {
    super.initState();
    if (widget.wiggle) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(covariant _InterestTagTile oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.wiggle && !_controller.isAnimating) {
      _controller.repeat(reverse: true);
    } else if (!widget.wiggle && _controller.isAnimating) {
      _controller.stop();
      _controller.value = 0;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
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
              : const Color(0xFFF7FAFF),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen + 1),
          border: Border.all(
            color: widget.mode == _TagTileMode.add
                ? const Color(0xFFDDE8F6)
                : const Color(0xFFE3EAF5),
          ),
          boxShadow: widget.isDragging
              ? <BoxShadow>[
                  BoxShadow(
                    color: CupertinoColors.black.withValues(alpha: 0.16),
                    blurRadius: 18,
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
                  horizontal: AppSpacing.containerXs,
                ),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    widget.label,
                    maxLines: 1,
                    style: TextStyle(
                      color: AppColors.iosLabel(context),
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.medium,
                      letterSpacing: 0,
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
                  width: 30,
                  height: 30,
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
                            : AppColors.iosLabel(context),
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
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final angle = math.sin(_controller.value * math.pi * 2) * 0.022;
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
    final grouped = <String, List<_CareerTagOption>>{};
    for (final option in options) {
      grouped
          .putIfAbsent(option.parentLabel, () => <_CareerTagOption>[])
          .add(option);
    }
    return AppScaffold(
      backgroundColor: const Color(0xFFF7FAFF),
      navigationBar: AppNavigationBar(
        backgroundColor: const Color(0xFFF7FAFF),
        border: null,
        automaticallyImplyLeading: false,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        middle: const Text(UITextConstants.careerInterestOccupationPickerTitle),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerXl,
        ),
        children: <Widget>[
          for (final entry in grouped.entries) ...<Widget>[
            Padding(
              padding: const EdgeInsets.only(
                left: AppSpacing.containerXs,
                bottom: AppSpacing.containerXs,
                top: AppSpacing.containerSm,
              ),
              child: Text(
                entry.key,
                style: TextStyle(
                  color: AppColors.iosSecondaryLabel(context),
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            Container(
              decoration: _CareerInterestPageState._cardDecoration(context),
              child: Column(
                children: <Widget>[
                  for (var i = 0; i < entry.value.length; i++)
                    _OccupationOptionRow(
                      option: entry.value[i],
                      selected: entry.value[i].tagRef == selectedTagRef,
                      showDivider: i != entry.value.length - 1,
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _OccupationOptionRow extends StatelessWidget {
  const _OccupationOptionRow({
    required this.option,
    required this.selected,
    required this.showDivider,
  });

  final _CareerTagOption option;
  final bool selected;
  final bool showDivider;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => Navigator.of(context).pop(option.tagRef),
      child: Container(
        height: 52,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        decoration: BoxDecoration(
          border: showDivider
              ? Border(
                  bottom: BorderSide(
                    color: AppColors.iosSeparator(context),
                    width: AppSpacing.hairline,
                  ),
                )
              : null,
        ),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                option.label,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosBody,
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
      return '产品/运营';
    case 'career_occupation_category_engineering':
      return '研发/技术';
    case 'career_occupation_category_design':
      return '设计/创意';
    case 'career_occupation_category_student':
      return '学生';
    case 'career_occupation_category_freelance':
      return '自由职业';
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
