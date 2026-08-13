import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_location_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/geo_tag_ref_resolver.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/layout/ios_selection_page_components.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/publish_circle_select_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/publish_location_selector_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/publish_tag_chip_picker_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_publish_confirm_sheet_widgets.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_route_models.dart';

/// 发布设置页：仅保留「谁可以看 / 所在位置 / 关联主页 / 发布到圈子」四项核心设置。
///
/// 内容摘要、标签、关联地点和事物、小趣推荐、小趣使用、圈子内形式与内容概览均已移除，
/// 保持发布页整洁。这些字段在 [PublishSettings.toPayloadFields] 中均为条件可选，
/// 删除 UI 不影响发布请求；摘要由正文/文章在 create payload 阶段自动派生。
class CreatePublishConfirmSheet extends ConsumerStatefulWidget {
  const CreatePublishConfirmSheet({
    super.key,
    required this.initialSettings,
    required this.locationCoordinator,
    required this.joinedCircles,
    required this.recommendedCircles,
    this.circleLoadUnavailable = false,
    this.suggestedTextContentType,
  });

  final PublishSettings initialSettings;
  final CreateLocationCoordinator locationCoordinator;
  final List<CreateCircleOption> joinedCircles;
  final List<CreateCircleOption> recommendedCircles;
  final bool circleLoadUnavailable;

  /// 系统建议的文字形态（`micro` | `article`）；null 表示非文字创作，不显示
  /// 形态行。确认页打开时把建议固化为 [PublishSettings.textContentType]，
  /// 用户可在此修改；提交阶段以确认值为准（GWT-001）。
  final String? suggestedTextContentType;

  @override
  ConsumerState<CreatePublishConfirmSheet> createState() =>
      _CreatePublishConfirmSheetState();
}

