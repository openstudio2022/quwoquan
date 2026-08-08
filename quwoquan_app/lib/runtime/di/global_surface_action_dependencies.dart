import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_edit_settings_page.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_action_sheet.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';

/// Recommendation 可携带 typed request 覆盖默认活动创建入口；该类型只在组合根
/// 与 Recommendation navigator 之间流动，runtime shell 不感知业务 request。
typedef GatheringCreateNavigationBinding =
    Future<void> Function(
      BuildContext context, [
      GatheringCreateNavigationRequest? request,
    ]);

final startGatheringNavigationBindingProvider =
    Provider<GatheringCreateNavigationBinding?>((ref) {
      Future<void> binding(
        BuildContext context, [
        GatheringCreateNavigationRequest? request,
      ]) async {
        await context.push<void>(AppRoutePaths.gatheringCreate, extra: request);
      }

      return binding;
    });

typedef GlobalCreateActionSelected = void Function(String actionWire);

class GlobalSurfaceActionBindings {
  const GlobalSurfaceActionBindings({required this.ref});

  final Ref ref;

  Future<void> openAssistant(BuildContext context, WidgetRef widgetRef) {
    final route = _routeForContext(context);
    final target = VisitTarget.page('global_assistant_$route');
    final experience = widgetRef
        .read(visitRecorderServiceProvider)
        .getExperience(target);
    final openContext = AssistantOpenContext(
      source: _assistantSourceForRoute(route),
      experienceLevel: switch (experience) {
        ExperienceLevel.firstTime => AssistantExperienceLevel.firstTime,
        ExperienceLevel.returning => AssistantExperienceLevel.returning,
        ExperienceLevel.frequent => AssistantExperienceLevel.frequent,
      },
      tab: route,
    );
    return context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  Widget buildQuickActionSheet({
    required BuildContext context,
    required GlobalCreateActionSelected onCreateAction,
    required VoidCallback onStartGathering,
    required VoidCallback onStartGroupChat,
    required VoidCallback onCancel,
  }) {
    return CreateActionSheet(
      onCreateAction: (action) => onCreateAction(action.name),
      onStartGathering: onStartGathering,
      onStartGroupChat: onStartGroupChat,
      onCancel: onCancel,
    );
  }

  Future<bool> openStartGathering(BuildContext context) async {
    final binding = ref.read(startGatheringNavigationBindingProvider);
    if (binding == null) {
      return false;
    }
    await binding(context);
    return true;
  }

  void openCreateCircle(BuildContext context) {
    Navigator.of(context)
        .push<String>(
          CupertinoPageRoute<String>(
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.globalSurfaceCircleEditCreate,
            ),
            builder: (_) => const CircleEditSettingsPage.create(),
          ),
        )
        .then((circleId) {
          if (!context.mounted || circleId == null || circleId.isEmpty) {
            return;
          }
          context.push(
            AppRoutePaths.circleDetail(id: circleId),
            extra: const CircleDetailPageRouteExtra(
              referralSource: ReferralSource.organicFeed,
            ),
          );
        });
  }

  static String _routeForContext(BuildContext context) {
    try {
      return GoRouterState.of(context).uri.path;
    } catch (_) {
      return AppRoutePaths.home;
    }
  }

  static AssistantSource _assistantSourceForRoute(String route) {
    if (route == AppRoutePaths.home) {
      return AssistantSource.home;
    }
    if (route == AppRoutePaths.circles || route.startsWith('/circle/')) {
      return AssistantSource.circles;
    }
    if (route.startsWith(AppRoutePaths.chat)) {
      return AssistantSource.chat;
    }
    if (route.startsWith(AppRoutePaths.createPathTemplate)) {
      return AssistantSource.create;
    }
    if (route.startsWith(AppRoutePaths.globalSearch)) {
      return AssistantSource.search;
    }
    if (route == AppRoutePaths.profile || route.startsWith('/user/')) {
      return AssistantSource.profile;
    }
    return AssistantSource.discovery;
  }
}

final globalSurfaceActionBindingsProvider =
    Provider<GlobalSurfaceActionBindings>(
      (ref) => GlobalSurfaceActionBindings(ref: ref),
    );
