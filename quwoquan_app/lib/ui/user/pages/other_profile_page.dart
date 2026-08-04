import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/user/account/user_account/domain/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 他人主页入口；壳内档案统一为Persona资料视图（`UserProfileViewData` 别名）。
///
/// 路由：/user/:userHandle
class OtherProfilePage extends ConsumerStatefulWidget {
  const OtherProfilePage({
    super.key,
    required this.userHandle,
    this.personaId,
    this.initialAvatarUrl,
    this.initialDisplayName,
    this.initialBackgroundImageUrl,
    this.onBack,
    this.referralSource = ReferralSource.authorProfile,
    this.openMessageComposerOnOpen = false,
    this.greetingIntersectionRef,
  });

  final String userHandle;
  final String? personaId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;
  final ReferralSource referralSource;
  final bool openMessageComposerOnOpen;
  final GreetingIntersectionRef? greetingIntersectionRef;

  @override
  ConsumerState<OtherProfilePage> createState() => _OtherProfilePageState();
}

class _OtherProfilePageState extends ConsumerState<OtherProfilePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final authorId = widget.personaId?.isNotEmpty == true
            ? widget.personaId!
            : widget.userHandle;
        unawaited(
          ref
              .read(visitRecorderServiceProvider)
              .recordVisit(
                VisitTarget.entity(kind: VisitEntityKind.author, id: authorId),
              ),
        );
        ref
            .read(contentEngagementTrackerProvider)
            .trackAuthorProfileView(authorId, from: widget.referralSource);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return ProfileShell(
      mode: ProfileMode.other,
      userId: widget.personaId?.isNotEmpty == true
          ? widget.personaId!
          : widget.userHandle,
      initialAvatarUrl: widget.initialAvatarUrl,
      initialDisplayName: widget.initialDisplayName,
      initialBackgroundUrl: widget.initialBackgroundImageUrl,
      openMessageComposerOnOpen: widget.openMessageComposerOnOpen,
      greetingIntersectionRef: widget.greetingIntersectionRef,
      onBack: widget.onBack ?? () => context.pop(),
    );
  }
}
