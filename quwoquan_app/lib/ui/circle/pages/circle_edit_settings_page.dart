import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_media_picker_provider.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';

enum CircleEditSettingsTab { info, settings }

enum _CircleMediaSlot { cover, avatar }

enum _CircleMediaAction { camera, photoLibrary, remove }

class CircleEditSettingsPage extends ConsumerStatefulWidget {
  const CircleEditSettingsPage({
    super.key,
    required this.circleId,
    required this.initialCircle,
    this.initialTab = CircleEditSettingsTab.info,
    this.initialAvatarUrl,
  }) : isCreateMode = false;

  const CircleEditSettingsPage.create({
    super.key,
    this.initialTab = CircleEditSettingsTab.info,
  }) : circleId = null,
       initialCircle = null,
       initialAvatarUrl = null,
       isCreateMode = true;

  final String? circleId;
  final CircleDto? initialCircle;
  final CircleEditSettingsTab initialTab;
  final String? initialAvatarUrl;
  final bool isCreateMode;

  @override
  ConsumerState<CircleEditSettingsPage> createState() =>
      _CircleEditSettingsPageState();
}

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

  bool get _isCreateMode => widget.isCreateMode;

  @override
  void initState() {
    super.initState();
    final circle = widget.initialCircle ?? _buildDraftCircle();
    _seedCircle = circle;
    _nameController = TextEditingController(text: circle.name);
    _descriptionController = TextEditingController(
      text: circle.description ?? '',
    );
    _tagsController = TextEditingController(text: circle.tags.join(' '));
    _activeTab = widget.initialTab;
    _visibility = circle.visibility;
    _joinPolicy = circle.joinPolicy;
    _categoryId =
        circle.category ?? (_isCreateMode ? _categoryIds.first : null);
    _autoSyncChat = circle.autoSyncChat;
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
              sectionType: 'interaction',
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
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
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
        CircleSectionConfigDto(
          sectionType: 'interaction',
          visible: true,
          order: 1,
        ),
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

  Map<String, dynamic> _submitPayload(String name) {
    return <String, dynamic>{
      'name': name,
      'description': _descriptionController.text.trim(),
      'tags': _normalizedTags(),
      'visibility': _visibility,
      'joinPolicy': _joinPolicy,
      'autoSyncChat': _autoSyncChat,
      'coverUrl': _resolvedCoverSource,
      'cover': _resolvedCoverSource,
      'avatarUrl': _resolvedAvatarSource,
      'avatar': _resolvedAvatarSource,
      if (_categoryId != null && _categoryId!.isNotEmpty)
        'categoryId': _categoryId,
      if (_categoryId != null && _categoryId!.isNotEmpty)
        'category': _categoryId,
      'sectionConfig': _sections
          .asMap()
          .entries
          .map((entry) => entry.value.copyWith(order: entry.key).toMap())
          .toList(growable: false),
    };
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
    return switch (type) {
      'works' => UITextConstants.circleWorksTab,
      'interaction' => UITextConstants.circleInteractionTab,
      'chat' => UITextConstants.circleGroups,
      'storage' => UITextConstants.circleAssetsTab,
      _ => type,
    };
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
        await _pickMedia(slot, CircleMediaPickSource.camera);
      case _CircleMediaAction.photoLibrary:
        await _pickMedia(slot, CircleMediaPickSource.photoLibrary);
      case _CircleMediaAction.remove:
        setState(() => _setMediaSource(slot, ''));
    }
  }

  Future<void> _pickMedia(
    _CircleMediaSlot slot,
    CircleMediaPickSource source,
  ) async {
    final picker = ref.read(circleMediaPickerProvider);
    final path = await picker.pickImage(context, source: source);
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
    if (_isCreateMode) {
      try {
        final repo = ref.read(circleRepositoryProvider);
        final created = await repo.createCircle(payload);
        final merged = <String, dynamic>{
          ...payload,
          ...created,
          'role': created['role'] ?? 'owner',
          'joinStatus': created['joinStatus'] ?? 'joined',
          'isFollowed': created['isFollowed'] ?? true,
          'memberCount': created['memberCount'] ?? 1,
          'postCount': created['postCount'] ?? 0,
          'weeklyActiveCount': created['weeklyActiveCount'] ?? 0,
          'createdAt': created['createdAt'] ?? DateTime.now().toIso8601String(),
          'updatedAt': created['updatedAt'] ?? DateTime.now().toIso8601String(),
        };
        createdCircleId = CircleDto.fromMap(merged).id;
        success = createdCircleId.isNotEmpty;
        if (success) {
          final refreshNotifier = ref.read(
            circleDirectoryRefreshProvider.notifier,
          );
          refreshNotifier.state = refreshNotifier.state + 1;
        }
      } catch (_) {
        success = false;
      }
    } else {
      final notifier = ref.read(circleStateProvider(widget.circleId!));
      success = await notifier.updateCircleDetails(payload);
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
      AppToast.show(context, UITextConstants.loadFailed);
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
                      _buildSwitchTile(
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
                          child: _buildSwitchTile(
                            icon: switch (entry.value.sectionType) {
                              'works' => CupertinoIcons.sparkles,
                              'interaction' => CupertinoIcons.heart,
                              'chat' => CupertinoIcons.chat_bubble_2,
                              'storage' => CupertinoIcons.folder,
                              _ => CupertinoIcons.square_grid_2x2,
                            },
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
                      ? const CupertinoActivityIndicator(color: Colors.white)
                      : Text(
                          _isCreateMode
                              ? UITextConstants.createCircle
                              : UITextConstants.circleSaveChanges,
                          style: TextStyle(
                            color: Colors.white,
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

  Widget _buildHeroCard(Color cardBg, Color fg, Color fgSecondary) {
    final coverUrl = _resolvedCoverSource;
    final avatarUrl = _resolvedAvatarSource;
    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: AppSpacing.lg,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Stack(
          children: [
            SizedBox(
              height:
                  AppSpacing.oneHundred +
                  AppSpacing.avatarCircleXl +
                  AppSpacing.md,
              width: double.infinity,
              child: coverUrl.isNotEmpty
                  ? CircleMediaImage(
                      imageSource: coverUrl,
                      fit: BoxFit.cover,
                      placeholder: ColoredBox(color: cardBg),
                      errorWidget: ColoredBox(color: cardBg),
                    )
                  : ColoredBox(
                      color: AppColors.primaryColor.withValues(alpha: 0.1),
                    ),
            ),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withValues(alpha: 0.12),
                      Colors.black.withValues(alpha: 0.04),
                      Colors.black.withValues(alpha: 0.42),
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              left: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              bottom: AppSpacing.containerMd,
              child: Row(
                children: [
                  Container(
                    width: AppSpacing.avatarCircleLg,
                    height: AppSpacing.avatarCircleLg,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white.withValues(alpha: 0.22),
                      border: Border.all(
                        color: Colors.white,
                        width: AppSpacing.two,
                      ),
                    ),
                    child: avatarUrl.isNotEmpty
                        ? ClipOval(
                            child: CircleMediaImage(
                              imageSource: avatarUrl,
                              fit: BoxFit.cover,
                              errorWidget: const ColoredBox(
                                color: Colors.transparent,
                                child: Center(
                                  child: Icon(
                                    CupertinoIcons.person_3_fill,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                            ),
                          )
                        : const Icon(
                            CupertinoIcons.person_3_fill,
                            color: Colors.white,
                          ),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _nameController.text.trim().isEmpty
                              ? (_isCreateMode
                                    ? UITextConstants.createCircle
                                    : _seedCircle.name)
                              : _nameController.text.trim(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: AppTypography.xl,
                            fontWeight: AppTypography.bold,
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          _isCreateMode
                              ? (_activeTab == CircleEditSettingsTab.info
                                    ? UITextConstants.createCircle
                                    : UITextConstants.circleEditSettings)
                              : (_activeTab == CircleEditSettingsTab.info
                                    ? UITextConstants.editCircle
                                    : UITextConstants.manageCenter),
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.86),
                            fontSize: AppTypography.sm,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
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

  Widget _buildCoverPickerTile({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(UITextConstants.circleCoverLabel, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        Container(
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: border.withValues(alpha: 0.2)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius),
                ),
                child: AspectRatio(
                  aspectRatio: 16 / 9,
                  child: _hasCoverSource
                      ? CircleMediaImage(
                          imageSource: _resolvedCoverSource,
                          fit: BoxFit.cover,
                          placeholder: ColoredBox(color: fill),
                          errorWidget: ColoredBox(color: fill),
                        )
                      : DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [
                                AppColors.primaryColor.withValues(alpha: 0.18),
                                fill,
                              ],
                            ),
                          ),
                          child: Center(
                            child: Icon(
                              CupertinoIcons.photo_on_rectangle,
                              color: fgSecondary,
                              size: AppSpacing.iconLarge,
                            ),
                          ),
                        ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(AppSpacing.containerSm),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        UITextConstants.circleCoverHint,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.containerSm),
                    CupertinoButton(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.intraGroupSm,
                      ),
                      minimumSize: Size.zero,
                      color: AppColors.primaryColor.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.circularBorderRadius,
                      ),
                      onPressed: () =>
                          _showMediaActionSheet(_CircleMediaSlot.cover),
                      child: Text(
                        _hasCoverSource
                            ? UITextConstants.videoChangeCover
                            : UITextConstants.addCover,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.semiBold,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAvatarPickerTile({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(UITextConstants.circleAvatarLabel, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        Container(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: border.withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              Container(
                width: AppSpacing.avatarCircleLg,
                height: AppSpacing.avatarCircleLg,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: fgSecondary.withValues(alpha: 0.14),
                  border: Border.all(
                    color: Colors.white,
                    width: AppSpacing.two,
                  ),
                ),
                child: ClipOval(
                  child: _hasAvatarSource
                      ? CircleMediaImage(
                          imageSource: _resolvedAvatarSource,
                          fit: BoxFit.cover,
                          placeholder: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                          errorWidget: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                            child: Icon(
                              CupertinoIcons.person_3_fill,
                              color: fgSecondary,
                            ),
                          ),
                        )
                      : Icon(CupertinoIcons.person_3_fill, color: fgSecondary),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.circleAvatarTitle,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.semiBold,
                        color: fg,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      UITextConstants.circleAvatarHint,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupSm,
                ),
                minimumSize: Size.zero,
                color: AppColors.primaryColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
                onPressed: () => _showMediaActionSheet(_CircleMediaSlot.avatar),
                child: Text(
                  _hasAvatarSource
                      ? UITextConstants.circleChangeAvatar
                      : UITextConstants.circleAddAvatar,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildCategorySelector({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    final categories = _categoryIds
        .where(CircleMockData.categoryConfig.containsKey)
        .map(
          (id) => MapEntry(
            id,
            CircleMockData.categoryConfig[id]?['label']?.toString() ?? id,
          ),
        )
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
            color: Colors.black.withValues(alpha: 0.04),
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
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(label, fgSecondary),
        SizedBox(height: AppSpacing.xs),
        CupertinoTextField(
          controller: controller,
          maxLines: maxLines,
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

  Widget _buildSegmentedControl<T extends Object>({
    required T groupValue,
    required Map<T, Widget> children,
    required ValueChanged<T?> onValueChanged,
    required Color cardBg,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.xs),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: CupertinoSlidingSegmentedControl<T>(
        groupValue: groupValue,
        backgroundColor: cardBg,
        thumbColor: AppColors.primaryColor.withValues(alpha: 0.12),
        children: children,
        onValueChanged: onValueChanged,
      ),
    );
  }

  Widget _buildSwitchTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
    required Color fg,
    required Color fgSecondary,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: fgSecondary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        children: [
          Container(
            width: AppSpacing.buttonHeight,
            height: AppSpacing.buttonHeight,
            decoration: BoxDecoration(
              color: AppColors.primaryColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            ),
            child: Icon(
              icon,
              color: AppColors.primaryColor,
              size: AppSpacing.iconMedium,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: fg,
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: fgSecondary,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ),
          ),
          CupertinoSwitch(
            value: value,
            activeTrackColor: AppColors.primaryColor,
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}
