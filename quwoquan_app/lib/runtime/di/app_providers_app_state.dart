import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/runtime/shell/state/accessibility_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/shell/state/appearance_state.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/user_data_notifier.dart';

export 'package:quwoquan_app/runtime/shell/state/appearance_state.dart';

// 已验证主体快照被 navigation / chat / rtc / ui.user 共同消费，且 app_state 的
// currentUserId / resolvedOwnerUserId 就建立在它之上；provider 定义留在 persona 对象内，
// 由本分片继续承担 barrel 侧的单一 import 面。
export 'package:quwoquan_app/service/user_service/persona_management/persona/application/user_data_notifier.dart'
    show UserDataNotifier, userDataProvider;

/// 从 assistant 域退出时恢复的主底栏 tab。
/// 仅记录进入 assistant 前的上一个主 tab，避免多处维护数字索引语义。
final lastMainTabBeforeAssistantProvider =
    NotifierProvider<LastMainTabBeforeAssistantNotifier, MainTabDestination?>(
      LastMainTabBeforeAssistantNotifier.new,
    );

class LastMainTabBeforeAssistantNotifier extends Notifier<MainTabDestination?> {
  @override
  MainTabDestination? build() => null;

  void set(MainTabDestination? value) => state = value;
}

/// 当前用户 ID — 以 Persona 快照为准；环境包可显式注入测试/预置用户。
final currentUserIdProvider = Provider<String>((ref) {
  final authSession = ref.watch(authSessionControllerProvider);
  if (authSession.activePersonaId.isNotEmpty) {
    return authSession.activePersonaId;
  }
  final profileUserId = ref.watch(userDataProvider)?.personaId;
  if (profileUserId != null && profileUserId.isNotEmpty) {
    return profileUserId;
  }
  return const String.fromEnvironment('APP_CURRENT_USER_ID');
});

/// 当前请求归属的 owner user id。
///
/// 优先使用已加载用户快照里的 `ownerUserId`，否则回退到当前用户 id，
/// 避免 remote 读链路在分身上下文尚未就绪时完全拿不到 `X-Client-User-Id`。
final resolvedOwnerUserIdProvider = Provider<String>((ref) {
  final authOwnerId = ref.watch(authSessionControllerProvider).ownerId.trim();
  if (authOwnerId.isNotEmpty) {
    return authOwnerId;
  }
  final currentUser = ref.watch(userDataProvider);
  final ownerUserId = currentUser?.ownerUserId.trim() ?? '';
  if (ownerUserId.isNotEmpty) {
    return ownerUserId;
  }
  return ref.watch(currentUserIdProvider).trim();
});

/// 当前命令 actor 的已认证 Persona ID。
///
/// Command header 必须能在 App 冷启动后的第一条用户意图中立即构造，不能等待
/// 另一次 Persona projection query。认证 grant 中的 activePersonaId 是该时刻的
/// canonical actor；环境编译值只保留给尚未建立认证会话的只读兼容路径。
final resolvedActivePersonaIdProvider = Provider<String>((ref) {
  final sessionPersonaId = ref
      .watch(authSessionControllerProvider)
      .activePersonaId
      .trim();
  if (sessionPersonaId.isNotEmpty) {
    return sessionPersonaId;
  }
  return ref.watch(currentUserIdProvider).trim();
});

/// 响应式Provider
final responsiveProvider =
    NotifierProvider<ResponsiveNotifier, ResponsiveState>(() {
      return ResponsiveNotifier();
    });

final appResourceCacheProfileProvider = Provider<AppResourceCacheProfile>((
  ref,
) {
  final responsiveState = ref.watch(responsiveProvider);
  final capabilities = ref.watch(platformCapabilitiesProvider);
  if (!capabilities.wideScreenLayout ||
      responsiveState.breakpoint == AppBreakpoint.compact) {
    return AppResourceCacheProfile.compact;
  }
  if (responsiveState.breakpoint == AppBreakpoint.expanded) {
    return AppResourceCacheProfile.expanded;
  }
  return AppResourceCacheProfile.regular;
});

/// 聚合后的全局外观快照，供根入口和共享组件消费。
final appearanceSnapshotProvider = Provider<AppearanceSnapshot>((ref) {
  final themeState = ref.watch(themeProvider);
  final accessibilityState = ref.watch(accessibilityProvider);
  final responsiveState = ref.watch(responsiveProvider);
  return AppearanceSnapshot(
    themeMode: themeState.themeMode,
    effectiveBrightness: themeState.effectiveBrightness,
    isDark: themeState.isDark,
    fontSizePreset: accessibilityState.fontSizePreset,
    textScaleFactor: accessibilityState.actualTextScaleFactor,
    boldText: accessibilityState.boldText,
    highContrast: accessibilityState.highContrast,
    disableAnimations: accessibilityState.disableAnimations,
    breakpoint: responsiveState.breakpoint,
    responsiveState: responsiveState,
  );
});

/// 浏览记录服务 Provider（小趣基线：记录访问用于 experienceLevel）。
/// 访问 actor 由服务端从已验证主体派生，端侧不再传递 userId。
final visitRecorderServiceProvider = Provider<VisitRecorderService>((ref) {
  return VisitRecorderService(
    remoteWriter: ref.watch(opsVisitAppendWriterProvider),
  );
});
