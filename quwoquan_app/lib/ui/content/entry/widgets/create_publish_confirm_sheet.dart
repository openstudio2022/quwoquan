import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_circle_select_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_location_selector_page.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_publish_confirm_sheet_widgets.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';

class CreatePublishConfirmSheet extends ConsumerStatefulWidget {
  const CreatePublishConfirmSheet({
    super.key,
    required this.initialSettings,
    required this.contentIdentity,
    required this.title,
    required this.body,
    required this.imageCount,
    required this.hasVideo,
    required this.locationService,
    required this.joinedCircles,
    required this.recommendedCircles,
  });

  final PublishSettings initialSettings;
  final CreateContentIdentity contentIdentity;
  final String title;
  final String body;
  final int imageCount;
  final bool hasVideo;
  final CreateLocationService locationService;
  final List<CreateCircleOption> joinedCircles;
  final List<CreateCircleOption> recommendedCircles;

  @override
  ConsumerState<CreatePublishConfirmSheet> createState() =>
      _CreatePublishConfirmSheetState();
}

class _CreatePublishConfirmSheetState
    extends ConsumerState<CreatePublishConfirmSheet> {
  late PublishSettings _settings;
  late final TextEditingController _summaryController;
  late final TextEditingController _tagController;
  late final TextEditingController _entityController;
  bool _bodyExpanded = false;
  bool _previewReady = false;
  bool _settingsReady = false;
  bool _buttonReady = false;
  bool _summaryLoading = false;
  bool _assistantSuggestLoading = false;
  String _summaryError = '';
  String _assistantSuggestError = '';

  bool get _hasContentSummary =>
      widget.title.trim().isNotEmpty || widget.body.trim().isNotEmpty;

  bool get _canGenerateSummary =>
      !_summaryLoading &&
      (widget.title.trim().isNotEmpty || widget.body.trim().length >= 24);

  @override
  void initState() {
    super.initState();
    final initialSummary = widget.initialSettings.summary.trim().isNotEmpty
        ? widget.initialSettings.summary.trim()
        : _fallbackSummary();
    _settings = widget.initialSettings.copyWith(summary: initialSummary);
    _summaryController = TextEditingController(text: initialSummary);
    _tagController = TextEditingController();
    _entityController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _previewReady = true;
      });
      Future<void>.delayed(const Duration(milliseconds: 90), () {
        if (!mounted) return;
        setState(() {
          _settingsReady = true;
        });
      });
      Future<void>.delayed(const Duration(milliseconds: 190), () {
        if (!mounted) return;
        setState(() {
          _buttonReady = true;
        });
      });
    });
  }

  @override
  void dispose() {
    _summaryController.dispose();
    _tagController.dispose();
    _entityController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IosSelectionPageScaffold(
      pageKey: TestKeys.createPublishConfirmSheet,
      title: UITextConstants.publishSettingsTitle,
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
          SizedBox(height: AppSpacing.interGroupMd),
          PublishConfirmSheetEntrance(
            visible: _settingsReady,
            beginOffsetY: 0.032,
            beginScale: 0.99,
            child: _buildSemanticCard(context),
          ),
          if (_hasContentSummary) ...<Widget>[
            SizedBox(height: AppSpacing.interGroupMd),
            PublishConfirmSheetEntrance(
              visible: _previewReady,
              beginOffsetY: 0.028,
              beginScale: 0.992,
              child: _buildPreviewCard(context),
            ),
          ],
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

  Widget _buildSettingsCard(BuildContext context) {
    return IosSelectionSection(
      child: Column(
        children: <Widget>[
          PublishConfirmSettingRow(
            title: UITextConstants.whoCanSeeLabel,
            value: _settings.isPublic
                ? UITextConstants.visibilityPublic
                : UITextConstants.visibilityPrivate,
            onTap: _pickVisibility,
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(AppSpacing.radiusTwentyEight),
            ),
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: UITextConstants.locationLabel,
            value: _settings.locationName.trim().isEmpty
                ? UITextConstants.locationHidden
                : _settings.locationName.trim(),
            onTap: _pickLocation,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: UITextConstants.attachHomepageTitle,
            value: !_settings.isPublic
                ? '仅公开内容可关联'
                : _settings.homepage == null
                ? UITextConstants.attachHomepageNone
                : _settings.homepage!.title,
            onTap: _settings.isPublic ? _pickHomepage : null,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: UITextConstants.selectPublishCirclesLabel,
            value: !_settings.isPublic
                ? '仅公开内容可选'
                : _settings.circleNames.isEmpty
                ? '未选圈子'
                : _settings.circleNames.join('、'),
            onTap: _settings.isPublic ? _pickCircles : null,
            borderRadius: BorderRadius.zero,
          ),
          const IosSelectionInlineDivider(indent: AppSpacing.containerMd),
          PublishConfirmSettingRow(
            title: UITextConstants.circlePublishModeLabel,
            value: widget.contentIdentity == CreateContentIdentity.work
                ? UITextConstants.circlePublishModeWork
                : UITextConstants.circlePublishModeMoment,
            onTap: null,
            borderRadius: BorderRadius.vertical(
              bottom: Radius.circular(AppSpacing.radiusTwentyEight),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSemanticCard(BuildContext context) {
    return IosSelectionSection(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _buildSummaryEditor(context),
            SizedBox(height: AppSpacing.interGroupMd),
            _buildTagEditor(context),
            SizedBox(height: AppSpacing.interGroupMd),
            _buildEntityEditor(context),
            SizedBox(height: AppSpacing.interGroupMd),
            _buildAssistantSuggestions(context),
            SizedBox(height: AppSpacing.interGroupMd),
            _buildAssistantPolicy(context),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryEditor(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                '内容摘要',
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosCallout,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            CupertinoButton(
              key: TestKeys.createPublishGenerateSummaryButton,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: _canGenerateSummary ? _generateSummary : null,
              child: _summaryLoading
                  ? const CupertinoActivityIndicator()
                  : Text(
                      'AI 摘要',
                      style: TextStyle(
                        color: _canGenerateSummary
                            ? AppColors.iosAccentLight
                            : CupertinoColors.inactiveGray.resolveFrom(context),
                        fontSize: AppTypography.sm,
                        fontWeight: AppTypography.medium,
                      ),
                    ),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        CupertinoTextField(
          key: TestKeys.createPublishSummaryField,
          controller: _summaryController,
          maxLines: 3,
          minLines: 2,
          padding: EdgeInsets.all(AppSpacing.containerSm),
          placeholder: '写一句发布后展示的摘要',
          onChanged: (value) {
            setState(() {
              _summaryError = '';
              _settings = _settings.copyWith(summary: value.trim());
            });
          },
        ),
        if (_summaryError.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            _summaryError,
            style: TextStyle(
              color: CupertinoColors.systemRed.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildTagEditor(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          '标签',
          style: TextStyle(
            color: AppColors.iosLabel(context),
            fontSize: AppTypography.iosCallout,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Row(
          children: <Widget>[
            Expanded(
              child: CupertinoTextField(
                key: TestKeys.createPublishTagInput,
                controller: _tagController,
                placeholder: '搜索或输入标签',
                onSubmitted: (_) => _addTagFromInput(),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              key: TestKeys.createPublishAddTagButton,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              onPressed: _addTagFromInput,
              child: const Text('添加'),
            ),
          ],
        ),
        PublishConfirmChipWrap(
          labels: _settings.tagLabels.isEmpty
              ? _settings.tagRefs
              : _settings.tagLabels,
          onRemove: _removeTagAt,
        ),
      ],
    );
  }

  Widget _buildEntityEditor(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          '关联地点和事物',
          style: TextStyle(
            color: AppColors.iosLabel(context),
            fontSize: AppTypography.iosCallout,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Row(
          children: <Widget>[
            Expanded(
              child: CupertinoTextField(
                key: TestKeys.createPublishEntityInput,
                controller: _entityController,
                placeholder: '搜索主页并关联',
                onSubmitted: (_) => _addEntityFromInput(),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              key: TestKeys.createPublishAddEntityButton,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              onPressed: _settings.isPublic ? _addEntityFromInput : null,
              child: const Text('关联'),
            ),
          ],
        ),
        PublishConfirmChipWrap(
          labels: _settings.entityNames.isEmpty
              ? _settings.entityRefs
              : _settings.entityNames,
          onRemove: _removeEntityAt,
        ),
      ],
    );
  }

  Widget _buildAssistantSuggestions(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                UITextConstants.publishAssistantSuggestTitle,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosCallout,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            CupertinoButton(
              key: TestKeys.createPublishAssistantSuggestButton,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: _assistantSuggestLoading
                  ? null
                  : _applyAssistantSuggestions,
              child: _assistantSuggestLoading
                  ? const CupertinoActivityIndicator()
                  : Text(
                      UITextConstants.publishAssistantSuggestAction,
                      style: TextStyle(
                        color: AppColors.iosAccent(context),
                        fontSize: AppTypography.sm,
                        fontWeight: AppTypography.medium,
                      ),
                    ),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          UITextConstants.publishAssistantSuggestSubtitle,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.iosFootnote,
          ),
        ),
        if (_assistantSuggestError.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            key: TestKeys.createPublishAssistantSuggestError,
            _assistantSuggestError,
            style: TextStyle(
              color: CupertinoColors.systemRed.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildAssistantPolicy(BuildContext context) {
    return PublishConfirmSettingRow(
      title: '小趣使用',
      value: _assistantPolicyLabel(_settings.assistantUsePolicy),
      onTap: _pickAssistantPolicy,
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
    );
  }

  Widget _buildPublishBottomBar(BuildContext context) {
    return IosSelectionBottomBar(
      confirmButtonKey: TestKeys.createPublishConfirmButton,
      confirmLabel: '确认发布',
      onConfirm: () => Navigator.of(context).pop(_settings),
    );
  }

  Widget _buildPreviewCard(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final readBundle = postReadPreviewBundleFromPublishConfirmSummary(
      contentIdentity: widget.contentIdentity,
      title: widget.title,
      body: widget.body,
      hasVideo: widget.hasVideo,
      imageCount: widget.imageCount,
    );
    final headline = readBundle.presentation.title.trim().isNotEmpty
        ? readBundle.presentation.title
        : widget.title;
    final prose = readBundle.presentation.body.trim().isNotEmpty
        ? readBundle.presentation.body
        : widget.body;
    final metaLabel = widget.hasVideo
        ? '视频内容'
        : widget.imageCount > 0
        ? '${widget.imageCount} 张图片'
        : '文字内容';
    return AnimatedContainer(
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOutCubic,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
          context,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.16),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ).withValues(alpha: isDark ? 0.12 : 0.035),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: AnimatedSize(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.iosAccentLight.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusNinetyNine,
                    ),
                  ),
                  child: Text(
                    metaLabel,
                    style: TextStyle(
                      color: AppColors.iosAccentLight,
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ),
                const Spacer(),
                Text(
                  '内容概览',
                  style: TextStyle(
                    color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            if (headline.isNotEmpty) ...<Widget>[
              Text(
                headline,
                style: const TextStyle(
                  fontSize: AppTypography.xl,
                  fontWeight: AppTypography.semiBold,
                  height: AppTypography.lineHeightTight,
                ),
              ),
              if (prose.isNotEmpty) SizedBox(height: AppSpacing.intraGroupXs),
            ],
            if (prose.isNotEmpty)
              PublishConfirmExpandablePreviewText(
                text: prose,
                expanded: _bodyExpanded,
                onToggle: () {
                  setState(() {
                    _bodyExpanded = !_bodyExpanded;
                  });
                },
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _generateSummary() async {
    if (!_canGenerateSummary) return;
    setState(() {
      _summaryLoading = true;
      _summaryError = '';
    });
    try {
      final result = await ref
          .read(contentRepositoryProvider)
          .generateArticleSummary(
            title: widget.title.trim(),
            body: widget.body.trim(),
          );
      final summary = result.summary.trim();
      if (!mounted) return;
      if (summary.isEmpty) {
        setState(() {
          _summaryError = '暂时没有生成可用摘要';
        });
        return;
      }
      _summaryController.text = summary;
      setState(() {
        _settings = _settings.copyWith(summary: summary);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _summaryError = '摘要生成失败，已保留当前内容';
      });
    } finally {
      if (mounted) {
        setState(() {
          _summaryLoading = false;
        });
      }
    }
  }

  Future<void> _applyAssistantSuggestions() async {
    if (_assistantSuggestLoading) return;
    setState(() {
      _assistantSuggestLoading = true;
      _assistantSuggestError = '';
    });
    try {
      final response = await ref
          .read(assistantRepositoryProvider)
          .suggestCreationAssistance(
            request: AssistantCreationSuggestRequest(
              draftTitle: widget.title.trim().isEmpty
                  ? null
                  : widget.title.trim(),
              draftSummary: _summaryController.text.trim().isEmpty
                  ? null
                  : _summaryController.text.trim(),
              bodyDigest: widget.body.trim().isEmpty
                  ? null
                  : widget.body.trim(),
              boundCircleIds: _settings.circleIds,
              primaryHomepageId: _settings.homepage?.id,
            ),
          );
      if (!mounted) return;
      if (!response.available) {
        setState(() {
          _assistantSuggestError =
              UITextConstants.publishAssistantSuggestUnavailable;
        });
        return;
      }
      var changed = false;
      var next = _settings;
      final nextTagRefs = List<String>.from(next.tagRefs);
      final nextTagLabels = List<String>.from(next.tagLabels);
      for (final tagRef in response.suggestedTagRefs) {
        final normalized = tagRef.trim();
        if (normalized.isEmpty || nextTagRefs.contains(normalized)) continue;
        nextTagRefs.add(normalized);
        nextTagLabels.add(_tagLabelFromRef(normalized));
        changed = true;
      }
      final nextEntityRefs = List<String>.from(next.entityRefs);
      final nextEntityNames = List<String>.from(next.entityNames);
      for (final homepage in response.suggestedHomepages) {
        final refValue = _entityRefFromAssistantSuggestion(homepage);
        if (refValue.isEmpty || nextEntityRefs.contains(refValue)) continue;
        nextEntityRefs.add(refValue);
        nextEntityNames.add(
          homepage.displayName.trim().isEmpty
              ? homepage.id.trim()
              : homepage.displayName.trim(),
        );
        changed = true;
      }
      final summary = (response.suggestedSummary ?? '').trim();
      if (summary.isNotEmpty && _summaryController.text.trim().isEmpty) {
        _summaryController.text = summary;
        next = next.copyWith(summary: summary);
        changed = true;
      }
      if (changed) {
        next = next.copyWith(
          tagRefs: nextTagRefs,
          tagLabels: nextTagLabels,
          entityRefs: nextEntityRefs,
          entityNames: nextEntityNames,
          assistantUsePolicy: next.assistantUsePolicy == 'no_assistant'
              ? 'allow_summary'
              : next.assistantUsePolicy,
        );
      }
      setState(() {
        _settings = next;
        if (!changed) {
          _assistantSuggestError =
              UITextConstants.publishAssistantSuggestNoResult;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _assistantSuggestError = UITextConstants.publishAssistantSuggestFailed;
      });
    } finally {
      if (mounted) {
        setState(() {
          _assistantSuggestLoading = false;
        });
      }
    }
  }

  Future<void> _addTagFromInput() async {
    final query = _tagController.text.trim();
    if (query.isEmpty) return;
    var tagRef = _isPathTagRef(query) ? query : '';
    var label = query;
    try {
      final results = await ref
          .read(tagRepositoryProvider)
          .search(query, limit: 1);
      if (results.isNotEmpty) {
        tagRef = results.first.tagRef.trim().isNotEmpty
            ? results.first.tagRef.trim()
            : tagRef;
        label = results.first.label.trim().isNotEmpty
            ? results.first.label.trim()
            : label;
      }
    } catch (_) {
      // 搜索失败不阻断手动路径制 tagRef 输入。
    }
    if (!mounted || tagRef.isEmpty) return;
    setState(() {
      final exists = _settings.tagRefs.contains(tagRef);
      final refs = exists
          ? _settings.tagRefs
          : <String>[..._settings.tagRefs, tagRef];
      final labels = exists
          ? _settings.tagLabels
          : <String>[..._settings.tagLabels, label];
      _settings = _settings.copyWith(tagRefs: refs, tagLabels: labels);
      _tagController.clear();
    });
  }

  Future<void> _addEntityFromInput() async {
    if (!_settings.isPublic) return;
    final query = _entityController.text.trim();
    if (query.isEmpty) {
      await _pickHomepage();
      return;
    }
    try {
      final results = await ref
          .read(homepageRepositoryProvider)
          .searchHomepages(query: query, limit: 1);
      if (!mounted || results.isEmpty) return;
      final summary = results.first;
      final reference = HomepageCanonicalReference(
        id: summary.id,
        homepageType: summary.homepageType,
        canonicalEntityId: summary.canonicalEntityId,
        title: summary.title,
        subtitle: summary.subtitle,
        coverUrl: summary.coverUrl,
        status: summary.status,
      );
      _addEntityReference(reference);
      _entityController.clear();
    } catch (_) {
      if (!mounted) return;
      await _pickHomepage();
    }
  }

  void _addEntityReference(HomepageCanonicalReference reference) {
    final refValue = homepageEntityRef(reference);
    if (refValue.isEmpty) return;
    final exists = _settings.entityRefs.contains(refValue);
    final refs = exists
        ? _settings.entityRefs
        : <String>[..._settings.entityRefs, refValue];
    final names = exists
        ? _settings.entityNames
        : <String>[..._settings.entityNames, reference.title];
    setState(() {
      _settings = _settings.copyWith(entityRefs: refs, entityNames: names);
    });
  }

  void _removeTagAt(int index) {
    setState(() {
      final refs = List<String>.from(_settings.tagRefs);
      final labels = List<String>.from(_settings.tagLabels);
      if (index >= 0 && index < refs.length) refs.removeAt(index);
      if (index >= 0 && index < labels.length) labels.removeAt(index);
      _settings = _settings.copyWith(tagRefs: refs, tagLabels: labels);
    });
  }

  void _removeEntityAt(int index) {
    setState(() {
      final refs = List<String>.from(_settings.entityRefs);
      final names = List<String>.from(_settings.entityNames);
      if (index >= 0 && index < refs.length) refs.removeAt(index);
      if (index >= 0 && index < names.length) names.removeAt(index);
      _settings = _settings.copyWith(entityRefs: refs, entityNames: names);
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
              label: UITextConstants.visibilityPublic,
              icon: CupertinoIcons.globe,
              isSelected: _settings.isPublic,
            ),
            AppActionSheetItem<bool>(
              value: false,
              label: UITextConstants.visibilityPrivate,
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
          locationService: widget.locationService,
        ),
      ),
    );
    if (option == null) return;
    setState(() {
      _settings = _settings.copyWith(
        locationName: option.name,
        clearLocationPoi: option == CreateLocationOption.hidden,
        locationPoi: option == CreateLocationOption.hidden
            ? null
            : option.toLocationPoiDto(),
      );
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

  Future<void> _pickAssistantPolicy() async {
    final nextValue = await showAppActionSheetForConfirm<String>(
      context,
      title: '小趣使用',
      sections: [
        AppActionSheetSection<String>(
          items: [
            AppActionSheetItem<String>(
              value: 'inherit',
              label: '按默认设置',
              icon: CupertinoIcons.sparkles,
              isSelected: _settings.assistantUsePolicy == 'inherit',
            ),
            AppActionSheetItem<String>(
              value: 'allow_summary',
              label: '允许摘要和推荐',
              icon: CupertinoIcons.text_badge_checkmark,
              isSelected: _settings.assistantUsePolicy == 'allow_summary',
            ),
            AppActionSheetItem<String>(
              value: 'no_assistant',
              label: '不用于小趣推荐',
              icon: CupertinoIcons.hand_raised,
              isSelected: _settings.assistantUsePolicy == 'no_assistant',
            ),
          ],
        ),
      ],
      initialValue: _settings.assistantUsePolicy,
    );
    if (nextValue == null) return;
    setState(() {
      _settings = _settings.copyWith(assistantUsePolicy: nextValue);
    });
  }

  String _fallbackSummary() {
    final text = widget.body.trim();
    if (text.isEmpty) return widget.imageCount > 0 ? '图文内容' : '';
    if (text.length <= 120) return text;
    return '${text.substring(0, 120)}...';
  }

  String _assistantPolicyLabel(String value) => switch (value) {
    'allow_summary' => '允许摘要和推荐',
    'no_assistant' => '不用于小趣推荐',
    _ => '按默认设置',
  };

  bool _isPathTagRef(String value) {
    final normalized = value.trim();
    return normalized.contains('/') && normalized.split('/').length >= 2;
  }

  String _tagLabelFromRef(String tagRef) {
    final segments = tagRef.split('/').where((item) => item.isNotEmpty);
    return segments.isEmpty ? tagRef : segments.last;
  }

  String _entityRefFromAssistantSuggestion(AssistantSuggestedHomepageView h) =>
      h.canonicalEntityId?.trim() ?? '';
}
