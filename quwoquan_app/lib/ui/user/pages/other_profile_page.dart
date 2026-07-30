import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

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
  });

  final String userHandle;
  final String? personaId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;
  final ReferralSource referralSource;
  final bool openMessageComposerOnOpen;

  @override
  ConsumerState<OtherProfilePage> createState() => _OtherProfilePageState();
}

class _OtherProfilePageState extends ConsumerState<OtherProfilePage> {
  final Stopwatch _dwell = Stopwatch();
  ContentBehaviorTracker? _behaviorTracker;
  String _trackedAuthorId = '';

  @override
  void initState() {
    super.initState();
    _dwell.start();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final authorId = widget.personaId?.isNotEmpty == true
            ? widget.personaId!
            : widget.userHandle;
        _trackedAuthorId = authorId;
        _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
        ref
            .read(contentEngagementTrackerProvider)
            .trackAuthorProfileView(authorId, from: widget.referralSource);
      }
    });
  }

  @override
  void dispose() {
    _dwell.stop();
    final seconds = _dwell.elapsedMilliseconds / 1000.0;
    if (_trackedAuthorId.isNotEmpty && seconds >= 1) {
      _behaviorTracker?.trackDwell(
        _trackedAuthorId,
        durationSeconds: seconds,
        contentType: 'user',
        referralSource: widget.referralSource,
      );
    }
    super.dispose();
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
      onBack: widget.onBack ?? () => context.pop(),
    );
  }
}
