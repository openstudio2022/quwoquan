import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 他人主页入口；壳内档案统一为子账号资料视图（`UserProfileViewData` 别名）。
///
/// 路由：/user/:username
class OtherProfilePage extends ConsumerStatefulWidget {
  const OtherProfilePage({
    super.key,
    required this.username,
    this.subAccountId,
    this.initialAvatarUrl,
    this.initialDisplayName,
    this.initialBackgroundImageUrl,
    this.onBack,
    this.referralSource = ReferralSource.authorProfile,
  });

  final String username;
  final String? subAccountId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;
  final ReferralSource referralSource;

  @override
  ConsumerState<OtherProfilePage> createState() => _OtherProfilePageState();
}

class _OtherProfilePageState extends ConsumerState<OtherProfilePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final authorId = widget.subAccountId?.isNotEmpty == true
            ? widget.subAccountId!
            : widget.username;
        ref.read(contentEngagementTrackerProvider).trackAuthorProfileView(
          authorId,
          from: widget.referralSource,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return ProfileShell(
      mode: ProfileMode.other,
      userId: widget.subAccountId?.isNotEmpty == true
          ? widget.subAccountId!
          : widget.username,
      initialAvatarUrl: widget.initialAvatarUrl,
      initialDisplayName: widget.initialDisplayName,
      initialBackgroundUrl: widget.initialBackgroundImageUrl,
      onBack: widget.onBack ?? () => context.pop(),
    );
  }
}
