// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/unified_emoji_picker.dart';

/// 编辑资料页（1:1 对应 EditProfilePage.tsx）
/// 路由：/profile/edit
class EditProfilePage extends ConsumerStatefulWidget {
  const EditProfilePage({super.key});

  @override
  ConsumerState<EditProfilePage> createState() => _EditProfilePageState();
}

class _EditProfilePageState extends ConsumerState<EditProfilePage> {
  final _displayNameController = TextEditingController(text: '我的账号');
  final _usernameController = TextEditingController(text: 'my_account');
  final _bioController = TextEditingController(text: '分享美好生活...');
  final _websiteController = TextEditingController();
  final _bioFocusNode = FocusNode();
  bool _isSaving = false;
  bool _showEmojiPanel = false;

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
    await Future<void>.delayed(const Duration(milliseconds: 500));
    if (mounted) {
      setState(() => _isSaving = false);
      context.pop();
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

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        foregroundColor: fg,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => context.pop(),
        ),
        title: Text(
          UITextConstants.editProfile,
          style: TextStyle(
            color: fg,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        actions: [
          TextButton(
            onPressed: _isSaving ? null : _save,
            child: _isSaving
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.primaryColor,
                    ),
                  )
                : Text(
                    UITextConstants.confirm,
                    style: TextStyle(
                      color: AppColors.primaryColor,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
          ),
        ],
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
                  child: GestureDetector(
                    onTap: () {},
                    child: CircleAvatar(
                      radius: 16,
                      backgroundColor: AppColors.primaryColor,
                      child: Icon(Icons.camera_alt, size: 18, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: AppSpacing.lg),
          Text(
            '昵称',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: 4),
          TextField(
            controller: _displayNameController,
            style: TextStyle(color: fg, fontSize: 16),
            decoration: InputDecoration(
              hintText: '显示名称',
              hintStyle: TextStyle(color: fgSecondary),
              filled: true,
              fillColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: borderColor),
              ),
              contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
          SizedBox(height: 16),
          Text(
            '用户名',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: 4),
          TextField(
            controller: _usernameController,
            style: TextStyle(color: fg, fontSize: 16),
            decoration: InputDecoration(
              hintText: '@username',
              hintStyle: TextStyle(color: fgSecondary),
              filled: true,
              fillColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: borderColor),
              ),
              contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
          SizedBox(height: 16),
          Row(
            children: [
              Text(
                '简介',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: fgSecondary,
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () {
                  setState(() {
                    _showEmojiPanel = !_showEmojiPanel;
                    if (_showEmojiPanel) _bioFocusNode.unfocus();
                  });
                },
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.xs),
                  child: Icon(
                    _showEmojiPanel ? Icons.keyboard_outlined : Icons.emoji_emotions_outlined,
                    size: 22,
                    color: fgSecondary,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 4),
          TextField(
            controller: _bioController,
            focusNode: _bioFocusNode,
            maxLines: 3,
            style: TextStyle(color: fg, fontSize: 16),
            decoration: InputDecoration(
              hintText: '写点什么介绍自己',
              hintStyle: TextStyle(color: fgSecondary),
              filled: true,
              fillColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: borderColor),
              ),
              contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
          if (_showEmojiPanel)
            UnifiedEmojiPicker(
              onEmojiSelected: (char) {
                final pos = _bioController.selection.baseOffset.clamp(0, _bioController.text.length);
                _bioController.text = _bioController.text.substring(0, pos) + char + _bioController.text.substring(pos);
                _bioController.selection = TextSelection.collapsed(offset: pos + char.length);
                setState(() {});
              },
            ),
          SizedBox(height: 16),
          Text(
            '网站',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: 4),
          TextField(
            controller: _websiteController,
            style: TextStyle(color: fg, fontSize: 16),
            decoration: InputDecoration(
              hintText: 'https://',
              hintStyle: TextStyle(color: fgSecondary),
              filled: true,
              fillColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: borderColor),
              ),
              contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
        ],
      ),
    );
  }
}
