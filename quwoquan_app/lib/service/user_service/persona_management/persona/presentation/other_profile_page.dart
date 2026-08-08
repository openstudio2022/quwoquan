import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_shell.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileParticipantSlots;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 他人主页入口；壳内档案统一为 [PersonaProfileViewData]。
///
/// 路由：/user/:userHandle
class OtherProfilePage extends StatefulWidget {
  const OtherProfilePage({
    super.key,
    required this.userHandle,
    required this.visitRecorderService,
    required this.contentEngagementTracker,
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
  final VisitRecorderService visitRecorderService;
  final ContentEngagementTracker contentEngagementTracker;
  final String? personaId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundImageUrl;
  final VoidCallback? onBack;
  final ReferralSource referralSource;
  final bool openMessageComposerOnOpen;
  final GreetingIntersectionRef? greetingIntersectionRef;

  @override
  State<OtherProfilePage> createState() => _OtherProfilePageState();
}

class _OtherProfilePageState extends State<OtherProfilePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final authorId = widget.personaId?.isNotEmpty == true
            ? widget.personaId!
            : widget.userHandle;
        unawaited(
          widget.visitRecorderService.recordVisit(
            VisitTarget.entity(kind: VisitEntityKind.author, id: authorId),
          ),
        );
        widget.contentEngagementTracker.trackAuthorProfileView(
          authorId,
          from: widget.referralSource,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return ProfileShell(
      recommendationSlots: profileRecommendationSlots,
      participantSlots: profileParticipantSlots,
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