class _CreatePublishConfirmSheetState
    extends ConsumerState<CreatePublishConfirmSheet> {
  late PublishSettings _settings;
  bool _settingsReady = false;
  bool _buttonReady = false;

  @override
  void initState() {
    super.initState();
    _settings = widget.initialSettings;
    // 形态确认单一真相：建议值只在尚未确认时固化一次；已确认（含草稿恢复）
    // 保留用户选择，不被建议覆盖。
    final suggested = widget.suggestedTextContentType?.trim() ?? '';
    if (suggested.isNotEmpty && _settings.textContentType.trim().isEmpty) {
      _settings = _settings.copyWith(textContentType: suggested);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _settingsReady = true;
      });
      Future<void>.delayed(const Duration(milliseconds: 120), () {
        if (!mounted) return;
        setState(() {
          _buttonReady = true;
        });
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return IosSelectionPageScaffold(
      pageKey: TestKeys.createPublishConfirmSheet,
      title: CreationText.publishSettingsTitle,
      onBack: () => Navigator.of(context).pop(),
      backgroundColor: AppColors.iosPageBackground(context),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.interGroupLg,
        ),
        children: <Widget>[
          PublishConfirmSheetEntrance(
            visible: _settingsReady,
            beginOffsetY: 0.035,
            beginScale: 0.988,
            child: _buildSettingsCard(context),
          ),
        ],
      ),
      bottomBar: PublishConfirmSheetEntrance(
        visible: _buttonReady,
        beginOffsetY: 0.045,
        beginScale: 0.992,
        child: _buildPublishBottomBar(context),
      ),
    );
  }

  bool get _showsPublishFormRow =>
      (widget.suggestedTextContentType?.trim() ?? '').isNotEmpty;

  String get _publishFormValueLabel =>
      _settings.textContentType.trim() == 'article'
      ? CreationText.publishFormArticle
      : CreationText.publishFormMicro;

  Widget _buildSettingsCard(BuildContext context) {
    final topRadius = BorderRadius.vertical(
      top: Radius.circular(AppSpacing.radiusTwentyEight),
    );
    return IosSelectionSection(
      child: Column(
        children: <Widget>[
          // 发布形态（GWT-001）：系统建议已固化为当前值，用户可修改；
          // 提交阶段只消费该确认值，不再静默推导。
          if (_showsPublishFormRow) ...<Widget>[
            PublishConfirmSettingRow(
              key: const ValueKey<String>('publish-confirm-form-row'),
              title: CreationText.publishFormLabel,
              value: _publishFormValueLabel,
              onTap: _pickPublishForm,
              borderRadius: topRadius,
            ),
            const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          ],
          PublishConfirmSettingRow(
            title: CreationText.whoCanSeeLabel,
            value: _settings.isPublic
                ? CreationText.visibilityPublic
                : CreationText.visibilityPrivate,
            onTap: _pickVisibility,
            borderRadius: _showsPublishFormRow ? BorderRadius.zero : topRadius,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: CreationText.locationLabel,
            value: _settings.locationName.trim().isEmpty
                ? CreationText.locationHidden
                : _settings.locationName.trim(),
            onTap: _pickLocation,
            borderRadius: BorderRadius.zero,
          ),
          // 出行时间只在内容已绑定地点事实时出现：脱离地点的时间不构成
          // 「同地同期」交集，单独填写只会造出无处可用的字段。
          if (_settings.hasPlaceAnchor) ...<Widget>[
            const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
            PublishConfirmSettingRow(
              key: const ValueKey<String>('publish-confirm-visited-at-row'),
              title: CreationText.visitedAtLabel,
              value: _settings.visitedAt == null
                  ? CreationText.visitedAtUndeclared
                  : _formatVisitedDate(_settings.visitedAt!),
              onTap: _pickVisitedAt,
              borderRadius: BorderRadius.zero,
            ),
          ],
          if (_settings.captureMetadata.isNotEmpty) ...<Widget>[
            const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
            PublishConfirmSettingRow(
              key: const ValueKey<String>(
                'publish-confirm-capture-disclosure-row',
              ),
              title: CreationText.captureDisclosureLabel,
              value: _captureDisclosureSummary(_settings),
              onTap: _pickCaptureDisclosure,
              borderRadius: BorderRadius.zero,
            ),
          ],
          // creator_chip 采集通道：创作者主动声明内容语义标签（同行人/预算/
          // 体能/后期风格/摄影主题），写入 tagRefs 供推荐召回与交集消费。
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            key: const ValueKey<String>('publish-confirm-content-tags-row'),
            title: CreationText.contentTagsLabel,
            value: _settings.tagRefs.isEmpty
                ? CreationText.contentTagsNone
                : _settings.tagRefs
                      .map((ref) => ref.split('/').last)
                      .join('、'),
            onTap: _pickContentTags,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: CreationText.attachHomepageTitle,
            value: !_settings.isPublic
                ? CreationText.createPublishHomepagePublicOnlyHint
                : _settings.homepage == null
                ? CreationText.attachHomepageNone
                : _settings.homepage!.title,
            onTap: _settings.isPublic ? _pickHomepage : null,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: CreationText.selectPublishCirclesLabel,
            value: !_settings.isPublic
                ? CreationText.createPublishCirclesPublicOnlyHint
                : widget.circleLoadUnavailable
                ? CreationText.createPublishCirclesUnavailable
                : _settings.circleNames.isEmpty
                ? CreationText.createPublishNoCirclesSelected
                : _settings.circleNames.join('、'),
            onTap: _settings.isPublic && !widget.circleLoadUnavailable
                ? _pickCircles
                : null,
            borderRadius: BorderRadius.vertical(
              bottom: Radius.circular(AppSpacing.radiusTwentyEight),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPublishBottomBar(BuildContext context) {
    return IosSelectionBottomBar(
      confirmButtonKey: TestKeys.createPublishConfirmButton,
      confirmLabel: CreationText.createPublishConfirmButton,
      onConfirm: () => Navigator.of(context).pop(_settings),
    );
  }

  Future<void> _pickPublishForm() async {
    final nextValue = await showAppActionSheetForConfirm<String>(
      context,
      title: CreationText.publishFormSheetTitle,
      message: CreationText.publishFormSheetHint,
      sections: [
        AppActionSheetSection<String>(
          items: [
            AppActionSheetItem<String>(
              value: 'micro',
              label: CreationText.publishFormMicro,
              icon: CupertinoIcons.text_bubble,
              isSelected: _settings.textContentType.trim() != 'article',
            ),
            AppActionSheetItem<String>(
              value: 'article',
              label: CreationText.publishFormArticle,
              icon: CupertinoIcons.doc_text,
              isSelected: _settings.textContentType.trim() == 'article',
            ),
          ],
        ),
      ],
      initialValue: _settings.textContentType.trim() == 'article'
          ? 'article'
          : 'micro',
    );
    if (nextValue == null) return;
    setState(() {
      _settings = _settings.copyWith(textContentType: nextValue);
    });
  }

  Future<void> _pickVisibility() async {
    final nextValue = await showAppActionSheetForConfirm<bool>(
      context,
      title: context.l10n.whoCanSeeLabel,
      sections: [
        AppActionSheetSection<bool>(
          items: [
            AppActionSheetItem<bool>(
              value: true,
              label: CreationText.visibilityPublic,
              icon: CupertinoIcons.globe,
              isSelected: _settings.isPublic,
            ),
            AppActionSheetItem<bool>(
              value: false,
              label: CreationText.visibilityPrivate,
              icon: CupertinoIcons.lock,
              isSelected: !_settings.isPublic,
            ),
          ],
        ),
      ],
      initialValue: _settings.isPublic,
    );
    if (nextValue == null) return;
    setState(() {
      _settings = _settings.copyWith(
        isPublic: nextValue,
        circleIds: nextValue ? _settings.circleIds : const <String>[],
        circleNames: nextValue ? _settings.circleNames : const <String>[],
        entityRefs: nextValue ? _settings.entityRefs : const <String>[],
        entityNames: nextValue ? _settings.entityNames : const <String>[],
        clearHomepage: !nextValue,
      );
    });
  }

  Future<void> _pickLocation() async {
    final option = await Navigator.of(context).push<CreateLocationOption>(
      CupertinoPageRoute<CreateLocationOption>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageLocationPicker,
        ),
        builder: (_) => PublishLocationSelectorPage(
          locationCoordinator: widget.locationCoordinator,
        ),
      ),
    );
    if (option == null) return;
    setState(() {
      _settings = _settings.copyWith(
        locationName: option.name,
        clearLocationPoi: option == CreateLocationOption.hidden,
        locationPoi: option == CreateLocationOption.hidden ? null : option,
      );
    });
    if (option != CreateLocationOption.hidden) {
      // poi 采集通道：把选中 POI 解析成行政区标签写入 geoTagRef。解析是
      // 尽力而为的异步补全（候选不存在或网络失败时保持为空，绝不阻断发布）。
      unawaited(_resolveGeoTagRef(option));
    }
  }

  Future<void> _pickContentTags() async {
    final result = await Navigator.of(context).push<List<String>>(
      CupertinoPageRoute<List<String>>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageTagChipPicker,
        ),
        builder: (_) => PublishTagChipPickerPage(
          initialTagRefs: _settings.tagRefs,
        ),
      ),
    );
    if (result == null || !mounted) return;
    setState(() {
      _settings = _settings.copyWith(tagRefs: result);
    });
  }

  Future<void> _resolveGeoTagRef(CreateLocationOption option) async {
    final resolver = GeoTagRefResolver(ref.read(tagCatalogQueryProvider));
    final resolved = await resolver.resolveFromPoi(
      address: option.address,
      name: option.name,
    );
    if (!mounted) return;
    // 解析期间用户可能已换 POI 或隐藏位置：只有当前选择仍是该 POI 时才回填。
    final current = _settings.locationPoi;
    if (current == null || current.id != option.id || current.name != option.name) {
      return;
    }
    setState(() {
      _settings = _settings.copyWith(geoTagRef: resolved ?? '');
    });
  }

  /// 声明实际到访日期。
  ///
  /// 只允许选到今天：未来日期是出行计划，不是到访事实，不能进入 `visitedAt`。
  Future<void> _pickVisitedAt() async {
    final today = _startOfDay(DateTime.now());
    final selected = _settings.visitedAt;
    final capturedAt = _settings.captureMetadata.capturedAt;
    final suggested = capturedAt == null
        ? today
        : _startOfDay(capturedAt.toLocal());
    final initialDate = selected == null
        ? (suggested.isAfter(today) ? today : suggested)
        : _startOfDay(selected);
    final selection = await showCupertinoModalPopup<_VisitedAtSelection>(
      context: context,
      builder: (sheetContext) => _VisitedAtPickerSheet(
        initialDate: initialDate,
        latestDate: today,
        canClear: selected != null,
      ),
    );
    if (selection == null || !mounted) return;
    setState(() {
      _settings = selection.date == null
          ? _settings.copyWith(clearVisitedAt: true)
          : _settings.copyWith(visitedAt: selection.date);
    });
  }

  Future<void> _pickCaptureDisclosure() async {
    final selected =
        await showCupertinoModalPopup<Set<CaptureMetadataDisclosureGroup>>(
          context: context,
          builder: (sheetContext) => _CaptureDisclosureSheet(
            available: _settings.captureMetadata.availableGroups,
            selected: _settings.captureDisclosure,
          ),
        );
    if (selected == null || !mounted) return;
    setState(() {
      _settings = _settings.copyWith(captureDisclosure: selected);
    });
  }

  Future<void> _pickCircles() async {
    final selected = await Navigator.of(context).push<Map<String, String>>(
      CupertinoPageRoute<Map<String, String>>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPagePublishCircleSelect,
        ),
        builder: (_) => PublishCircleSelectPage(
          joinedCircles: widget.joinedCircles,
          recommendedCircles: widget.recommendedCircles,
          initialSelected: <String, String>{
            for (var i = 0; i < _settings.circleIds.length; i++)
              _settings.circleIds[i]: i < _settings.circleNames.length
                  ? _settings.circleNames[i]
                  : _settings.circleIds[i],
          },
        ),
      ),
    );
    if (selected == null) return;
    setState(() {
      _settings = _settings.copyWith(
        circleIds: selected.keys.toList(growable: false),
        circleNames: selected.values.toList(growable: false),
      );
    });
  }

  Future<void> _pickHomepage() async {
    if (!mounted) return;
    final result = await context.push<HomepagePickerSelectionResult>(
      AppRoutePaths.homepagePicker(query: _settings.homepage?.title),
      extra: HomepagePickerPageRouteExtra(initialSelection: _settings.homepage),
    );
    if (!mounted || result == null) return;
    setState(() {
      var next = result.clearSelection
          ? _settings.copyWith(clearHomepage: true)
          : _settings.copyWith(homepage: result.selection);
      final selection = result.selection;
      if (selection != null) {
        final refValue = homepageEntityRef(selection);
        if (refValue.isNotEmpty && !next.entityRefs.contains(refValue)) {
          next = next.copyWith(
            entityRefs: <String>[...next.entityRefs, refValue],
            entityNames: <String>[...next.entityNames, selection.title],
          );
        }
      }
      _settings = next;
    });
  }
}

