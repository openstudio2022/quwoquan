import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 我的主页入口；`ProfileShell` 经 UserProfileRepository 加载 ProfileSubjectViewData。
///
/// 路由：/profile（MainAppShell IndexedStack 第4项）
/// 也可通过 /user/:username（当前用户）push 进入，此时传入 onBack 显示返回按钮。
/// 进入时自动加载当前用户档案，确保 displayName、avatar、background 正确展示。
class MyProfilePage extends ConsumerStatefulWidget {
  const MyProfilePage({super.key, this.onBack});

  final VoidCallback? onBack;

  @override
  ConsumerState<MyProfilePage> createState() => _MyProfilePageState();
}

class _MyProfilePageState extends ConsumerState<MyProfilePage> {
  bool _didTriggerLoad = false;

  @override
  Widget build(BuildContext context) {
    if (!_didTriggerLoad) {
      _didTriggerLoad = true;
      final currentUserId = ref.read(currentUserIdProvider);
      ref.read(userDataProvider.notifier).loadUser(currentUserId);
    }
    final userData = ref.watch(userDataProvider);
    final currentUserId = ref.watch(currentUserIdProvider);
    final userId = userData?.id ?? currentUserId;

    return ProfileShell(
      mode: ProfileMode.mine,
      userId: userId,
      initialAvatarUrl: userData?.avatar ?? userData?.avatarUrl,
      initialDisplayName: userData?.displayName,
      initialBackgroundUrl: userData?.backgroundImage,
      onBack: widget.onBack,
    );
  }
}
