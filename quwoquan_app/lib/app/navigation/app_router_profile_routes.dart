part of 'app_router.dart';

GoRoute _userProfileRoute(Ref ref) => GoRoute(
  path: AppRoutePaths.userProfilePathTemplate.replaceAll(
    '{userHandle}',
    ':userHandle',
  ),
  pageBuilder: (context, state) {
    final userHandle = state.pathParameters['userHandle'] ?? '';
    final currentUser = ref.read(userDataProvider);
    final isSelf =
        currentUser != null &&
        (userHandle == currentUser.id ||
            (currentUser.userHandle != null &&
                userHandle == currentUser.userHandle));
    void onBack() {
      if (context.canPop()) {
        context.pop();
      } else {
        context.go(AppRoutePaths.home);
      }
    }

    if (isSelf) {
      return appRoutePage<void>(
        state: state,
        child: MyProfilePage(onBack: onBack),
      );
    }
    UserProfileRouteExtra? extra;
    if (state.extra is UserProfileRouteExtra) {
      extra = state.extra! as UserProfileRouteExtra;
    } else if (state.extra is Map) {
      final m = state.extra! as Map;
      extra = UserProfileRouteExtra(
        personaId: m['personaId']?.toString(),
        avatar: m['avatar']?.toString(),
        displayName: m['displayName']?.toString(),
        backgroundImage: m['backgroundImage']?.toString(),
        openMessageComposer: m['openMessageComposer'] == true,
      );
    }
    return appRoutePage<void>(
      state: state,
      child: OtherProfilePage(
        userHandle: userHandle,
        personaId: extra?.safePersonaId,
        initialAvatarUrl: extra?.safeAvatar,
        initialDisplayName: extra?.safeDisplayName,
        initialBackgroundImageUrl: extra?.safeBackgroundImage,
        referralSource: ReferralSource.authorProfile,
        openMessageComposerOnOpen: extra?.openMessageComposer ?? false,
        onBack: onBack,
      ),
    );
  },
);
