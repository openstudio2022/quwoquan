// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

/// 编辑资料页（1:1 对应 EditProfilePage.tsx）
/// 路由：/profile/edit
class EditProfilePage extends ConsumerStatefulWidget {
  const EditProfilePage({super.key});

  @override
  ConsumerState<EditProfilePage> createState() => _EditProfilePageState();
}

class _EditProfilePageState extends ConsumerState<EditProfilePage> {
  late final TextEditingController _displayNameController;
  late final TextEditingController _usernameController;
  late final TextEditingController _bioController;
  final TextEditingController _websiteController = TextEditingController();
  final FocusNode _bioFocusNode = FocusNode();
  bool _isSaving = false;
  bool _showEmojiPanel = false;

  @override
  void initState() {
    super.initState();
    final userData = ref.read(userDataProvider);
    _displayNameController = TextEditingController(
      text: userData?.displayName ?? '我的账号',
    );
    _usernameController = TextEditingController(
      text: userData?.username ?? 'my_account',
    );
    _bioController = TextEditingController(text: userData?.bio ?? '分享美好生活...');
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _usernameController.dispose();
    _bioController.dispose();
    _websiteController.dispose();
    _bioFocusNode.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _isSaving = true);
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      await repo.updateProfile({
        'nickname': _displayNameController.text,
        'username': _usernameController.text,
        'bio': _bioController.text,
        'website': _websiteController.text,
      });
      if (mounted) {
        final currentUserId = ref.read(currentUserIdProvider);
        ref.read(userDataProvider.notifier).loadUser(currentUserId);
        setState(() => _isSaving = false);
        AppToast.show(context, '资料已更新');
        context.pop();
      }
    } catch (_) {
      if (mounted) {
        setState(() => _isSaving = false);
        AppToast.show(context, '保存失败，请稍后再试');
      }
    }
  }

  Future<void> _showMediaActionSheet(String target) async {
    final action = await showAppActionSheet<_EditProfileMediaAction>(
      context,
      title: '更换$target',
      sections: const [
        AppActionSheetSection<_EditProfileMediaAction>(
          items: [
            AppActionSheetItem<_EditProfileMediaAction>(
              value: _EditProfileMediaAction.camera,
              label: '拍照',
              icon: CupertinoIcons.camera,
            ),
            AppActionSheetItem<_EditProfileMediaAction>(
              value: _EditProfileMediaAction.photoLibrary,
              label: '从照片中选择',
              icon: CupertinoIcons.photo_on_rectangle,
            ),
          ],
        ),
      ],
    );
    if (!mounted || action == null) return;
    switch (action) {
      case _EditProfileMediaAction.camera:
        AppToast.show(context, '$target拍摄能力待接入');
      case _EditProfileMediaAction.photoLibrary:
        AppToast.show(context, '$target相册选择待接入');
    }
  }

  @override
  Widget build(BuildContext context) {
    final userData = ref.watch(userDataProvider);
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosPageBackground(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final accent = AppColors.iosAccent(context);

    return AppScaffold(
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
          icon: CupertinoIcons.xmark,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.editProfile,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _isSaving ? null : _save,
          child: _isSaving
              ? const CupertinoActivityIndicator()
              : Text(
                  '保存',
                  style: TextStyle(
                    color: accent,
                    fontSize: AppTypography.iosButton,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(
          0,
          AppSpacing.containerSm,
          0,
          MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg,
        ),
        children: <Widget>[
          _buildProfileMediaCard(userData),
          ProfileIosGroupedSection(
            header: '基本信息',
            footer: _buildSectionFootnote('用户名会展示在你的主页链接中，建议保持清晰且便于识别。'),
            children: <Widget>[
              _EditProfileFieldCell(
                label: '昵称',
                child: _buildTextField(
                  controller: _displayNameController,
                  placeholder: '显示名称',
                ),
              ),
              _EditProfileFieldCell(
                label: '用户名',
                child: _buildTextField(
                  controller: _usernameController,
                  placeholder: '@username',
                ),
              ),
            ],
          ),
          ProfileIosGroupedSection(
            header: '个人简介',
            footer: _buildSectionFootnote('简介和链接会在用户主页上展示，建议保持简洁且具有辨识度。'),
            children: <Widget>[
              _EditProfileFieldCell(
                label: '简介',
                trailing: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(AppSpacing.minInteractiveSize),
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
                child: _buildTextField(
                  controller: _bioController,
                  focusNode: _bioFocusNode,
                  placeholder: '写点什么介绍自己',
                  maxLines: 4,
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
                      onClose: () => setState(() => _showEmojiPanel = false),
                      onEmojiSelected: _insertEmoji,
                    ),
                  ),
                ),
              _EditProfileFieldCell(
                label: '网站',
                child: _buildTextField(
                  controller: _websiteController,
                  placeholder: 'https://',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _insertEmoji(String char) {
    final pos = _bioController.selection.baseOffset.clamp(
      0,
      _bioController.text.length,
    );
    _bioController.text =
        _bioController.text.substring(0, pos) +
        char +
        _bioController.text.substring(pos);
    _bioController.selection = TextSelection.collapsed(
      offset: pos + char.length,
    );
    setState(() {});
  }

  Widget _buildProfileMediaCard(User? userData) {
    final avatarUrl = userData?.avatar ?? userData?.avatarUrl;
    final coverUrl = userData?.backgroundImage;
    final secondary = AppColors.iosSecondaryLabel(context);
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
          const ProfileIosSectionHeader(title: '头像与封面'),
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
                  child: Stack(
                    children: <Widget>[
                      SizedBox(
                        height: AppSpacing.oneHundred + AppSpacing.forty,
                        width: double.infinity,
                        child: coverUrl != null && coverUrl.isNotEmpty
                            ? Image.network(
                                coverUrl,
                                fit: BoxFit.cover,
                                errorBuilder: (_, _, _) =>
                                    _buildCoverPlaceholder(),
                              )
                            : _buildCoverPlaceholder(),
                      ),
                      Positioned(
                        top: AppSpacing.containerSm,
                        right: AppSpacing.containerSm,
                        child: ProfileIosActionButton(
                          label: '更换封面',
                          icon: CupertinoIcons.photo,
                          onPressed: () => _showMediaActionSheet('封面'),
                          style: ProfileIosActionStyle.tinted,
                          expand: false,
                          height: AppSpacing.buttonHeightSm,
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  child: Row(
                    children: <Widget>[
                      CircleAvatar(
                        radius: 36,
                        backgroundImage:
                            avatarUrl != null && avatarUrl.isNotEmpty
                            ? NetworkImage(avatarUrl)
                            : null,
                        backgroundColor: AppColors.iosFill(context),
                        child: avatarUrl == null || avatarUrl.isEmpty
                            ? Icon(
                                CupertinoIcons.person_crop_circle_fill,
                                size: AppSpacing.iconLarge,
                                color: secondary,
                              )
                            : null,
                      ),
                      SizedBox(width: AppSpacing.containerSm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '主页头像',
                              style: TextStyle(
                                fontSize: AppTypography.iosSubheadline,
                                fontWeight: AppTypography.semiBold,
                                color: AppColors.iosLabel(context),
                              ),
                            ),
                            SizedBox(height: AppSpacing.intraGroupXs),
                            Text(
                              '更新后会展示在主页、评论和互动入口中。',
                              style: TextStyle(
                                fontSize: AppTypography.iosFootnote,
                                color: secondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      SizedBox(width: AppSpacing.containerSm),
                      ProfileIosActionButton(
                        label: '更换头像',
                        icon: CupertinoIcons.camera,
                        onPressed: () => _showMediaActionSheet('头像'),
                        style: ProfileIosActionStyle.outlined,
                        expand: false,
                        height: AppSpacing.buttonHeightSm,
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

  Widget _buildCoverPlaceholder() {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            AppColors.iosTintedFill(context),
            AppColors.iosGroupedSurfaceElevated(context),
          ],
        ),
      ),
      child: Center(
        child: Icon(
          CupertinoIcons.photo_on_rectangle,
          size: AppSpacing.iconLarge,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String placeholder,
    FocusNode? focusNode,
    int maxLines = 1,
  }) {
    final secondary = AppColors.iosSecondaryLabel(context);
    final label = AppColors.iosLabel(context);
    return CupertinoTextField(
      controller: controller,
      focusNode: focusNode,
      maxLines: maxLines,
      minLines: maxLines > 1 ? maxLines : 1,
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

  Widget _buildSectionFootnote(String text) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
      child: Text(
        text,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: AppColors.iosSecondaryLabel(context),
          height: AppSpacing.textLineHeightBody,
        ),
      ),
    );
  }
}

enum _EditProfileMediaAction { camera, photoLibrary }

class _EditProfileFieldCell extends StatelessWidget {
  const _EditProfileFieldCell({
    required this.label,
    required this.child,
    this.trailing,
  });

  final String label;
  final Widget child;
  final Widget? trailing;

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
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              const Spacer(),
              ?trailing,
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          child,
        ],
      ),
    );
  }
}
