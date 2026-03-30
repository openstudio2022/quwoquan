import 'package:flutter/widgets.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';

/// 页面级 open/return 写入 [AppLogService]（与 [MainAppShell] 同构，供全屏路由 Observer 复用）。
Future<void> writeAppPageAccessOpen({
  required String location,
  required String pageVisitId,
  String? pageNameOverride,
}) async {
  final trace = AppTraceContextStore.instance;
  final pageName = pageNameOverride ?? pageNameFromRouteLocation(location);
  await AppLogService.instance.writeEvent(
    logType: AppLogType.pageAccess,
    level: AppLogLevel.info,
    context: AppLogContext(
      sessionId: trace.sessionId,
      journeyId: trace.journeyId,
      pageVisitId: pageVisitId,
    ),
    payload: <String, dynamic>{
      'event': 'open',
      'route': location,
      'pageName': pageName,
    },
    summaryPayload: <String, dynamic>{'event': 'open', 'route': location},
  );
  await AppLogService.instance.writeEvent(
    logType: AppLogType.perf,
    level: AppLogLevel.info,
    context: AppLogContext(
      sessionId: trace.sessionId,
      journeyId: trace.journeyId,
      pageVisitId: pageVisitId,
    ),
    payload: AppPerfProbe.snapshot(event: 'page_open', route: location),
    summaryPayload: <String, dynamic>{
      'event': 'page_open',
      'route': location,
    },
  );
}

Future<void> writeAppPageAccessReturn({
  required String location,
  required String pageVisitId,
  required DateTime enterAt,
  String? pageNameOverride,
}) async {
  final trace = AppTraceContextStore.instance;
  final durationMs = DateTime.now().difference(enterAt).inMilliseconds;
  final pageName = pageNameOverride ?? pageNameFromRouteLocation(location);
  await AppLogService.instance.writeEvent(
    logType: AppLogType.pageAccess,
    level: AppLogLevel.info,
    context: AppLogContext(
      sessionId: trace.sessionId,
      journeyId: trace.journeyId,
      pageVisitId: pageVisitId,
    ),
    payload: <String, dynamic>{
      'event': 'return',
      'route': location,
      'pageName': pageName,
      'durationMs': durationMs,
    },
    summaryPayload: <String, dynamic>{
      'event': 'return',
      'route': location,
      'durationMs': durationMs,
    },
  );
  await AppLogService.instance.writeEvent(
    logType: AppLogType.perf,
    level: AppLogLevel.info,
    context: AppLogContext(
      sessionId: trace.sessionId,
      journeyId: trace.journeyId,
      pageVisitId: pageVisitId,
    ),
    payload: AppPerfProbe.snapshot(
      event: 'page_return',
      route: location,
      latencyMs: durationMs,
    ),
    summaryPayload: <String, dynamic>{
      'event': 'page_return',
      'route': location,
      'latencyMs': durationMs,
    },
  );
}