DateTime _startOfDay(DateTime value) =>
    DateTime(value.year, value.month, value.day);

String _formatVisitedDate(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

String _captureDisclosureSummary(PublishSettings settings) {
  final selected = settings.captureDisclosure.intersection(
    settings.captureMetadata.availableGroups,
  );
  if (selected.isEmpty) return CreationText.captureDisclosureNone;
  return '${selected.length}/${settings.captureMetadata.availableGroups.length} 项已开启';
}

/// 到访时间选择结果。[date] 为 null 表示创作者选择不填写。
class _VisitedAtSelection {
  const _VisitedAtSelection(this.date);

  final DateTime? date;
}

class _VisitedAtPickerSheet extends StatefulWidget {
  const _VisitedAtPickerSheet({
    required this.initialDate,
    required this.latestDate,
    required this.canClear,
  });

  final DateTime initialDate;
  final DateTime latestDate;
  final bool canClear;

  @override
  State<_VisitedAtPickerSheet> createState() => _VisitedAtPickerSheetState();
}

class _VisitedAtPickerSheetState extends State<_VisitedAtPickerSheet> {
  late DateTime _picked = widget.initialDate;

  @override
  Widget build(BuildContext context) {
    return CupertinoActionSheet(
      key: const ValueKey<String>('publish-confirm-visited-at-sheet'),
      title: const Text(CreationText.visitedAtSheetTitle),
      message: Column(
        children: <Widget>[
          const Text(CreationText.visitedAtSheetHint),
          SizedBox(height: AppSpacing.intraGroupSm),
          SizedBox(
            height: AppSpacing.twoHundredTwenty,
            child: CupertinoDatePicker(
              key: const ValueKey<String>('publish-confirm-visited-at-picker'),
              mode: CupertinoDatePickerMode.date,
              initialDateTime: widget.initialDate,
              minimumDate: DateTime(1970),
              maximumDate: widget.latestDate,
              onDateTimeChanged: (value) =>
                  setState(() => _picked = _startOfDay(value)),
            ),
          ),
        ],
      ),
      actions: <Widget>[
        CupertinoActionSheetAction(
          key: const ValueKey<String>('publish-confirm-visited-at-confirm'),
          onPressed: () =>
              Navigator.of(context).pop(_VisitedAtSelection(_picked)),
          child: const Text(CreationText.visitedAtConfirm),
        ),
        if (widget.canClear)
          CupertinoActionSheetAction(
            key: const ValueKey<String>('publish-confirm-visited-at-clear'),
            isDestructiveAction: true,
            onPressed: () =>
                Navigator.of(context).pop(const _VisitedAtSelection(null)),
            child: const Text(CreationText.visitedAtClear),
          ),
      ],
      cancelButton: CupertinoActionSheetAction(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text(FoundationText.cancel),
      ),
    );
  }
}

class _CaptureDisclosureSheet extends StatefulWidget {
  const _CaptureDisclosureSheet({
    required this.available,
    required this.selected,
  });

  final Set<CaptureMetadataDisclosureGroup> available;
  final Set<CaptureMetadataDisclosureGroup> selected;

  @override
  State<_CaptureDisclosureSheet> createState() =>
      _CaptureDisclosureSheetState();
}

class _CaptureDisclosureSheetState extends State<_CaptureDisclosureSheet> {
  late final Set<CaptureMetadataDisclosureGroup> _selected = widget.selected
      .intersection(widget.available);

  @override
  Widget build(BuildContext context) {
    return CupertinoActionSheet(
      key: const ValueKey<String>('publish-confirm-capture-disclosure-sheet'),
      title: const Text(CreationText.captureDisclosureSheetTitle),
      message: const Text(CreationText.captureDisclosureSheetHint),
      actions: <Widget>[
        for (final group in CaptureMetadataDisclosureGroup.values)
          if (widget.available.contains(group))
            CupertinoActionSheetAction(
              key: ValueKey<String>('capture-disclosure-${group.wire}'),
              onPressed: () {
                setState(() {
                  if (!_selected.remove(group)) _selected.add(group);
                });
              },
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Text(_captureDisclosureGroupLabel(group)),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Icon(
                    _selected.contains(group)
                        ? CupertinoIcons.check_mark_circled_solid
                        : CupertinoIcons.circle,
                    size: AppSpacing.iconSmall,
                  ),
                ],
              ),
            ),
      ],
      cancelButton: CupertinoActionSheetAction(
        onPressed: () => Navigator.of(context).pop(_selected),
        child: const Text(CreationText.visitedAtConfirm),
      ),
    );
  }
}

String _captureDisclosureGroupLabel(CaptureMetadataDisclosureGroup group) =>
    switch (group) {
      CaptureMetadataDisclosureGroup.gear => CreationText.captureDisclosureGear,
      CaptureMetadataDisclosureGroup.parameters =>
        CreationText.captureDisclosureParameters,
      CaptureMetadataDisclosureGroup.place =>
        CreationText.captureDisclosurePlace,
      CaptureMetadataDisclosureGroup.time => CreationText.captureDisclosureTime,
    };
