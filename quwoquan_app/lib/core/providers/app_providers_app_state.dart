part of 'app_providers.dart';

/// 主题相关的便捷Provider
final isDarkProvider = Provider<bool>((ref) {
  return ref.watch(effectiveIsDarkProvider);
});

enum AppBreakpoint { compact, regular, expanded }

class ResponsiveState {
  final Size size;
  final double devicePixelRatio;
  final Orientation orientation;
  final AppBreakpoint breakpoint;

  const ResponsiveState({
    this.size = Size.zero,
    this.devicePixelRatio = 1.0,
    this.orientation = Orientation.portrait,
    this.breakpoint = AppBreakpoint.regular,
  });

  ResponsiveState copyWith({
    Size? size,
    double? devicePixelRatio,
    Orientation? orientation,
    AppBreakpoint? breakpoint,
  }) {
    return ResponsiveState(
      size: size ?? this.size,
      devicePixelRatio: devicePixelRatio ?? this.devicePixelRatio,
      orientation: orientation ?? this.orientation,
      breakpoint: breakpoint ?? this.breakpoint,
    );
  }

  @override
  bool operator ==(Object other) {
    return other is ResponsiveState &&
        other.size == size &&
        other.devicePixelRatio == devicePixelRatio &&
        other.orientation == orientation &&
        other.breakpoint == breakpoint;
  }

  @override
  int get hashCode =>
      Object.hash(size, devicePixelRatio, orientation, breakpoint);
}

class ResponsiveNotifier extends Notifier<ResponsiveState> {
  @override
  ResponsiveState build() {
    return const ResponsiveState();
  }

  void updateFromMediaQueryData(MediaQueryData data) {
    updateFromSize(data.size, devicePixelRatio: data.devicePixelRatio);
  }

  void updateFromSize(Size size, {double devicePixelRatio = 1.0}) {
    final breakpoint = switch (size.width) {
      < 360 => AppBreakpoint.compact,
      >= 600 => AppBreakpoint.expanded,
      _ => AppBreakpoint.regular,
    };
    final orientation = size.width > size.height
        ? Orientation.landscape
        : Orientation.portrait;
    final next = ResponsiveState(
      size: size,
      devicePixelRatio: devicePixelRatio,
      orientation: orientation,
      breakpoint: breakpoint,
    );
    if (next == state) return;
    state = next;
  }
}

class AppearanceSnapshot {
  final ThemeMode themeMode;
  final Brightness effectiveBrightness;
  final bool isDark;
  final AppFontSizePreset fontSizePreset;
  final double textScaleFactor;
  final bool boldText;
  final bool highContrast;
  final bool disableAnimations;
  final AppBreakpoint breakpoint;
  final ResponsiveState responsiveState;

  const AppearanceSnapshot({
    required this.themeMode,
    required this.effectiveBrightness,
    required this.isDark,
    required this.fontSizePreset,
    required this.textScaleFactor,
    required this.boldText,
    required this.highContrast,
    required this.disableAnimations,
    required this.breakpoint,
    required this.responsiveState,
  });
}

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

/// 用户数据 Provider — 通过对象级 ProfileQuery 加载档案。
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(
    String userId, {
    required AppUiSurface sourceSurface,
  }) async {
    try {
      final profile = await ref
          .read(profileQueryProvider(sourceSurface))
          .getUserProfile('me');
      // 本地选取（相册/拍照）但尚未上传的临时文件路径原样保留（alpha 保存后即时回显），
      // 不经媒体解析器拼成不可访问 URL；服务端对象键 / 远端地址仍正常解析。
      final avatarUrl = isLocalFileImageSource(profile.avatarUrl)
          ? profile.avatarUrl
          : resolveAvatarImageUrl(
              profile.avatarUrl,
              avatarVersion: profile.avatarVersion,
            );
      final backgroundUrl = isLocalFileImageSource(profile.backgroundUrl)
          ? profile.backgroundUrl
          : resolveContentMediaUrl(profile.backgroundUrl);
      final subAccountId = profile.subAccountId.isNotEmpty
          ? profile.subAccountId
          : userId;
      state = User(
        id: subAccountId,
        username: profile.username.isNotEmpty ? profile.username : userId,
        displayName: profile.displayName.isNotEmpty
            ? profile.displayName
            : null,
        avatarUrl: avatarUrl,
        avatar: avatarUrl,
        bio: profile.bio.isNotEmpty ? profile.bio : null,
        backgroundImage: backgroundUrl.isNotEmpty ? backgroundUrl : null,
        metadata: <String, dynamic>{
          'ownerUserId': profile.ownerUserId,
          'subAccountId': profile.subAccountId,
          'subjectType': profile.subjectType,
          'avatarVersion': profile.avatarVersion,
        },
      );
    } catch (_) {
      state = User(id: userId, username: userId);
    }
  }
}

final userDataProvider = NotifierProvider<UserDataNotifier, User?>(() {
  return UserDataNotifier();
});

/// 当前用户 ID — 以 User 快照为准；环境包可显式注入测试/预置用户。
final currentUserIdProvider = Provider<String>((ref) {
  final authSession = ref.watch(authSessionControllerProvider);
  if (authSession.activeSubAccountId.isNotEmpty) {
    return authSession.activeSubAccountId;
  }
  final profileUserId = ref.watch(userDataProvider)?.id;
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
  final ownerUserId =
      currentUser?.metadata?['ownerUserId']?.toString().trim() ?? '';
  if (ownerUserId.isNotEmpty) {
    return ownerUserId;
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