String pageNameFromRouteLocation(String location) {
  var path = location.split('?').first;
  if (path.length > 1 && path.endsWith('/')) {
    path = path.substring(0, path.length - 1);
  }

  // Internal (Navigator.push + RouteSettings.name)
  switch (path) {
    case PageAccessInternalRoutes.createMediaPicker:
      return 'create_media_picker';
    case PageAccessInternalRoutes.createMediaPickerConfirm:
      return 'create_media_picker_confirm';
    case PageAccessInternalRoutes.createMediaPickerOneTapMovie:
      return 'create_media_picker_one_tap_movie';
    case PageAccessInternalRoutes.createPageCamera:
      return 'create_camera';
    case PageAccessInternalRoutes.createPageVideoEditor:
      return 'create_video_editor';
    case PageAccessInternalRoutes.createPageImagePreview:
      return 'create_image_preview';
    case PageAccessInternalRoutes.createPagePublishSettings:
      return 'create_publish_settings';
    case PageAccessInternalRoutes.createPagePublishConfirm:
      return 'create_publish_confirm';
    case PageAccessInternalRoutes.createPageArticlePreview:
      return 'create_article_preview';
    case PageAccessInternalRoutes.createPageLocationPicker:
      return 'create_location_picker';
    case PageAccessInternalRoutes.createPagePublishCircleSelect:
      return 'create_publish_circle_select';
    case PageAccessInternalRoutes.createPageHomepageSearch:
      return 'create_homepage_search';
    case PageAccessInternalRoutes.circleShellEditSettings:
      return 'circle_edit_settings';
    case PageAccessInternalRoutes.circleMediaPickerCamera:
      return 'circle_media_camera';
    case PageAccessInternalRoutes.circleMediaPickerGallery:
      return 'circle_media_gallery';
    case PageAccessInternalRoutes.globalSurfaceCircleEditCreate:
      return 'circle_edit_create';
    case PageAccessInternalRoutes.publishLocationSearch:
      return 'publish_location_search';
    case PageAccessInternalRoutes.chatInputExpandedDraft:
      return 'chat_input_expanded_draft';
    case PageAccessInternalRoutes.assistantConversationChatSettings:
      return 'assistant_chat_settings_modal';
    case PageAccessInternalRoutes.assistantConversationReferenceWeb:
      return 'assistant_reference_webview_modal';
    case PageAccessInternalRoutes.assistantConversationDevReplay:
      return 'assistant_dev_replay_modal';
    case PageAccessInternalRoutes.assistantChatSettingsHistory:
      return 'assistant_chat_history';
  }

  if (path == AppRoutePaths.home ||
      path == AppRoutePaths.circles ||
      path == AppRoutePaths.assistant ||
      path == AppRoutePaths.profile) {
    return mainTabFromLocation(path).routeName;
  }
  if (path == AppRoutePaths.chat) {
    return MainTabDestination.chat.routeName;
  }

  if (path == AppRoutePaths.welcome) return 'welcome';
  if (path == AppRoutePaths.startGroupChat) return 'start_group_chat';
  if (path == AppRoutePaths.createEntry) return 'create_entry';
  if (path == AppRoutePaths.globalSearch) return 'global_search';
  if (path == AppRoutePaths.globalSearchNetworkResultsPathTemplate ||
      path.startsWith('${AppRoutePaths.globalSearch}/network')) {
    return 'global_search_network';
  }
  if (path == AppRoutePaths.homepagePickerPathTemplate ||
      path.startsWith('/homepages/picker')) {
    return 'homepage_picker';
  }
  if (path == AppRoutePaths.suggestHomepagePathTemplate ||
      path.startsWith('/homepages/suggest')) {
    return 'suggest_homepage';
  }
  if (path.startsWith('/homepages/')) {
    if (path.endsWith('/claim')) return 'homepage_claim';
    if (path.endsWith('/manage')) return 'homepage_maintenance';
    if (path.endsWith('/status-report')) return 'homepage_status_report';
    if (RegExp(r'^/homepages/[^/]+$').hasMatch(path)) {
      return 'homepage_detail';
    }
  }
  if (path == AppRoutePaths.createPathTemplate ||
      path.startsWith('${AppRoutePaths.createPathTemplate}/')) {
    if (path.startsWith(AppRoutePaths.createEditImagePathTemplate)) {
      return 'create_edit_image';
    }
    return 'create';
  }
  if (path.startsWith('/circle/')) {
    if (path.contains('/stats')) return 'circle_stats';
    return 'circle_detail';
  }
  if (path.startsWith('/article/')) return 'article_detail';
  if (path.startsWith('/user/')) return 'user_profile';
  if (path.startsWith('/media-viewer/')) return 'media_viewer';
  if (path.startsWith('/video-viewer/')) return 'video_viewer';
  if (path == AppRoutePaths.assistantManagement) return 'assistant_management';
  if (path == AppRoutePaths.assistantSkills) return 'assistant_skills';
  if (path == AppRoutePaths.settings) return 'settings';
  if (path == AppRoutePaths.settingsDeveloper) return 'settings_developer';
  if (path == AppRoutePaths.profileEdit) return 'profile_edit';
  if (path == AppRoutePaths.profilePersonas) return 'profile_personas';
  if (path == AppRoutePaths.profileComments) return 'profile_comments';
  if (path == AppRoutePaths.profileResonance) return 'profile_resonance';
  if (path.startsWith('/profile/stats')) return 'profile_stats';
  if (path.startsWith('/rtc/outgoing/')) return 'rtc_outgoing';
  if (path.startsWith('/rtc/incoming/')) return 'rtc_incoming';
  if (path.startsWith('/rtc/voice/')) return 'rtc_voice';
  if (path.startsWith('/rtc/video/')) return 'rtc_video';
  if (path == AppRoutePaths.rtcPickParticipants) return 'rtc_pick_participants';

  if (path.startsWith('/chat/')) {
    if (path.endsWith('/settings')) return 'chat_settings';
    if (path.endsWith('/member-search')) return 'chat_member_search';
    if (path.endsWith('/add-members')) return 'chat_add_members';
    if (path.endsWith('/manage')) return 'chat_manage';
    if (path.endsWith('/transfer-ownership')) return 'chat_transfer_ownership';
    if (path.endsWith('/admins')) return 'chat_admins';
    if (RegExp(r'^/chat/[^/]+$').hasMatch(path)) {
      return 'chat_detail';
    }
    return 'chat_subroute';
  }

  return 'route_unregistered';
}

/// 主壳 Tab 路由由 [MainAppShell] 单独埋点；Observer 跳过以免重复。
bool isShellTabLocation(String? routeName) {
  if (routeName == null || routeName.isEmpty) return false;
  var n = routeName;
  if (n != '/' && n.endsWith('/')) {
    n = n.substring(0, n.length - 1);
  }
  return n == AppRoutePaths.home ||
      n == AppRoutePaths.circles ||
      n == AppRoutePaths.chat ||
      n == AppRoutePaths.profile ||
      n == AppRoutePaths.assistant;
}

String? routeLocationFromSettings(Route<dynamic> route) {
  final name = route.settings.name;
  if (name != null && name.isNotEmpty) return name;
  return null;
}
