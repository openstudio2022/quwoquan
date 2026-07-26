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
  late final CircleDto _seedCircle;
  late CircleEditSettingsTab _activeTab;
  late String _visibility;
  late String _joinPolicy;
  String? _categoryId;
  String? _coverSourceOverride;
  String? _avatarSourceOverride;
  late bool _autoSyncChat;
  late List<CircleSectionConfigDto> _sections;
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
    final circle = widget.initialCircle ?? _buildDraftCircle();
    _seedCircle = circle;
    _nameController = TextEditingController(text: circle.name);
    _descriptionController = TextEditingController(
      text: circle.description ?? '',
    );
    _rulesController = TextEditingController(text: circle.rulesText ?? '');
    _welcomeMessageController = TextEditingController(
      text: circle.welcomeMessage ?? '',
    );
    _tagsController = TextEditingController(text: circle.tags.join(' '));
    _activeTab = widget.initialTab;
    _visibility = circle.visibility;
    _joinPolicy = circle.joinPolicy;
    _categoryId =
        circle.category ?? (_isCreateMode ? _categoryIds.first : null);
    _autoSyncChat = circle.autoSyncChat;
    // 默认板块与 metadata ui_config circle_sections 闭集一致（works/members/chat/storage）。
    _sections = circle.sectionConfig.isNotEmpty
        ? (circle.sectionConfig
              .map((section) => section.copyWith())
              .toList(growable: true)
            ..sort((a, b) => a.order.compareTo(b.order)))
        : const [
            CircleSectionConfigDto(
              sectionType: 'works',
              visible: true,
              order: 0,
            ),
            CircleSectionConfigDto(
              sectionType: 'members',
              visible: true,
              order: 1,
            ),
            CircleSectionConfigDto(
              sectionType: 'chat',
              visible: true,
              order: 2,
            ),
            CircleSectionConfigDto(
              sectionType: 'storage',
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

  CircleDto _buildDraftCircle() {
    final now = DateTime.now();
    return CircleDto(
      id: '',
      name: '',
      description: '',
      ownerId: '',
      category: _categoryIds.first,
      visibility: 'public',
      joinPolicy: 'open',
      autoSyncChat: true,
      sectionConfig: const [
        CircleSectionConfigDto(sectionType: 'works', visible: true, order: 0),
        CircleSectionConfigDto(sectionType: 'members', visible: true, order: 1),
        CircleSectionConfigDto(sectionType: 'chat', visible: true, order: 2),
        CircleSectionConfigDto(sectionType: 'storage', visible: true, order: 3),
      ],
      createdAt: now,
      updatedAt: now,
    );
  }

  String get _initialCoverSource => (_seedCircle.coverUrl ?? '').trim();

  String get _initialAvatarSource {
    final raw = (widget.initialAvatarUrl ?? _seedCircle.coverUrl ?? '').trim();
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

  String _sectionTitle(String type) {
    return circleSectionLabel(type);
  }

  String _visibilityDescription(String value) {
    return value == 'private'
        ? UITextConstants.circleVisibilityMembersDescription
        : UITextConstants.circleVisibilityPublicDescription;
  }

  String _joinPolicyDescription(String value) {
    return value == 'approval'
        ? UITextConstants.circleJoinApprovalDescription
        : UITextConstants.circleJoinOpenDescription;
  }

  String _mediaLabel(_CircleMediaSlot slot) {
    return slot == _CircleMediaSlot.cover
        ? UITextConstants.circleCoverLabel
        : UITextConstants.circleAvatarLabel;
  }

  Future<void> _showMediaActionSheet(_CircleMediaSlot slot) async {
    final currentHasValue = slot == _CircleMediaSlot.cover
        ? _hasCoverSource
        : _hasAvatarSource;
    final action = await showAppActionSheet<_CircleMediaAction>(
      context,
      title: _mediaLabel(slot),
      message: slot == _CircleMediaSlot.cover
          ? UITextConstants.circleCoverHint
          : UITextConstants.circleAvatarHint,
      sections: [
        const AppActionSheetSection<_CircleMediaAction>(
          items: [
            AppActionSheetItem<_CircleMediaAction>(
              value: _CircleMediaAction.camera,
              label: UITextConstants.cameraPhotoMode,
              icon: CupertinoIcons.camera,
            ),
            AppActionSheetItem<_CircleMediaAction>(
              value: _CircleMediaAction.photoLibrary,
              label: UITextConstants.circleSelectFromPhotos,
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
                    ? UITextConstants.circleRemoveCover
                    : UITextConstants.circleRemoveAvatar,
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
      AppToast.show(context, UITextConstants.circleNamePlaceholder);
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
            ? UITextConstants.circleCreateSuccess
            : UITextConstants.circleSaveSuccess,
      );
      if (_isCreateMode) {
        Navigator.of(context).pop(createdCircleId);
      } else {
        Navigator.of(context).pop();
      }
    } else {
      final resolved = runtimeErrorSemantic(
        context,
        error: actionError ?? UITextConstants.loadFailed,
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
          label: UITextConstants.tryAgain,
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
          ? UITextConstants.createCircle
          : UITextConstants.circleEditSettings,
      onBack: () => Navigator.of(context).maybePop(),
      trailing: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: _isSaving ? null : _save,
        child: _isSaving
            ? const CupertinoActivityIndicator()
            : Text(
                _isCreateMode
                    ? UITextConstants.create
                    : UITextConstants.circleSaveChanges,
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
                  title: UITextConstants.circleInfoSectionTitle,
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
                        label: UITextConstants.circleNameLabel,
                        controller: _nameController,
                        placeholder: UITextConstants.circleNamePlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 1,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: UITextConstants.circleDescriptionLabel,
                        controller: _descriptionController,
                        placeholder:
                            UITextConstants.circleDescriptionPlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 4,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: UITextConstants.circleRulesLabel,
                        controller: _rulesController,
                        placeholder: UITextConstants.circleRulesPlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 6,
                        maxLength: 2000,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: UITextConstants.circleWelcomeMessageLabel,
                        controller: _welcomeMessageController,
                        placeholder:
                            UITextConstants.circleWelcomeMessagePlaceholder,
                        fill: fill,
                        fg: fg,
                        fgSecondary: fgSecondary,
                        maxLines: 4,
                        maxLength: 500,
                      ),
                      SizedBox(height: AppSpacing.md),
                      _buildField(
                        label: UITextConstants.circleTagsLabel,
                        controller: _tagsController,
                        placeholder: UITextConstants.circleTagsPlaceholder,
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
                  title: UITextConstants.circlePermissionSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildSegmentTitle(
                        UITextConstants.circleVisibilityLabel,
                        fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      _buildSegmentedControl<String>(
                        groupValue: _visibility,
                        cardBg: fill,
                        children: {
                          'public': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(UITextConstants.visibilityPublic),
                          ),
                          'private': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(UITextConstants.visibilityMembers),
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
                        UITextConstants.circleJoinPolicyLabel,
                        fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      _buildSegmentedControl<String>(
                        groupValue: _joinPolicy,
                        cardBg: fill,
                        children: {
                          'open': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(UITextConstants.joinCircle),
                          ),
                          'approval': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                            ),
                            child: Text(UITextConstants.circleJoinApproval),
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
                  title: UITextConstants.circleSurfaceSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    children: [
                      _CircleEditSettingsPageStateHelpers(
                        this,
                      )._buildSwitchTile(
                        icon: CupertinoIcons.chat_bubble_2_fill,
                        title: UITextConstants.circleAutoSyncChatLabel,
                        subtitle: UITextConstants.circleAutoSyncChatHint,
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
                          UITextConstants.circleSectionDisplayLabel,
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
                                  entry.value.sectionType,
                                ),
                                title: _sectionTitle(entry.value.sectionType),
                                subtitle: UITextConstants.circleSectionVisible,
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
                      ? const CupertinoActivityIndicator(color: AppColors.white)
                      : Text(
                          _isCreateMode
                              ? UITextConstants.createCircle
                              : UITextConstants.circleSaveChanges,
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
                  ? UITextConstants.circleInfoSectionTitle
                  : UITextConstants.editCircle,
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
                  ? UITextConstants.circleEditSettings
                  : UITextConstants.manageCenter,
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
      title: UITextConstants.circleMediaSectionTitle,
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
          UITextConstants.circleCategoryLabel,
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
