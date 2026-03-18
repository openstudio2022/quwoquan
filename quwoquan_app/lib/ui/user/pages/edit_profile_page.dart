// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';

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
    _bioController = TextEditingController(
      text: userData?.bio ?? '分享美好生活...',
    );
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
        context.pop();
      }
    } catch (_) {
      if (mounted) {
        setState(() => _isSaving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    final fillColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => context.pop(),
          child: const Icon(CupertinoIcons.xmark),
        ),
        middle: Text(
          UITextConstants.editProfile,
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
                  UITextConstants.confirm,
                  style: TextStyle(
                    color: AppColors.primaryColor,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.all(
          AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd,
        ),
        children: [
          Center(
            child: Stack(
              children: [
                CircleAvatar(
                  radius: 48,
                  backgroundColor: borderColor.withValues(alpha: 0.3),
                  backgroundImage: const NetworkImage(
                    'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
                  ),
                  onBackgroundImageError: (_, __) {},
                ),
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {},
                    child: CircleAvatar(
                      radius: 16,
                      backgroundColor: AppColors.primaryColor,
                      child: const Icon(
                        CupertinoIcons.camera_fill,
                        size: AppSpacing.eighteen,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: AppSpacing.lg),
          _buildSectionLabel('昵称', fgSecondary),
          SizedBox(height: AppSpacing.xs),
          CupertinoTextField(
            controller: _displayNameController,
            style: TextStyle(color: fg, fontSize: AppTypography.base),
            placeholder: '显示名称',
            placeholderStyle: TextStyle(color: fgSecondary),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: fillColor,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(color: fillColor),
            ),
          ),
          SizedBox(height: 16),
          _buildSectionLabel('用户名', fgSecondary),
          SizedBox(height: AppSpacing.xs),
          CupertinoTextField(
            controller: _usernameController,
            style: TextStyle(color: fg, fontSize: AppTypography.base),
            placeholder: '@username',
            placeholderStyle: TextStyle(color: fgSecondary),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: fillColor,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(color: fillColor),
            ),
          ),
          SizedBox(height: 16),
          Row(
            children: [
              _buildSectionLabel('简介', fgSecondary),
              const Spacer(),
              CupertinoButton(
                padding: EdgeInsets.all(AppSpacing.xs),
                minimumSize: Size.zero,
                onPressed: () {
                  setState(() {
                    _showEmojiPanel = !_showEmojiPanel;
                    if (_showEmojiPanel) _bioFocusNode.unfocus();
                  });
                },
                child: Icon(
                  _showEmojiPanel
                      ? CupertinoIcons.keyboard
                      : CupertinoIcons.smiley,
                  size: AppTypography.xxxl,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.xs),
          CupertinoTextField(
            controller: _bioController,
            focusNode: _bioFocusNode,
            maxLines: 3,
            style: TextStyle(color: fg, fontSize: AppTypography.base),
            placeholder: '写点什么介绍自己',
            placeholderStyle: TextStyle(color: fgSecondary),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: fillColor,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(color: fillColor),
            ),
          ),
          if (_showEmojiPanel)
            UnifiedEmojiPicker(
              onEmojiSelected: (char) {
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
              },
            ),
          SizedBox(height: AppSpacing.md),
          _buildSectionLabel('网站', fgSecondary),
          SizedBox(height: AppSpacing.xs),
          CupertinoTextField(
            controller: _websiteController,
            style: TextStyle(color: fg, fontSize: AppTypography.base),
            placeholder: 'https://',
            placeholderStyle: TextStyle(color: fgSecondary),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: fillColor,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(color: fillColor),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionLabel(String text, Color color) {
    return Text(
      text,
      style: TextStyle(
        fontSize: AppTypography.sm,
        fontWeight: FontWeight.w700,
        color: color,
      ),
    );
  }
}
