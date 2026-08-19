import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_surface_actions.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/web_main_app_shell.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_actions_discovery_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/home_feed_post_open_action.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_featured_immersive_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/my_profile_page.dart';

/// WebMainAppShell 的 production composition root。
///
/// 这里只读取对象 provider/config 并提供 typed builder/action；不定义 Widget、业务状态
/// 或文案，runtime shell 因而无需反向 import 任一 service/**。
final webMainAppShellDependenciesProvider =
    Provider<WebMainAppShellDependencies>((ref) {
      final homeContextOptions = ref
          .watch(homeChannelsProvider)
          .map(
            (channel) => WebMainAppShellContextOption(
              id: channel.id,
              labelKey: channel.labelKey,
            ),
          )
          .toList(growable: false);
      return WebMainAppShellDependencies(
        homeContextOptions: homeContextOptions,
        buildContentFeed:
            ({
              required context,
              required ref,
              required isDark,
              required channelId,
              required onInitialContentPainted,
            }) => HomeMultiFormFeed(
              key: ValueKey<String>('web-content-feed-$channelId'),
              isDark: isDark,
              channelId: channelId,
              onInitialContentPainted: onInitialContentPainted,
              onUserTap:
                  (
                    userId, {
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
                  },
              onPostTap: (post, index, {feedPosts}) {
                unawaited(
                  openHomeFeedPost(
                    context,
                    ref,
                    post: post,
                    mediaIndex: index,
                    channelId: channelId,
                    feedPosts: feedPosts,
                  ),
                );
              },
            ),
        buildFeaturedChannel: ({required onExitToRecommend}) =>
            HomeFeaturedImmersivePage(onExitToHome: onExitToRecommend),
        buildChat: () => const ChatPage(),
        buildProfile: () => const MyProfilePage(),
        buildActionsDiscovery: () => const GatheringActionsDiscoveryPage(),
        openCreate: (context, intent) {
          final action = EditorStartAction.values.singleWhere(
            (candidate) => candidate.name == intent.name,
          );
          GlobalQuickActionSheet.openCreateAction(context, action.name);
        },
        openStartGathering: GlobalQuickActionSheet.openGatedStartGathering,
        openStartGroupChat: GlobalQuickActionSheet.openGatedStartGroupChat,
      );
    });
