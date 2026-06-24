import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

part 'career_interest_page_widgets.dart';

class CareerInterestPage extends ConsumerStatefulWidget {
  const CareerInterestPage({super.key});

  @override
  ConsumerState<CareerInterestPage> createState() => _CareerInterestPageState();
}

class _CareerTagOption {
  const _CareerTagOption({
    required this.tagRef,
    required this.label,
    required this.parentTagRef,
    required this.parentLabel,
    required this.categoryId,
  });

  final String tagRef;
  final String label;
  final String parentTagRef;
  final String parentLabel;
  final String categoryId;
}

class _CareerInterestPageState extends ConsumerState<CareerInterestPage> {
  static const double _pagePadding = AppSpacing.containerMd;
  static const double _gridSpacing = 10;
  static const double _tagTileHeight = 62;

  final Map<String, _CareerTagOption> _tagByRef = <String, _CareerTagOption>{};
  final Map<String, List<_CareerTagOption>> _interestByCategory =
      <String, List<_CareerTagOption>>{};
  List<_CareerTagOption> _occupationOptions = const <_CareerTagOption>[];
  List<String> _initialInterestRefs = const <String>[];
  String _initialOccupationRef = '';
  String _occupationTagRef = '';
  List<String> _interestTagRefs = const <String>[];
  String _selectedCategoryId =
      UserProfileUIConfig.careerInterestCatalog.defaultInterestCategoryId;
  bool _loading = true;
  bool _loadFailed = false;
  bool _saving = false;
  bool _scrolling = false;

