import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 我的主页入口
///
/// 路由：/profile（MainAppShell IndexedStack 第4项）
class MyProfilePage extends ConsumerWidget {
  const MyProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userData = ref.watch(userDataProvider);
    final userId = userData?.id ?? 'me';

    return ProfileShell(
      mode: ProfileMode.mine,
      userId: userId,
      initialAvatarUrl: userData?.avatar,
      initialDisplayName: userData?.displayName,
      initialBackgroundUrl: userData?.backgroundImage,
    );
  }
}
