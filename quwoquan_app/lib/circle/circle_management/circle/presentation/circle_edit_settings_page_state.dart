part of 'circle_edit_settings_page.dart';

class _CircleEditSettingsPageState
    extends ConsumerState<CircleEditSettingsPage> {
  static const List<String> _categoryIds = <String>[
    'meet',
    'campus',
    'car',
    'humanity',
    'life',
    'sports',
    'tech',
    'travel',
    'food',
  ];

  late final TextEditingController _nameController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _rulesController;
  late final TextEditingController _welcomeMessageController;
  late final TextEditingController _tagsController;
  late final Circle? _seedCircle;
  late CircleEditSettingsTab _activeTab;
  late CircleVisibility _visibility;
  late CircleJoinPolicy _joinPolicy;
  String? _categoryId;
  String? _coverSourceOverride;
  String? _avatarSourceOverride;
  late bool _autoSyncChat;
  late List<CircleSectionEditValue> _sections;
  bool _isSaving = false;
  Map<String, CircleCategoryTabConfigDto> _categoryLabelsFromRepo = {};

  bool get _isCreateMode => widget.isCreateMode;

  // R20 管理工具页曝光/停留：无推荐反馈语义，走 product_action journey 通道。
  // dispose 阶段禁止再解析 ref，进入时缓存 tracker。
  late final DateTime _pageEnteredAt;
  JourneyEventTracker? _journeyTracker;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    final circle = widget.initialCircle;
    _seedCircle = circle;
    _nameController = TextEditingController(text: circle?.name ?? '');
    _descriptionController = TextEditingController(
      text: circle?.description ?? '',
    );
    _rulesController = TextEditingController(text: circle?.rulesText ?? '');
    _welcomeMessageController = TextEditingController(
      text: circle?.welcomeMessage ?? '',
    );
    _tagsController = TextEditingController(
      text: (circle?.tags ?? const <String>[]).join(' '),
    );
    _activeTab = widget.initialTab;
    _visibility = circle?.visibility ?? CircleVisibility.public;
    _joinPolicy = circle?.joinPolicy ?? CircleJoinPolicy.open;
    _categoryId =
        circle?.category ?? (_isCreateMode ? _categoryIds.first : null);
    _autoSyncChat = circle?.autoSyncChat ?? true;
    // 默认板块与 metadata ui_config circle_sections 闭集一致（works/members/chat/storage）。
    final sectionConfig =
        circle?.sectionConfig ?? const <CircleSectionConfig>[];
    _sections = sectionConfig.isNotEmpty
        ? (sectionConfig
              .map(CircleSectionEditValue.fromWire)
              .toList(growable: true)
            ..sort((a, b) => a.order.compareTo(b.order)))
        : const [
            CircleSectionEditValue(
              sectionType: CircleSectionType.works,
              visible: true,
              order: 0,
            ),
            CircleSectionEditValue(
              sectionType: CircleSectionType.members,
              visible: true,
              order: 1,
            ),
            CircleSectionEditValue(
              sectionType: CircleSectionType.chat,
              visible: true,
              order: 2,
            ),
            CircleSectionEditValue(
              sectionType: CircleSectionType.storage,
              visible: true,
              order: 3,
            ),
          ].toList(growable: true);
    // 分类标签的唯一真相源是 metadata 投影的 generated 常量。
    _categoryLabelsFromRepo = Map<String, CircleCategoryTabConfigDto>.from(
      CircleCategoryTabDefaults.remoteStyleFallback,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _journeyTracker = ref.read(journeyEventTrackerProvider);
      unawaited(
        _journeyTracker!.trackAction(
          journey: 'circle_manage',
          action: 'page_enter',
          pageName: 'circle_edit_settings',
          targetType: 'circle',
          targetKey: widget.circleId ?? '',
          payload: {'mode': _isCreateMode ? 'create' : 'edit'},
        ),
      );
    });
  }

  @override
  void dispose() {
    final tracker = _journeyTracker;
    if (tracker != null) {
      unawaited(
        tracker.trackAction(
          journey: 'circle_manage',
          action: 'page_exit',
          pageName: 'circle_edit_settings',
          targetType: 'circle',
          targetKey: widget.circleId ?? '',
          payload: {
            'mode': _isCreateMode ? 'create' : 'edit',
            'durationMs': DateTime.now()
                .difference(_pageEnteredAt)
                .inMilliseconds,
          },
        ),
      );
    }
    _nameController.dispose();
    _descriptionController.dispose();
    _rulesController.dispose();
    _welcomeMessageController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  String get _initialCoverSource => (_seedCircle?.coverUrl ?? '').trim();

  String get _initialAvatarSource {
    final raw = (widget.initialAvatarUrl ?? _seedCircle?.iconUrl ?? '').trim();
    return raw;
  }

  String get _resolvedCoverSource =>
      (_coverSourceOverride ?? _initialCoverSource).trim();

  String get _resolvedAvatarSource {
    final resolved = (_avatarSourceOverride ?? _initialAvatarSource).trim();
    if (resolved.isNotEmpty) {
      return resolved;
    }
    return _avatarSourceOverride == null ? _resolvedCoverSource : '';
  }

  bool get _hasCoverSource => _resolvedCoverSource.isNotEmpty;

  bool get _hasAvatarSource => _resolvedAvatarSource.isNotEmpty;

  void _setMediaSource(_CircleMediaSlot slot, String value) {
    if (slot == _CircleMediaSlot.cover) {
      _coverSourceOverride = value;
    } else {
      _avatarSourceOverride = value;
    }
  }

  CircleEditSubmitPayload _submitPayload(String name) {
    final orderedSections = _sections
        .asMap()
        .entries
        .map((e) => e.value.copyWith(order: e.key))
        .toList(growable: false);
    return CircleEditSubmitPayload(
      name: name,
      description: _descriptionController.text.trim(),
      rulesText: _rulesController.text.trim(),
      welcomeMessage: _welcomeMessageController.text.trim(),
      tags: _normalizedTags(),
      visibility: _visibility,
      joinPolicy: _joinPolicy,
      autoSyncChat: _autoSyncChat,
      coverUrl: _resolvedCoverSource,
      avatarUrl: _resolvedAvatarSource,
      categoryId: _categoryId,
      sectionConfig: orderedSections,
    );
  }

  List<String> _normalizedTags() {
    return _tagsController.text
        .split(RegExp(r'[\s,，]+'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
  }

  String _sectionTitle(CircleSectionType type) {
    return circleSectionLabel(type.wireName);
  }

  String _visibilityDescription(CircleVisibility value) => switch (value) {
    CircleVisibility.public => CommunityText.circleVisibilityPublicDescription,
    CircleVisibility.private =>
      CommunityText.circleVisibilityMembersDescription,
    CircleVisibility.inviteOnly =>
      CommunityText.circleVisibilityInviteOnlyDescription,
  };

  String _joinPolicyDescription(CircleJoinPolicy value) => switch (value) {
    CircleJoinPolicy.open => CommunityText.circleJoinOpenDescription,
    CircleJoinPolicy.approval => CommunityText.circleJoinApprovalDescription,
    CircleJoinPolicy.inviteOnly =>
      CommunityText.circleJoinInviteOnlyDescription,
  };

  String _mediaLabel(_CircleMediaSlot slot) {
    return slot == _CircleMediaSlot.cover
        ? CommunityText.circleCoverLabel
        : CommunityText.circleAvatarLabel;
  }

  Future<void> _showMediaActionSheet(_CircleMediaSlot slot) async {
    final currentHasValue = slot == _CircleMediaSlot.cover
        ? _hasCoverSource
        : _hasAvatarSource;
    final action = await showAppActionSheet<_CircleMediaAction>(
      context,
      title: _mediaLabel(slot),
      message: slot == _CircleMediaSlot.cover
          ? CommunityText.circleCoverHint
          : CommunityText.circleAvatarHint,
      sections: [
        const AppActionSheetSection<_CircleMediaAction>(
          items: [
            AppActionSheetItem<_CircleMediaAction>(
              value: _CircleMediaAction.camera,
              label: MediaText.cameraPhotoMode,
              icon: CupertinoIcons.camera,
            ),
            AppActionSheetItem<_CircleMediaAction>(
              value: _CircleMediaAction.photoLibrary,
              label: CommunityText.circleSelectFromPhotos,
              icon: CupertinoIcons.photo_on_rectangle,
            ),
          ],
        ),
        if (currentHasValue)
          AppActionSheetSection<_CircleMediaAction>(
            items: [
              AppActionSheetItem<_CircleMediaAction>(
                value: _CircleMediaAction.remove,
                label: slot == _CircleMediaSlot.cover
                    ? CommunityText.circleRemoveCover
                    : CommunityText.circleRemoveAvatar,
                icon: CupertinoIcons.delete,
                isDestructive: true,
              ),
            ],
          ),
      ],
    );
    if (!mounted || action == null) {
      return;
    }
    switch (action) {
      case _CircleMediaAction.camera:
        await _pickMedia(slot, ImagePickSource.camera);
      case _CircleMediaAction.photoLibrary:
        await _pickMedia(slot, ImagePickSource.photoLibrary);
      case _CircleMediaAction.remove:
        setState(() => _setMediaSource(slot, ''));
    }
  }

  Future<void> _pickMedia(_CircleMediaSlot slot, ImagePickSource source) async {
    final picker = ref.read(imagePickGatewayProvider);
    final path = await picker.pickImage(
      context,
      source: source,
      cameraRouteName: PageAccessInternalRoutes.circleMediaPickerCamera,
      galleryRouteName: PageAccessInternalRoutes.circleMediaPickerGallery,
    );
    if (!mounted || path == null || path.trim().isEmpty) {
      return;
    }
    setState(() => _setMediaSource(slot, path.trim()));
  }

  Future<void> _save() async {
    if (_isSaving) return;
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      AppToast.show(context, CommunityText.circleNamePlaceholder);
      return;
    }

    setState(() => _isSaving = true);
    final payload = _submitPayload(name);
    bool success = false;
    String? createdCircleId;
    Object? actionError;
    if (_isCreateMode) {
      try {
        await ref.read(activePersonaContextProvider.future);
        final result = await ref
            .read(circlesListCircleLifecycleCommandWriterProvider)
            .createCircle(payload.toCreateCommand());
        createdCircleId = result.circleId;
        success = createdCircleId.isNotEmpty;
        if (success) {
          await ref
              .read(circleDetailCircleConfigurationCommandWriterProvider)
              .updateCircleSections(payload.toSectionsCommand(createdCircleId));
          ref.read(circleDirectoryRefreshProvider.notifier).bump();
        }
      } catch (error) {
        actionError = error;
        success = false;
      }
    } else {
      final circleCtrl = ref.read(
        circleStateProvider(widget.circleId!).notifier,
      );
      success = await circleCtrl.updateCircleDetails(
        payload.toUpdateCommand(widget.circleId!),
        payload.toSectionsCommand(widget.circleId!),
      );
    }
    if (!mounted) {
      return;
    }
    setState(() => _isSaving = false);
    if (success) {
      AppToast.show(
        context,
        _isCreateMode
            ? CommunityText.circleCreateSuccess
            : CommunityText.circleSaveSuccess,
      );
      if (_isCreateMode) {
        Navigator.of(context).pop(createdCircleId);
      } else {
        Navigator.of(context).pop();
      }
    } else {
      final resolved = runtimeErrorSemantic(
        context,
        error: actionError ?? FoundationText.loadFailed,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      final semantic = UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: _isCreateMode ? '创建圈子未完成' : '保存圈子未完成',
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.retry,
          label: ContentText.tryAgain,
        ),
        secondaryAction: resolved.secondaryAction,
        dismissible: resolved.dismissible,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
        presentation: resolved.presentation,
        tone: resolved.tone,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _save();
          }
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fill = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: _isCreateMode
          ? CommunityText.createCircle
          : CommunityText.circleEditSettings,
      onBack: () => Navigator.of(context).maybePop(),
      trailing: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: _isSaving ? null : _save,
        child: _isSaving
            ? AppRequestFeedback.inline()
            : Text(
                _isCreateMode
                    ? DiscoveryText.create
                    : CommunityText.circleSaveChanges,
                style: TextStyle(
                  color: AppColors.primaryColor,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
      ),
      body: Stack(
        children: [
          ListView(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              AppSpacing.containerLg * 5,
            ),
            children: [
              _buildHeroCard(cardBg, fg, fgSecondary),
              SizedBox(height: AppSpacing.md),
              _buildTabSwitcher(cardBg, fg, fgSecondary, border),
              SizedBox(height: AppSpacing.md),
              if (_activeTab == CircleEditSettingsTab.info) ...[
                _buildMediaSelectorCard(
                  cardBg: cardBg,
                  fill: fill,
                  fg: fg,
                  fgSecondary: fgSecondary,
                  border: border,
                ),
                SizedBox(height: AppSpacing.md),
                _buildFormCard(
                  title: CommunityText.circleInfoSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    children: [
                      _buildCategorySelector(
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        border: border,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: CommunityText.circleNameLabel,
                        controller: _nameController,
                        placeholder: CommunityText.circleNamePlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 1,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: CommunityText.circleDescriptionLabel,
                        controller: _descriptionController,
                        placeholder: CommunityText.circleDescriptionPlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 4,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: CommunityText.circleRulesLabel,
                        controller: _rulesController,
                        placeholder: CommunityText.circleRulesPlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 6,
                        maxLength: 2000,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: CommunityText.circleWelcomeMessageLabel,
                        controller: _welcomeMessageController,
                        placeholder:
                            CommunityText.circleWelcomeMessagePlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 4,
                        maxLength: 500,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: CommunityText.circleTagsLabel,
                        controller: _tagsController,
                        placeholder: CommunityText.circleTagsPlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 2,
                      ),
                    ],
                  ),
                ),
              ] else ...[
                _buildFormCard(
                  title: CommunityText.circlePermissionSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildSegmentTitle(
                        CommunityText.circleVisibilityLabel,
                        fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      _buildSegmentedControl<CircleVisibility>(
                        groupValue: _visibility,
                        cardBg: fill,
                        children: {
                          CircleVisibility.public: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CreationText.visibilityPublic),
                          ),
                          CircleVisibility.private: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CommunityText.visibilityMembers),
                          ),
                          CircleVisibility.inviteOnly: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CommunityText.visibilityInviteOnly),
                          ),
                        },
                        onValueChanged: (value) {
                          if (value != null) {
                            setState(() => _visibility = value);
                          }
                        },
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        _visibilityDescription(_visibility),
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildSegmentTitle(
                        CommunityText.circleJoinPolicyLabel,
                        fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      _buildSegmentedControl<CircleJoinPolicy>(
                        groupValue: _joinPolicy,
                        cardBg: fill,
                        children: {
                          CircleJoinPolicy.open: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CommunityText.joinCircle),
                          ),
                          CircleJoinPolicy.approval: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CommunityText.circleJoinApproval),
                          ),
                          CircleJoinPolicy.inviteOnly: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(CommunityText.circleJoinInviteOnly),
                          ),
                        },
                        onValueChanged: (value) {
                          if (value != null) {
                            setState(() => _joinPolicy = value);
                          }
                        },
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        _joinPolicyDescription(_joinPolicy),
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(height: AppSpacing.md),
                _buildFormCard(
                  title: CommunityText.circleSurfaceSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    children: [
                      _CircleEditSettingsPageStateHelpers(
                        this,
                      )._buildSwitchTile(
                        icon: CupertinoIcons.chat_bubble_2_fill,
                        title: CommunityText.circleAutoSyncChatLabel,
                        subtitle: CommunityText.circleAutoSyncChatHint,
                        value: _autoSyncChat,
                        onChanged: (value) =>
                            setState(() => _autoSyncChat = value),
                        fg: fg,
                        fgSecondary: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          CommunityText.circleSectionDisplayLabel,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            fontWeight: AppTypography.semiBold,
                            color: fgSecondary,
                          ),
                        ),
                      ),
                      SizedBox(height: AppSpacing.sm),
                      ..._sections.asMap().entries.map(
                        (entry) => Padding(
                          padding: EdgeInsets.only(
                            bottom: entry.key == _sections.length - 1
                                ? 0
                                : AppSpacing.sm,
                          ),
                          child: _CircleEditSettingsPageStateHelpers(this)
                              ._buildSwitchTile(
                                icon: circleSectionIcon(
                                  entry.value.sectionType.wireName,
                                ),
                                title: _sectionTitle(entry.value.sectionType),
                                subtitle: CommunityText.circleSectionVisible,
                                value: entry.value.visible,
                                onChanged: (value) {
                                  setState(() {
                                    _sections[entry.key] = entry.value.copyWith(
                                      visible: value,
                                    );
                                  });
                                },
                                fg: fg,
                                fgSecondary: fgSecondary,
                              ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          Positioned(
            left: AppSpacing.containerMd,
            right: AppSpacing.containerMd,
            bottom: AppSpacing.containerMd,
            child: SafeArea(
              top: false,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                color: AppColors.primaryColor,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
                onPressed: _isSaving ? null : _save,
                child: Container(
                  height: AppSpacing.buttonHeight,
                  alignment: Alignment.center,
                  child: _isSaving
                      ? AppRequestFeedback.inline(
                          indicatorColor: AppColors.white,
                        )
                      : Text(
                          _isCreateMode
                              ? CommunityText.createCircle
                              : CommunityText.circleSaveChanges,
                          style: TextStyle(
                            color: AppColors.white,
                            fontSize: AppTypography.base,
                            fontWeight: AppTypography.semiBold,
                          ),
                        ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTabSwitcher(
    Color cardBg,
    Color fg,
    Color fgSecondary,
    Color border,
  ) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.xs),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: border.withValues(alpha: 0.3)),
      ),
      child: CupertinoSlidingSegmentedControl<CircleEditSettingsTab>(
        groupValue: _activeTab,
        backgroundColor: cardBg,
        thumbColor: AppColors.primaryColor.withValues(alpha: 0.12),
        children: {
          CircleEditSettingsTab.info: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            child: Text(
              _isCreateMode
                  ? CommunityText.circleInfoSectionTitle
                  : CommunityText.editCircle,
              style: TextStyle(
                color: _activeTab == CircleEditSettingsTab.info
                    ? fg
                    : fgSecondary,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
          CircleEditSettingsTab.settings: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            child: Text(
              _isCreateMode
                  ? CommunityText.circleEditSettings
                  : CommunityText.manageCenter,
              style: TextStyle(
                color: _activeTab == CircleEditSettingsTab.settings
                    ? fg
                    : fgSecondary,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        },
        onValueChanged: (value) {
          if (value != null) {
            setState(() => _activeTab = value);
          }
        },
      ),
    );
  }

  Widget _buildMediaSelectorCard({
    required Color cardBg,
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    return _buildFormCard(
      title: CommunityText.circleMediaSectionTitle,
      cardBg: cardBg,
      child: Column(
        children: [
          _buildCoverPickerTile(
            fill: fill,
            fg: fg,
            fgSecondary: fgSecondary,
            border: border,
          ),
          SizedBox(height: AppSpacing.md),
          _buildAvatarPickerTile(
            fill: fill,
            fg: fg,
            fgSecondary: fgSecondary,
            border: border,
          ),
        ],
      ),
    );
  }

  Widget _buildCategorySelector({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    final labels = _categoryLabelsFromRepo;
    final categories = _categoryIds
        .map((id) => MapEntry(id, labels[id]?.label ?? id))
        .toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          CommunityText.circleCategoryLabel,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.semiBold,
            color: fgSecondary,
          ),
        ),
        SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: categories
              .map((entry) {
                final selected = entry.key == _categoryId;
                return CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => setState(() => _categoryId = entry.key),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    curve: Curves.easeOutCubic,
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                      vertical: AppSpacing.intraGroupSm,
                    ),
                    decoration: BoxDecoration(
                      color: selected
                          ? AppColors.primaryColor.withValues(alpha: 0.12)
                          : fill,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.circularBorderRadius,
                      ),
                      border: Border.all(
                        color: selected
                            ? AppColors.primaryColor.withValues(alpha: 0.28)
                            : border.withValues(alpha: 0.22),
                      ),
                    ),
                    child: Text(
                      entry.value,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        fontWeight: selected
                            ? AppTypography.semiBold
                            : AppTypography.medium,
                        color: selected ? AppColors.primaryColor : fg,
                      ),
                    ),
                  ),
                );
              })
              .toList(growable: false),
        ),
      ],
    );
  }

  Widget _buildFormCard({
    required String title,
    required Color cardBg,
    required Widget child,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.04),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.bold,
            ),
          ),
          SizedBox(height: AppSpacing.md),
          child,
        ],
      ),
    );
  }

  Widget _buildField({
    required String label,
    required TextEditingController controller,
    required String placeholder,
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required int maxLines,
    int? maxLength,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(label, fgSecondary),
        SizedBox(height: AppSpacing.xs),
        CupertinoTextField(
          controller: controller,
          maxLines: maxLines,
          maxLength: maxLength,
          style: TextStyle(color: fg, fontSize: AppTypography.base),
          placeholder: placeholder,
          placeholderStyle: TextStyle(color: fgSecondary),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: fill),
          ),
          onChanged: (_) => setState(() {}),
        ),
      ],
    );
  }

  Widget _buildSegmentTitle(String title, Color color) {
    return Text(
      title,
      style: TextStyle(
        fontSize: AppTypography.sm,
        fontWeight: AppTypography.semiBold,
        color: color,
      ),
    );
  }
}
