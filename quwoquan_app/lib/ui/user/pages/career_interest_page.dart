import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ReportTagFeedbackCommand, TagFeedbackAck, UpdateUserProfileCommand;
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
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
  static const double _gridSpacing = AppSpacing.ten;
  static const double _tagTileHeight =
      AppSpacing.minInteractiveSize + AppSpacing.ten;

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
  Object? _loadError;
  bool _saving = false;
  bool _scrolling = false;

  bool get _isDirty =>
      _occupationTagRef != _initialOccupationRef ||
      !_sameOrderedList(_interestTagRefs, _initialInterestRefs);

  late final DateTime _enteredAt;
  JourneyEventTracker? _journeyTracker;

  @override
  void initState() {
    super.initState();
    _enteredAt = DateTime.now();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _journeyTracker = ref.read(journeyEventTrackerProvider);
      unawaited(
        _journeyTracker!.trackAction(
          journey: 'career_interest',
          action: 'enter',
          pageName: 'CareerInterestPage',
        ),
      );
    });
    unawaited(_load());
  }

  @override
  void dispose() {
    final tracker = _journeyTracker;
    if (tracker != null) {
      unawaited(
        tracker.trackAction(
          journey: 'career_interest',
          action: 'exit',
          pageName: 'CareerInterestPage',
          payload: <String, dynamic>{
            'durationMs': DateTime.now().difference(_enteredAt).inMilliseconds,
          },
        ),
      );
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final profileEditQuery = ref.read(
        profileEditQueryProvider(AppUiSurfaces.profileCareerInterests),
      );
      final tagRepo = ref.read(tagCatalogQueryProvider);
      final snapshot = await profileEditQuery.getProfileEditSnapshot();
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
        _loadError = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _loadError = error;
      });
    }
  }

  Future<List<_CareerTagOption>> _loadOccupationOptions(
    TagCatalogQuery tagRepo,
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
    TagCatalogQuery tagRepo,
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
    TagCatalogQuery tagRepo,
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
      Navigator.of(context).pop(false);
      return;
    }
    final action = await showAppCupertinoDialog<String>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.careerInterestUnsavedTitle),
          content: const Text(UITextConstants.careerInterestUnsavedMessage),
          actions: <Widget>[
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop('save'),
              child: const Text(UITextConstants.editProfileSaveAction),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop('keep'),
              child: const Text(UITextConstants.careerInterestKeepEditing),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop('discard'),
              child: const Text(UITextConstants.careerInterestDiscard),
            ),
          ],
        );
      },
    );
    if (!mounted) {
      return;
    }
    if (action == 'save') {
      await _save(closeAfterSave: true);
    } else if (action == 'discard') {
      Navigator.of(context).pop(false);
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
          .read(tagCatalogQueryProvider)
          .validateRefs(refs);
      if (validation.invalid.isNotEmpty) {
        // 结构化校验失败：走 TAG.USER.invalid_tag_ref 语义（对齐 tag/errors.yaml），
        // 不抛裸 StateError（军规 R18）。
        throw CloudErrorMapper.invalidResponse(
          message: UITextConstants.careerInterestInvalidTagToast,
          requestPath: 'career-interest/validate',
          functionModule: 'career_interest_page',
        );
      }
      await ref
          .read(profileCommandWriterProvider)
          .updateUserProfile(
            UpdateUserProfileCommand(
              occupationTagRef: _occupationTagRef,
              interestTagRefs: _interestTagRefs,
            ),
          );
      // 兴趣采集回流推荐（N2-4，W11 interest-onboarding-prior）：保存成功的
      // 职业/兴趣 tagRefs 经 onboarding_interest 行为进 HotPath tag 先验，
      // 首刷 TagRecall 立即可用；只回流 tagRefs，不绑定 post。
      ref.read(contentBehaviorTrackerProvider).trackOnboardingInterest(refs);
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
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _saving = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _save(closeAfterSave: closeAfterSave);
          }
        },
      );
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
    _reportTagFeedback(tagRef: tagRef, action: 'ignore');
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
    _reportTagFeedback(tagRef: tagRef, action: 'click');
  }

  /// 标签添加/移除动作产出 TagFeedback 事实（fire-and-forget，不阻断编辑）。
  void _reportTagFeedback({required String tagRef, required String action}) {
    unawaited(
      ref
          .read(tagFeedbackCommandWriterProvider)
          .reportTagFeedback(
            ReportTagFeedbackCommand(tagRef: tagRef, action: action),
          )
          .catchError((Object error) {
            if (kDebugMode) {
              debugPrint('tag feedback degraded: $error');
            }
            return const TagFeedbackAck(accepted: false);
          }),
    );
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
    final background = AppColors.iosPageBackground(context);
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
          middle: Text(
            UITextConstants.careerInterestTitle,
            style: TextStyle(
              color: AppColors.iosLabel(context),
              fontSize: AppTypography.iosNavTitle,
              fontWeight: AppTypography.medium,
              height: AppTypography.lineHeightTight,
            ),
          ),
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
                fontWeight: AppTypography.medium,
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
    if (_loadError != null) {
      return AppPageErrorState(
        semantic: UiErrorSemanticResolver.resolve(
          context,
          error: _loadError!,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load();
          }
        },
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
                  isPlaceholder: _occupationTagRef.trim().isEmpty,
                  onTap: _pickOccupation,
                ),
                const SizedBox(height: AppSpacing.containerXl),
                _SectionTitle(
                  title: UITextConstants.careerInterestMyTagsSection,
                ),
                const SizedBox(height: AppSpacing.containerSm),
                _buildMyTags(context),
                const SizedBox(height: AppSpacing.containerXl),
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
      return SizedBox(
        width: double.infinity,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.containerXs,
          ),
          child: Text(
            UITextConstants.careerInterestMyTagsEmptyHint,
            style: TextStyle(
              color: AppColors.iosTertiaryLabel(context),
              fontSize: AppTypography.iosSubheadline,
              height: AppTypography.lineHeightCompact,
              fontWeight: AppTypography.regular,
            ),
          ),
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
      height: AppSpacing.minInteractiveSize,
      padding: const EdgeInsets.all(AppSpacing.containerXs),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(
          AppSpacing.radiusTen + AppSpacing.two,
        ),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.45),
        ),
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
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: selected
                      ? AppTypography.medium
                      : AppTypography.regular,
                  height: AppTypography.lineHeightTight,
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
    borderRadius: BorderRadius.circular(
      AppSpacing.radiusTen + AppSpacing.containerXs / 2,
    ),
    border: Border.all(
      color: AppColors.iosSeparator(context).withValues(alpha: 0.45),
    ),
  );
}
