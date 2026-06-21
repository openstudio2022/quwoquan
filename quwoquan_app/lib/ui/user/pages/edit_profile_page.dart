// ignore_for_file: unnecessary_underscores

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

/// 编辑资料页（iOS 风格完整编辑链路）。
///
/// 路由：/profile/edit
/// - 顶部返回箭头（非 X），返回时若有未保存改动弹 iOS 风格放弃确认；
/// - 底部固定「取消 / 保存」操作区，保存仅在 dirty 时可点；
/// - 头像 / 封面接通真实「选择 → 本地预览 → 保存回写」链路（alpha：本地路径直显，
///   云侧上传接入后无缝替换为对象键），不再保留「待接入」toast；
/// - 昵称默认即新建用户名，改名后保存使主页隐藏改名画笔；简介提示与我的主页一致。
class EditProfilePage extends ConsumerStatefulWidget {
  const EditProfilePage({super.key});

  @override
  ConsumerState<EditProfilePage> createState() => _EditProfilePageState();
}

class _EditProfilePageState extends ConsumerState<EditProfilePage> {
  static const int _bioMaxLength = 200;

  late final TextEditingController _displayNameController;
  late final TextEditingController _bioController;
  final FocusNode _bioFocusNode = FocusNode();

  /// dirty 比对基线（initState 捕获的进入态）。
  late final String _initialNickname;
  late final String _initialBio;
  late final String _initialAvatarSource;
  late final String _initialCoverSource;

  /// 本次新选取（相册/拍照）的本地路径；null = 未改动该项。
  String? _pickedAvatarSource;
  String? _pickedCoverSource;

  bool _isSaving = false;
  bool _showEmojiPanel = false;

  @override
  void initState() {
    super.initState();
    final userData = ref.read(userDataProvider);
    _initialNickname = (userData?.displayName ?? '').trim();
    _initialBio = _limitBio(userData?.bio ?? '');
    _initialAvatarSource = (userData?.avatar ?? userData?.avatarUrl ?? '')
        .trim();
    _initialCoverSource = (userData?.backgroundImage ?? '').trim();
    _displayNameController = TextEditingController(text: _initialNickname)
      ..addListener(_handleFieldChanged);
    _bioController = TextEditingController(text: _initialBio)
      ..addListener(_handleFieldChanged);
  }

  @override
  void dispose() {
    _displayNameController.removeListener(_handleFieldChanged);
    _bioController.removeListener(_handleFieldChanged);
    _displayNameController.dispose();
    _bioController.dispose();
    _bioFocusNode.dispose();
    super.dispose();
  }

  static String _limitBio(String value) {
    return value.length <= _bioMaxLength
        ? value
        : value.substring(0, _bioMaxLength);
  }

  void _handleFieldChanged() {
    if (mounted) {
      setState(() {});
    }
  }

  /// 当前头像 / 封面来源（优先本次选取，其次进入态），用于预览与空态判定。
  String get _effectiveAvatarSource =>
      _pickedAvatarSource ?? _initialAvatarSource;
  String get _effectiveCoverSource => _pickedCoverSource ?? _initialCoverSource;

  bool get _nicknameDirty =>
      _displayNameController.text.trim() != _initialNickname;
  bool get _bioDirty => _limitBio(_bioController.text) != _initialBio;
  bool get _isDirty =>
      _nicknameDirty ||
      _bioDirty ||
      _pickedAvatarSource != null ||
      _pickedCoverSource != null;