  bool get _isDirty =>
      _occupationTagRef != _initialOccupationRef ||
      !_sameOrderedList(_interestTagRefs, _initialInterestRefs);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadFailed = false;
    });
    try {
      final userRepo = ref.read(userProfileRepositoryProvider);
      final tagRepo = ref.read(tagRepositoryProvider);
      final snapshot = await userRepo.getProfileEditSnapshot();
      final occupationOptions = await _loadOccupationOptions(tagRepo);
      final interestByCategory = await _loadInterestOptions(tagRepo);
      final tagByRef = <String, _CareerTagOption>{};
      for (final option in occupationOptions) {
        tagByRef[option.tagRef] = option;
      }
      for (final options in interestByCategory.values) {
        for (final option in options) {
          tagByRef[option.tagRef] = option;
        }
      }
      await _resolveMissingSelectedTags(tagRepo, snapshot, tagByRef);
      if (!mounted) {
        return;
      }
      setState(() {
        _occupationOptions = occupationOptions;
        _interestByCategory
          ..clear()
          ..addAll(interestByCategory);
        _tagByRef
          ..clear()
          ..addAll(tagByRef);
        _initialOccupationRef = snapshot.occupationTagRef.trim();
        _occupationTagRef = _initialOccupationRef;
        _initialInterestRefs = _dedupe(snapshot.interestTagRefs);
        _interestTagRefs = List<String>.from(_initialInterestRefs);
        _loading = false;
        _loadFailed = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _loadFailed = true;
      });
    }
  }

  Future<List<_CareerTagOption>> _loadOccupationOptions(
    TagRepository tagRepo,
  ) async {
    final catalog = UserProfileUIConfig.careerInterestCatalog;
    final options = <_CareerTagOption>[];
    for (final category in catalog.occupationCategories) {
      final parentLabel = _categoryLabel(category);
      final children = await tagRepo.listChildren(category.tagRef);
      for (final child in children) {
        options.add(
          _CareerTagOption(
            tagRef: child.tagRef,
            label: _tagLabel(child.label, child.displayLabel),
            parentTagRef: category.tagRef,
            parentLabel: parentLabel,
            categoryId: category.id,
          ),
        );
      }
    }
    return options;
  }

  Future<Map<String, List<_CareerTagOption>>> _loadInterestOptions(
    TagRepository tagRepo,
  ) async {
    final catalog = UserProfileUIConfig.careerInterestCatalog;
    final result = <String, List<_CareerTagOption>>{};
    for (final category in catalog.interestCategories) {
      if (category.tagRef.trim().isEmpty) {
        continue;
      }
      final parentLabel = _categoryLabel(category);
      final children = await tagRepo.listChildren(category.tagRef);
      result[category.id] = <_CareerTagOption>[
        for (final child in children)
          _CareerTagOption(
            tagRef: child.tagRef,
            label: _tagLabel(child.label, child.displayLabel),
            parentTagRef: category.tagRef,
            parentLabel: parentLabel,
            categoryId: category.id,
          ),
      ];
    }
    result[UserProfileUIConfig
        .careerInterestCatalog
        .defaultInterestCategoryId] = _dedupeOptions(
      result.values.expand((options) => options),
    );
    return result;
  }

  Future<void> _resolveMissingSelectedTags(
    TagRepository tagRepo,
    ProfileEditSnapshotData snapshot,
    Map<String, _CareerTagOption> tagByRef,
  ) async {
    final refs = <String>[
      if (snapshot.occupationTagRef.trim().isNotEmpty)
        snapshot.occupationTagRef.trim(),
      ...snapshot.interestTagRefs,
    ];
    for (final ref in _dedupe(refs)) {
      if (tagByRef.containsKey(ref)) {
        continue;
      }
      final resolved = await tagRepo.resolveTag(ref);
      final parentRef = _parentRef(ref);
      tagByRef[ref] = _CareerTagOption(
        tagRef: ref,
        label: resolved.label.trim().isEmpty ? _leafLabel(ref) : resolved.label,
        parentTagRef: parentRef,
        parentLabel: _leafLabel(parentRef),
        categoryId: parentRef,
      );
    }
  }

  Future<void> _handleBack() async {
    if (!_isDirty) {
      Navigator.of(context).maybePop(false);
      return;
    }
    final action = await showAppActionSheet<String>(
      context,
      title: UITextConstants.careerInterestUnsavedTitle,
      sections: <AppActionSheetSection<String>>[
        AppActionSheetSection<String>(
          items: <AppActionSheetItem<String>>[
            AppActionSheetItem<String>(
              label: UITextConstants.editProfileSaveAction,
              value: 'save',
            ),
            AppActionSheetItem<String>(
              label: UITextConstants.careerInterestKeepEditing,
              value: 'keep',
            ),
            AppActionSheetItem<String>(
              label: UITextConstants.careerInterestDiscard,
              value: 'discard',
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!mounted) {
      return;
    }
    if (action == 'save') {
      await _save(closeAfterSave: true);
    } else if (action == 'discard') {
      Navigator.of(context).maybePop(false);
    }
  }

  Future<void> _save({bool closeAfterSave = true}) async {
    if (_saving) {
      return;
    }
    if (!_isDirty) {
      AppToast.show(context, UITextConstants.careerInterestSaved);
      return;
    }
    setState(() => _saving = true);
    try {
      final refs = <String>[
        if (_occupationTagRef.trim().isNotEmpty) _occupationTagRef.trim(),
        ..._interestTagRefs,
      ];
      final validation = await ref
          .read(tagRepositoryProvider)
          .validateRefs(refs);
      if (validation.invalid.isNotEmpty) {
        throw StateError(validation.invalid.join(','));
      }
      await ref
          .read(userProfileRepositoryProvider)
          .updateProfile(
            ProfileEditUpdatePayload(
              occupationTagRef: _occupationTagRef,
              interestTagRefs: _interestTagRefs,
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.careerInterestSaved);
      setState(() {
        _initialOccupationRef = _occupationTagRef;
        _initialInterestRefs = List<String>.from(_interestTagRefs);
        _saving = false;
      });
      if (closeAfterSave && mounted) {
        Navigator.of(context).pop(true);
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _saving = false);
      AppToast.show(context, UITextConstants.careerInterestSaveFailed);
    }
  }

  Future<void> _pickOccupation() async {
    final selected = await Navigator.of(context).push<String>(
      CupertinoPageRoute<String>(
        builder: (_) => _OccupationPickerPage(
          options: _occupationOptions,
          selectedTagRef: _occupationTagRef,
        ),
      ),
    );
    if (selected == null || !mounted) {
      return;
    }
    setState(() => _occupationTagRef = selected);
  }

  void _removeInterest(String tagRef) {
    setState(() {
      _interestTagRefs = _interestTagRefs
          .where((ref) => ref != tagRef)
          .toList(growable: false);
    });
  }

  void _addInterest(String tagRef) {
    if (_interestTagRefs.contains(tagRef)) {
      return;
    }
    if (_interestTagRefs.length >=
        UserProfileUIConfig.careerInterestCatalog.maxInterestCount) {
      AppToast.show(context, UITextConstants.careerInterestMaxToast);
      return;
    }
    setState(() {
      _interestTagRefs = <String>[..._interestTagRefs, tagRef];
    });
  }

  void _reorderInterest(int oldIndex, int newIndex) {
    final next = List<String>.from(_interestTagRefs);
    if (oldIndex < 0 || oldIndex >= next.length) {
      return;
    }
    final item = next.removeAt(oldIndex);
    final insertIndex = (newIndex > oldIndex ? newIndex - 1 : newIndex)
        .clamp(0, next.length)
        .toInt();
    next.insert(insertIndex, item);
    setState(() => _interestTagRefs = next);
  }

  @override
  Widget build(BuildContext context) {
    final background = const Color(0xFFF7FAFF);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          unawaited(_handleBack());
        }
      },
      child: AppScaffold(
        backgroundColor: background,
        navigationBar: AppNavigationBar(
          backgroundColor: background,
          border: null,
          automaticallyImplyLeading: false,
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () => unawaited(_handleBack()),
          ),
          middle: const Text(UITextConstants.careerInterestTitle),
          trailing: CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(
              AppSpacing.appChromeActionButtonSize,
              AppSpacing.appChromeTextActionMinHeight,
            ),
            onPressed: _saving ? null : () => unawaited(_save()),
            child: Text(
              _saving
                  ? UITextConstants.careerInterestSaving
                  : UITextConstants.editProfileSaveAction,
              style: TextStyle(
                color: _saving
                    ? AppColors.iosTertiaryLabel(context)
                    : AppColors.iosAccent(context),
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        ),
        child: _buildBody(context),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_loadFailed) {
      return Center(
        child: CupertinoButton(
          onPressed: () => unawaited(_load()),
          child: const Text(UITextConstants.careerInterestLoadingFailed),
        ),
      );
    }
    return NotificationListener<ScrollNotification>(
      onNotification: (notification) {
        if (notification is ScrollStartNotification && !_scrolling) {
          setState(() => _scrolling = true);
        } else if (notification is ScrollEndNotification && _scrolling) {
          setState(() => _scrolling = false);
        }
        return false;
      },
      child: CustomScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        slivers: <Widget>[
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              _pagePadding,
              AppSpacing.containerLg,
              _pagePadding,
              AppSpacing.containerXl,
            ),
            sliver: SliverList.list(
              children: <Widget>[
                _SectionTitle(
                  title: UITextConstants.careerInterestOccupationSection,
                ),
                const SizedBox(height: AppSpacing.containerSm),
                _OccupationRow(
                  label: _occupationDisplay,
                  onTap: _pickOccupation,
                ),
                const SizedBox(height: 34),
                _SectionTitle(
                  title: UITextConstants.careerInterestMyTagsSection,
                ),
                const SizedBox(height: AppSpacing.containerXs),
                Text(
                  UITextConstants.careerInterestMyTagsHint,
                  style: TextStyle(
                    color: AppColors.iosSecondaryLabel(context),
                    fontSize: AppTypography.iosSubheadline,
                    height: 1.25,
                  ),
                ),
                const SizedBox(height: AppSpacing.containerMd),
                _buildMyTags(context),
                const SizedBox(height: 34),
                _SectionTitle(title: UITextConstants.careerInterestAllSection),
                const SizedBox(height: AppSpacing.containerMd),
                _buildCategoryTabs(context),
                const SizedBox(height: AppSpacing.containerLg),
                _buildAllTags(context),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMyTags(BuildContext context) {
    if (_interestTagRefs.isEmpty) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerLg,
        ),
        decoration: _cardDecoration(context),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              UITextConstants.careerInterestMyTagsEmptyHint,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
                height: 1.3,
              ),
            ),
            const SizedBox(height: AppSpacing.containerSm),
            Text(
              UITextConstants.careerInterestMyTagsEmpty,
              style: TextStyle(
                color: AppColors.iosTertiaryLabel(context),
                fontSize: AppTypography.iosBody,
              ),
            ),
          ],
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth < 360 ? 3 : 4;
        final width =
            (constraints.maxWidth - _gridSpacing * (columns - 1)) / columns;
        final reduceMotion = MediaQuery.disableAnimationsOf(context);
        return MediaReorderableView(
          itemCount: _interestTagRefs.length,
          itemSize: Size(width, _tagTileHeight),
          crossAxisCount: columns,
          spacing: _gridSpacing,
          runSpacing: _gridSpacing,
          enabled: _interestTagRefs.length > 1,
          onReorder: _reorderInterest,
          onDragStart: (_) => setState(() => _scrolling = true),
          onDragEnd: () => setState(() => _scrolling = false),
          itemBuilder: (context, index, isDragging) {
            final ref = _interestTagRefs[index];
            final option = _tagByRef[ref];
            return _InterestTagTile(
              label: option?.label ?? _leafLabel(ref),
              mode: _TagTileMode.remove,
              wiggle: !reduceMotion && !_scrolling && !isDragging,
              isDragging: isDragging,
              onTap: null,
              onAction: () => _removeInterest(ref),
            );
          },
        );
      },
    );
  }

  Widget _buildCategoryTabs(BuildContext context) {
    final categories =
        UserProfileUIConfig.careerInterestCatalog.interestCategories;
    return Container(
      height: 44,
      padding: const EdgeInsets.all(AppSpacing.containerXs),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen + 2),
        border: Border.all(color: const Color(0xFFE5ECF5)),
      ),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        itemBuilder: (context, index) {
          final category = categories[index];
          final selected = category.id == _selectedCategoryId;
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => setState(() => _selectedCategoryId = category.id),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              curve: Curves.easeOut,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.containerMd,
              ),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected ? AppColors.iosAccent(context) : null,
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              ),
              child: Text(
                _categoryLabel(category),
                style: TextStyle(
                  color: selected
                      ? CupertinoColors.white
                      : AppColors.iosSecondaryLabel(context),
                  fontSize: AppTypography.iosBody,
                  fontWeight: selected
                      ? AppTypography.semiBold
                      : AppTypography.regular,
                ),
              ),
            ),
          );
        },
        separatorBuilder: (_, _) =>
            const SizedBox(width: AppSpacing.containerXs),
        itemCount: categories.length,
      ),
    );
  }

  Widget _buildAllTags(BuildContext context) {
    final selected = _interestTagRefs.toSet();
    final options =
        (_interestByCategory[_selectedCategoryId] ?? const <_CareerTagOption>[])
            .where((option) => !selected.contains(option.tagRef))
            .toList(growable: false);
    if (options.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.containerXl),
        child: Center(
          child: Text(
            UITextConstants.careerInterestEmptyCategory,
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.iosSubheadline,
            ),
          ),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth < 360 ? 3 : 4;
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisExtent: _tagTileHeight,
            mainAxisSpacing: _gridSpacing,
            crossAxisSpacing: _gridSpacing,
          ),
          itemBuilder: (context, index) {
            final option = options[index];
            return _InterestTagTile(
              label: option.label,
              mode: _TagTileMode.add,
              onTap: () => _addInterest(option.tagRef),
              onAction: () => _addInterest(option.tagRef),
            );
          },
          itemCount: options.length,
        );
      },
    );
  }

  String get _occupationDisplay {
    if (_occupationTagRef.trim().isEmpty) {
      return UITextConstants.careerInterestSelectOccupation;
    }
    final option = _tagByRef[_occupationTagRef];
    if (option == null) {
      return _leafLabel(_occupationTagRef);
    }
    return '${option.parentLabel} · ${option.label}';
  }

  static BoxDecoration _cardDecoration(BuildContext context) => BoxDecoration(
    color: AppColors.iosSystemBackground(context),
    borderRadius: BorderRadius.circular(14),
    border: Border.all(color: const Color(0xFFE5ECF5)),
    boxShadow: <BoxShadow>[
      BoxShadow(
        color: CupertinoColors.black.withValues(alpha: 0.025),
        blurRadius: 18,
        offset: const Offset(0, 8),
      ),
    ],
  );
}
