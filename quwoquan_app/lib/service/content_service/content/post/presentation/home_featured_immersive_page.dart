import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show visitRecorderServiceProvider;
import 'package:quwoquan_app/runtime/di/presentation/content_viewer_composition.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';

/// canonical `/video-book` 根页的 premium 沉浸正文。
///
/// 页面本身不持有业务数据；沉浸流内容、交集单句与行动 CTA 均由
/// `ContentViewerComposition.featuredWorks` 装配的 viewer 消费各自读面。
class HomeFeaturedImmersivePage extends ConsumerWidget {
  const HomeFeaturedImmersivePage({
    super.key,
    required this.onExitToHome,
    this.isActive = true,
  });

  static const Key pageKey = ValueKey<String>('video-book-root');

  final VoidCallback onExitToHome;
  final bool isActive;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return CupertinoPageScaffold(
      key: pageKey,
      backgroundColor: AppColors.black,
      child: SafeArea(
        bottom: false,
        child: Material(
          type: MaterialType.transparency,
          child: ContentViewerComposition.featuredWorks(
            isActive: isActive,
            topChromeSafeInset: 0,
            onUserTap: (userId, {avatarUrl, displayName, backgroundUrl}) =>
                _openUserProfile(
                  context,
                  userId,
                  avatarUrl: avatarUrl,
                  displayName: displayName,
                  backgroundUrl: backgroundUrl,
                ),
            onAssistantTap: () => _openAssistantHalfSheet(context, ref),
            onTapBack: onExitToHome,
            onSwitchToFollowing: onExitToHome,
            onSwitchToCircles: onExitToHome,
          ),
        ),
      ),
    );
  }

  void _openUserProfile(
    BuildContext context,
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  }) {
    context.push(
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
        avatarUrl: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  void _openAssistantHalfSheet(BuildContext context, WidgetRef ref) {
    final target = VisitTarget.page('video_book');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.discovery,
      tab: 'video_book',
      experienceLevel: switch (service.getExperience(target)) {
        ExperienceLevel.firstTime => AssistantExperienceLevel.firstTime,
        ExperienceLevel.returning => AssistantExperienceLevel.returning,
        ExperienceLevel.frequent => AssistantExperienceLevel.frequent,
      },
    );
    unawaited(ContentViewerComposition.showAssistantHalfSheet(context, ctx));
  }
}
