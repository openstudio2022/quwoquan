import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';

enum CircleEditSettingsTab { info, settings }

class CircleEditSettingsPage extends ConsumerStatefulWidget {
  const CircleEditSettingsPage({
    super.key,
    required this.circleId,
    required this.initialCircle,
    this.initialTab = CircleEditSettingsTab.info,
  });

  final String circleId;
  final CircleDto initialCircle;
  final CircleEditSettingsTab initialTab;

  @override
  ConsumerState<CircleEditSettingsPage> createState() =>
      _CircleEditSettingsPageState();
}

class _CircleEditSettingsPageState
    extends ConsumerState<CircleEditSettingsPage> {
  late final TextEditingController _nameController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _tagsController;
  late CircleEditSettingsTab _activeTab;
  late String _visibility;
  late String _joinPolicy;
  late bool _autoSyncChat;
  late List<CircleSectionConfigDto> _sections;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    final circle = widget.initialCircle;
    _nameController = TextEditingController(text: circle.name);
    _descriptionController = TextEditingController(
      text: circle.description ?? '',
    );
    _tagsController = TextEditingController(text: circle.tags.join(' '));
    _activeTab = widget.initialTab;
    _visibility = circle.visibility;
    _joinPolicy = circle.joinPolicy;
    _autoSyncChat = circle.autoSyncChat;
    _sections = circle.sectionConfig.isNotEmpty
        ? (circle.sectionConfig
              .map((section) => section.copyWith())
              .toList(growable: true)
          ..sort((a, b) => a.order.compareTo(b.order)))
        : const [
            CircleSectionConfigDto(sectionType: 'works', visible: true, order: 0),
            CircleSectionConfigDto(
              sectionType: 'interaction',
              visible: true,
              order: 1,
            ),
            CircleSectionConfigDto(sectionType: 'chat', visible: true, order: 2),
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

  Future<void> _save() async {
    if (_isSaving) return;
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      AppToast.show(context, UITextConstants.circleNamePlaceholder);
      return;
    }

    setState(() => _isSaving = true);
    final notifier = ref.read(circleStateProvider(widget.circleId));
    final success = await notifier.updateCircleDetails({
      'name': name,
      'description': _descriptionController.text.trim(),
      'tags': _normalizedTags(),
      'visibility': _visibility,
      'joinPolicy': _joinPolicy,
      'autoSyncChat': _autoSyncChat,
      'sectionConfig': _sections
          .asMap()
          .entries
          .map(
            (entry) => entry.value.copyWith(order: entry.key).toMap(),
          )
          .toList(growable: false),
    });
    if (!mounted) {
      return;
    }
    setState(() => _isSaving = false);
    if (success) {
      AppToast.show(context, UITextConstants.circleSaveSuccess);
      Navigator.of(context).pop();
    } else {
      AppToast.show(context, UITextConstants.loadFailed);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fill = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: cardBg.withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: border.withValues(alpha: 0.3),
            width: AppSpacing.hairline,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).maybePop(),
          child: const Icon(CupertinoIcons.back),
        ),
        middle: Text(
          UITextConstants.circleEditSettings,
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.bold,
          ),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _isSaving ? null : _save,
          child: _isSaving
              ? const CupertinoActivityIndicator()
              : Text(
                  UITextConstants.circleSaveChanges,
                  style: TextStyle(
                    color: AppColors.primaryColor,
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                  ),
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
                _buildFormCard(
                  title: UITextConstants.circleInfoSectionTitle,
                  cardBg: cardBg,
                  child: Column(
                    children: [
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
                          UITextConstants.circleSaveChanges,
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
    final coverUrl = widget.initialCircle.coverUrl;
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
              height: 188,
              width: double.infinity,
              child: coverUrl != null && coverUrl.isNotEmpty
                  ? Image.network(
                      coverUrl,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) =>
                          ColoredBox(color: cardBg),
                    )
                  : ColoredBox(color: AppColors.primaryColor.withValues(alpha: 0.1)),
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
                      border: Border.all(color: Colors.white, width: 2),
                    ),
                    child: coverUrl != null && coverUrl.isNotEmpty
                        ? ClipOval(
                            child: Image.network(
                              coverUrl,
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) =>
                                  const Icon(
                                    CupertinoIcons.person_3_fill,
                                    color: Colors.white,
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
                              ? widget.initialCircle.name
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
                          _activeTab == CircleEditSettingsTab.info
                              ? UITextConstants.editCircle
                              : UITextConstants.manageCenter,
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
              UITextConstants.editCircle,
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
              UITextConstants.manageCenter,
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