  Future<void> _handleBackRequest() async {
    if (!_isDirty) {
      _doClose();
      return;
    }
    final discard = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.editProfileDiscardTitle),
          content: const Text(UITextConstants.editProfileDiscardMessage),
          actions: <Widget>[
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(UITextConstants.editProfileDiscardConfirm),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(UITextConstants.editProfileKeepEditing),
            ),
          ],
        );
      },
    );
    if (discard == true) {
      _doClose();
    }
  }

  void _doClose() {
    final navigator = Navigator.maybeOf(context);
    if (navigator != null && navigator.canPop()) {
      navigator.pop();
    }
  }

  Future<void> _save() async {
    if (!_isDirty || _isSaving) {
      return;
    }
    setState(() => _isSaving = true);
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      // PATCH 语义：仅回写本次实际改动的字段，避免空串误清未改项。
      final payload = ProfileEditUpdatePayload(
        nickname: _nicknameDirty ? _displayNameController.text.trim() : null,
        bio: _bioDirty ? _limitBio(_bioController.text) : null,
        avatarUrl: _pickedAvatarSource,
        backgroundUrl: _pickedCoverSource,
      );
      await repo.updateProfile(payload);
      if (!mounted) {
        return;
      }
      // 保存成功后同步刷新三条本人态链路：
      // 1) userDataProvider：我的主页壳层 initial*；
      // 2) activePersonaContextProvider：创作 / 聊天 / 评论等活跃 persona 上下文；
      // 3) profileNotifierProvider：nicknameCustomized / 画笔 / 统计等主页聚合态。
      // 这样返回上一页时，本人昵称 / 简介 / 头像 / 封面能立即回显，且不会遗留旧 persona
      // 上下文继续被下游读到。
      final currentUserId = ref.read(currentUserIdProvider);
      await ref.read(userDataProvider.notifier).loadUser(currentUserId);
      final _ = await ref.refresh(activePersonaContextProvider.future);
      if (currentUserId.isNotEmpty) {
        await ref.read(profileNotifierProvider(currentUserId).notifier).loadProfile();
      }
      if (!mounted) {
        return;
      }
      setState(() => _isSaving = false);
      AppToast.show(context, UITextConstants.editProfileSavedToast);
      _doClose();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _isSaving = false);
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      final semantic = UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: UITextConstants.editProfileSaveFailedTitle,
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

  Future<void> _pickMedia(_EditProfileMediaTarget target) async {
    final source = await showAppActionSheet<ImagePickSource>(
      context,
      title: target == _EditProfileMediaTarget.avatar
          ? '更换${UITextConstants.profileAvatarNoun}'
          : '更换${UITextConstants.profileCoverNoun}',
      sections: const [
        AppActionSheetSection<ImagePickSource>(
          items: [
            AppActionSheetItem<ImagePickSource>(
              value: ImagePickSource.camera,
              label: '拍照',
              icon: CupertinoIcons.camera,
            ),
            AppActionSheetItem<ImagePickSource>(
              value: ImagePickSource.photoLibrary,
              label: '从照片中选择',
              icon: CupertinoIcons.photo_on_rectangle,
            ),
          ],
        ),
      ],
    );
    if (!mounted || source == null) {
      return;
    }
    final picker = ref.read(imagePickGatewayProvider);
    final path = await picker.pickImage(
      context,
      source: source,
      cameraRouteName: PageAccessInternalRoutes.profileMediaPickerCamera,
      galleryRouteName: PageAccessInternalRoutes.profileMediaPickerGallery,
    );
    if (!mounted || path == null || path.trim().isEmpty) {
      return;
    }
    setState(() {
      switch (target) {
        case _EditProfileMediaTarget.avatar:
          _pickedAvatarSource = path.trim();
        case _EditProfileMediaTarget.cover:
          _pickedCoverSource = path.trim();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosPageBackground(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          unawaited(_handleBackRequest());
        }
      },
      child: AppScaffold(
        backgroundColor: bg,
        navigationBar: AppNavigationBar(
          backgroundColor: AppColors.iosSystemBackground(
            context,
          ).withValues(alpha: 0.94),
          border: Border(
            bottom: BorderSide(
              color: AppColors.iosSeparator(context).withValues(alpha: 0.28),
              width: AppSpacing.hairline,
            ),
          ),
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () => unawaited(_handleBackRequest()),
          ),
          middle: Text(
            UITextConstants.editProfile,
            style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
          ),
        ),
        body: Column(
          children: <Widget>[
            Expanded(
              child: ListView(
                padding: EdgeInsets.fromLTRB(
                  0,
                  AppSpacing.containerSm,
                  0,
                  AppSpacing.interGroupLg,
                ),
                children: <Widget>[
                  _buildProfileMediaCard(),
                  ProfileIosGroupedSection(
                    header: UITextConstants.editProfileInfoSectionHeader,
                    children: <Widget>[
                      _EditProfileFieldCell(
                        label: UITextConstants.editProfileNicknameLabel,
                        child: _buildTextField(
                          controller: _displayNameController,
                          placeholder:
                              UITextConstants.editProfileNicknamePlaceholder,
                        ),
                      ),
                      _EditProfileFieldCell(
                        label: UITextConstants.editProfileBioLabel,
                        trailing: CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: const Size.square(
                            AppSpacing.minInteractiveSize,
                          ),
                          onPressed: () {
                            setState(() {
                              _showEmojiPanel = !_showEmojiPanel;
                              if (_showEmojiPanel) {
                                _bioFocusNode.unfocus();
                              }
                            });
                          },
                          child: Icon(
                            _showEmojiPanel
                                ? CupertinoIcons.keyboard
                                : CupertinoIcons.smiley,
                            size: AppSpacing.iconMedium,
                            color: fgSecondary,
                          ),
                        ),
                        footer: Align(
                          alignment: AlignmentDirectional.centerEnd,
                          child: Text(
                            '${_bioController.text.length}/$_bioMaxLength',
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption2,
                              color: AppColors.iosTertiaryLabel(context),
                            ),
                          ),
                        ),
                        child: _buildTextField(
                          controller: _bioController,
                          focusNode: _bioFocusNode,
                          placeholder: UITextConstants.profileEmptyBioPrompt,
                          maxLines: 4,
                          maxLength: _bioMaxLength,
                        ),
                      ),
                      if (_showEmojiPanel)
                        Padding(
                          padding: EdgeInsets.fromLTRB(
                            AppSpacing.containerSm,
                            0,
                            AppSpacing.containerSm,
                            AppSpacing.containerSm,
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusTwenty,
                            ),
                            child: UnifiedEmojiPicker(
                              showCloseButton: true,
                              onClose: () =>
                                  setState(() => _showEmojiPanel = false),
                              onEmojiSelected: _insertEmoji,
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
            _buildBottomActionBar(isDark),
          ],
        ),
      ),
    );
  }

  void _insertEmoji(String char) {
    final pos = _bioController.selection.baseOffset.clamp(
      0,
      _bioController.text.length,
    );
    final next =
        _bioController.text.substring(0, pos) +
        char +
        _bioController.text.substring(pos);
    _bioController.text = _limitBio(next);
    _bioController.selection = TextSelection.collapsed(
      offset: (pos + char.length).clamp(0, _bioController.text.length),
    );
    setState(() {});
  }

  /// 底部固定操作区：取消 / 保存。保存仅在有未保存改动时可点（iOS 习惯）。
  Widget _buildBottomActionBar(bool isDark) {
    final canSave = _isDirty && !_isSaving;
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context).withValues(alpha: 0.96),
        border: Border(
          top: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: ProfileIosActionButton(
              key: const ValueKey<String>('edit-profile-cancel'),
              label: UITextConstants.editProfileCancelAction,
              style: ProfileIosActionStyle.outlined,
              height: AppSpacing.buttonHeightLg,
              onPressed: _isSaving ? null : () => unawaited(_handleBackRequest()),
            ),
          ),
          SizedBox(width: AppSpacing.containerMd),
          Expanded(
            child: ProfileIosActionButton(
              key: const ValueKey<String>('edit-profile-save'),
              label: UITextConstants.editProfileSaveAction,
              style: ProfileIosActionStyle.filled,
              height: AppSpacing.buttonHeightLg,
              backgroundColor: canSave
                  ? null
                  : AppColors.iosAccent(context).withValues(alpha: 0.32),
              onPressed: canSave ? _save : null,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProfileMediaCard() {
    final coverSource = _effectiveCoverSource;
    final avatarSource = _effectiveAvatarSource;
    final hasCover = coverSource.isNotEmpty;
    final hasAvatar = avatarSource.isNotEmpty;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupXs,
        AppSpacing.containerMd,
        AppSpacing.interGroupMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ProfileIosSectionHeader(
            title: UITextConstants.editProfileMediaSectionHeader,
          ),
          ProfileIosSectionCard(
            padding: EdgeInsets.zero,
            addShadow: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.vertical(
                    top: Radius.circular(AppSpacing.radiusTwenty),
                  ),
                  child: SizedBox(
                    height: AppSpacing.oneHundred + AppSpacing.forty,
                    width: double.infinity,
                    child: Stack(
                      fit: StackFit.expand,
                      children: <Widget>[
                        hasCover
                            ? AppMediaImage(
                                key: const ValueKey<String>(
                                  'edit-profile-cover-preview',
                                ),
                                imageSource: coverSource,
                                fit: BoxFit.cover,
                                errorWidget: _buildCoverFallback(),
                                placeholder: _buildCoverFallback(),
                              )
                            : _buildCoverFallback(),
                        Align(
                          alignment: hasCover
                              ? AlignmentDirectional.topEnd
                              : Alignment.center,
                          child: Padding(
                            padding: EdgeInsets.all(AppSpacing.containerSm),
                            child: ProfileIosActionButton(
                              key: const ValueKey<String>(
                                'edit-profile-cover-action',
                              ),
                              label: hasCover
                                  ? UITextConstants.profileChangeCover
                                  : UITextConstants.profileUploadCover,
                              icon: CupertinoIcons.photo,
                              onPressed: () =>
                                  unawaited(_pickMedia(_EditProfileMediaTarget.cover)),
                              style: ProfileIosActionStyle.tinted,
                              expand: false,
                              height: AppSpacing.buttonHeightSm,
                              labelFontWeight: AppTypography.regular,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  child: Row(
                    children: <Widget>[
                      _buildAvatar(
                        hasAvatar: hasAvatar,
                        avatarSource: avatarSource,
                      ),
                      SizedBox(width: AppSpacing.containerMd),
                      Expanded(
                        child: ProfileIosActionButton(
                          key: const ValueKey<String>(
                            'edit-profile-avatar-action',
                          ),
                          label: hasAvatar
                              ? UITextConstants.profileChangeAvatar
                              : UITextConstants.profileUploadAvatar,
                          icon: CupertinoIcons.camera,
                          onPressed: () =>
                              unawaited(_pickMedia(_EditProfileMediaTarget.avatar)),
                          style: ProfileIosActionStyle.outlined,
                          height: AppSpacing.buttonHeightSm,
                          labelFontWeight: AppTypography.regular,
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
    );
  }

  Widget _buildAvatar({required bool hasAvatar, required String avatarSource}) {
    const double diameter = AppSpacing.xl * 2;
    final border = AppColors.iosSystemBackground(context);
    return Container(
      width: diameter + AppSpacing.three * 2,
      height: diameter + AppSpacing.three * 2,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: hasAvatar
            ? AppColors.iosSecondaryFill(context)
            : AppColors.iosTintedFill(context),
        border: Border.all(color: border, width: AppSpacing.three),
      ),
      child: ClipOval(
        child: hasAvatar
            ? AppMediaImage(
                key: const ValueKey<String>('edit-profile-avatar-preview'),
                imageSource: avatarSource,
                fit: BoxFit.cover,
                width: diameter,
                height: diameter,
                errorWidget: _buildAvatarPlaceholder(),
                placeholder: _buildAvatarPlaceholder(),
              )
            : _buildAvatarPlaceholder(),
      ),
    );
  }

  Widget _buildAvatarPlaceholder() {
    return Center(
      child: Icon(
        CupertinoIcons.camera_fill,
        size: AppSpacing.iconLarge,
        color: AppColors.iosSecondaryLabel(context).withValues(alpha: 0.82),
      ),
    );
  }

  /// 封面空态/降级渐变：与我的主页封面 fallback 同源（浅色品牌蓝渐变 / 深色档案面渐变）。
  Widget _buildCoverFallback() {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final base = AppColors.iosProfileSurface(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            isDark
                ? base.withValues(alpha: 0.86)
                : AppColors.brandBlue100.withValues(alpha: 0.96),
            isDark
                ? base.withValues(alpha: 0.72)
                : AppColors.brandBlue50.withValues(alpha: 0.92),
          ],
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String placeholder,
    FocusNode? focusNode,
    int maxLines = 1,
    int? maxLength,
  }) {
    final secondary = AppColors.iosSecondaryLabel(context);
    final label = AppColors.iosLabel(context);
    return CupertinoTextField(
      controller: controller,
      focusNode: focusNode,
      maxLines: maxLines,
      minLines: maxLines > 1 ? maxLines : 1,
      inputFormatters: maxLength == null
          ? null
          : <TextInputFormatter>[LengthLimitingTextInputFormatter(maxLength)],
      padding: EdgeInsets.zero,
      placeholder: placeholder,
      placeholderStyle: TextStyle(
        color: secondary,
        fontSize: AppTypography.iosBody,
      ),
      style: TextStyle(
        color: label,
        fontSize: AppTypography.iosBody,
        height: AppSpacing.textLineHeightBody,
      ),
      decoration: const BoxDecoration(),
    );
  }
}

enum _EditProfileMediaTarget { avatar, cover }

class _EditProfileFieldCell extends StatelessWidget {
  const _EditProfileFieldCell({
    required this.label,
    required this.child,
    this.trailing,
    this.footer,
  });

  final String label;
  final Widget child;
  final Widget? trailing;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.regular,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              const Spacer(),
              ?trailing,
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          child,
          if (footer != null) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            footer!,
          ],
        ],
      ),
    );
  }
}
