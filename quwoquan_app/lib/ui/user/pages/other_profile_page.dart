import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 他人主页入口
///
/// 路由：/user/:username
class OtherProfilePage extends ConsumerWidget {
  const OtherProfilePage({
    super.key,
    required this.username,
    this.profileSubjectId,
    this.initialAvatarUrl,
    this.initialDisplayName,
    this.initialBackgroundImageUrl,
    this.onBack,
  });

  final String username;
  final String? profileSubjectId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ProfileShell(
      mode: ProfileMode.other,
      userId: profileSubjectId?.isNotEmpty == true
          ? profileSubjectId!
          : username,
      initialAvatarUrl: initialAvatarUrl,
      initialDisplayName: initialDisplayName,
      initialBackgroundUrl: initialBackgroundImageUrl,
      onBack: onBack ?? () => context.pop(),
    );
  }
}
