import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/tag/tag/tag_node_view/application/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/media_reorderable_view.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
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
    required this.taxonomyReleaseId,
  });

  final String tagRef;
  final String label;
  final String parentTagRef;
  final String parentLabel;
  final String categoryId;
  final String taxonomyReleaseId;
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
  String _taxonomyReleaseId = '';
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
          payload: <String, Object?>{
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
      final taxonomyReleaseId = _requireSingleTaxonomyReleaseId(
        occupationOptions.followedBy(
          interestByCategory.values.expand((options) => options),
        ),
      );
      final tagByRef = <String, _CareerTagOption>{};
      for (final option in occupationOptions) {
        tagByRef[option.tagRef] = option;
      }
      for (final options in interestByCategory.values) {
        for (final option in options) {
          tagByRef[option.tagRef] = option;
        }
      }
      await _resolveMissingSelectedTags(
        tagRepo,
        snapshot,
        tagByRef,
        taxonomyReleaseId,
      );
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
        _taxonomyReleaseId = taxonomyReleaseId;
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
            label: _tagLabel(child.label, child.displayLabel ?? ''),
            parentTagRef: category.tagRef,
            parentLabel: parentLabel,
            categoryId: category.id,
            taxonomyReleaseId: child.releaseId,
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
            label: _tagLabel(child.label, child.displayLabel ?? ''),
            parentTagRef: category.tagRef,
            parentLabel: parentLabel,
            categoryId: category.id,
            taxonomyReleaseId: child.releaseId,
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
    String taxonomyReleaseId,
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
        taxonomyReleaseId: taxonomyReleaseId,
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
          title: const Text(ProfileText.careerInterestUnsavedTitle),
          content: const Text(ProfileText.careerInterestUnsavedMessage),
          actions: <Widget>[
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop('save'),
              child: const Text(ProfileText.editProfileSaveAction),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop('keep'),
              child: const Text(ProfileText.careerInterestKeepEditing),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop('discard'),
              child: const Text(ProfileText.careerInterestDiscard),
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
      AppToast.show(context, ProfileText.careerInterestSaved);
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
          .validateRefs(
            expectedTaxonomyReleaseId: _taxonomyReleaseId,
            tagRefs: refs,
          );
      if (validation.invalid.isNotEmpty) {
        // 结构化校验失败：走 TAG.USER.invalid_tag_ref 语义（对齐对象级 errors.yaml），
        // 不抛裸 StateError（军规 R18）。
        throw CloudErrorMapper.invalidResponse(
          message: ProfileText.careerInterestInvalidTagToast,
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
              expectedTaxonomyReleaseId: _taxonomyReleaseId,
            ),
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, ProfileText.careerInterestSaved);
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
    _reportTagFeedback(tagRef: tagRef, action: TagFeedbackAction.ignore);
  }

  void _addInterest(String tagRef) {
    if (_interestTagRefs.contains(tagRef)) {
      return;
    }
    if (_interestTagRefs.length >=
        UserProfileUIConfig.careerInterestCatalog.maxInterestCount) {
      AppToast.show(context, ProfileText.careerInterestMaxToast);
      return;
    }
    setState(() {
      _interestTagRefs = <String>[..._interestTagRefs, tagRef];
    });
    _reportTagFeedback(tagRef: tagRef, action: TagFeedbackAction.click);
  }

  /// 标签添加/移除动作产出 TagFeedbackFact 事实（fire-and-forget，不阻断编辑）。
  void _reportTagFeedback({
    required String tagRef,
    required TagFeedbackAction action,
  }) {
    unawaited(
      ref
          .read(tagFeedbackCommandWriterProvider)
          .reportTagFeedback(
            ReportTagFeedbackCommand(tagRef: tagRef, action: action),
          )
          .then<void>((_) {})
          .catchError((Object error) {
            if (kDebugMode) {
              debugPrint('tag feedback degraded: $error');
            }
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
            ProfileText.careerInterestTitle,
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
                  ? ProfileText.careerInterestSaving
                  : ProfileText.editProfileSaveAction,
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
      return AppRequestFeedback.section();
    }
    if (_loadError != null) {
      return AppPageErrorState(
        semantic: UiErrorSemanticResolver.resolve(
          context,
          error: _loadError!,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load();
            return _loadError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
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
                  title: ProfileText.careerInterestOccupationSection,
                ),
                const SizedBox(height: AppSpacing.containerSm),
                _OccupationRow(
                  label: _occupationDisplay,
                  isPlaceholder: _occupationTagRef.trim().isEmpty,
                  onTap: _pickOccupation,
                ),
                const SizedBox(height: AppSpacing.containerXl),
                _SectionTitle(title: ProfileText.careerInterestMyTagsSection),
                const SizedBox(height: AppSpacing.containerSm),
                _buildMyTags(context),
                const SizedBox(height: AppSpacing.containerXl),
                _SectionTitle(title: ProfileText.careerInterestAllSection),
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
            ProfileText.careerInterestMyTagsEmptyHint,
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
            ProfileText.careerInterestEmptyCategory,
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
      return ProfileText.careerInterestSelectOccupation;
    }
    final option = _tagByRef[_occupationTagRef];
    if (option == null) {
      return _leafLabel(_occupationTagRef);
    }
    return '${option.parentLabel} · ${option.label}';
  }

  static String _requireSingleTaxonomyReleaseId(
    Iterable<_CareerTagOption> options,
  ) {
    final releaseIds = <String>{};
    for (final option in options) {
      final releaseId = option.taxonomyReleaseId.trim();
      if (releaseId.isEmpty) {
        throw const FormatException(
          'career interest tag is missing taxonomyReleaseId',
        );
      }
      releaseIds.add(releaseId);
    }
    if (releaseIds.length != 1) {
      throw FormatException(
        'career interest catalog must use one taxonomy release; '
        'found ${releaseIds.length}',
      );
    }
    return releaseIds.single;
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
