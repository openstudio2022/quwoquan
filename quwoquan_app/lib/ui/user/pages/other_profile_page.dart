import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/user/pages/author_profile_page.dart';

/// 他人主页入口
///
/// 路由：/user/:username
class OtherProfilePage extends ConsumerWidget {
  const OtherProfilePage({
    super.key,
    required this.username,
    this.initialAvatarUrl,
    this.initialDisplayName,
    this.initialBackgroundImageUrl,
    this.onBack,
  });

  final String username;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AuthorProfile(
      username: username,
      onBack: onBack ?? () => context.pop(),
      initialAvatarUrl: initialAvatarUrl,
      initialDisplayName: initialDisplayName,
      initialBackgroundImageUrl: initialBackgroundImageUrl,
    );
  }
}
