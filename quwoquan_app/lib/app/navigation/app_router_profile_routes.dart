part of 'app_router.dart';

GoRoute _userProfileRoute(Ref ref) => GoRoute(
  path: AppRoutePaths.userProfilePathTemplate.replaceAll(
    '{username}',
    ':username',
  ),
  pageBuilder: (context, state) {
    final username = state.pathParameters['username'] ?? '';
    final currentUser = ref.read(userDataProvider);
    final isSelf =
        currentUser != null &&
        (username == currentUser.id ||
            (currentUser.username != null && username == currentUser.username));
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
    ReferralSource profileReferralSource = ReferralSource.authorProfile;
    if (state.extra is OtherProfilePageRouteExtra) {
      final profileExtra = state.extra! as OtherProfilePageRouteExtra;
      profileReferralSource =
          profileExtra.referralSource ?? ReferralSource.authorProfile;
      extra = UserProfileRouteExtra(
        subAccountId: profileExtra.subAccountId,
        avatar: profileExtra.avatar,
        displayName: profileExtra.displayName,
        backgroundImage: profileExtra.backgroundImage,
      );
    } else if (state.extra is UserProfileRouteExtra) {
      extra = state.extra! as UserProfileRouteExtra;
    } else if (state.extra is Map) {
      final m = state.extra! as Map;
      extra = UserProfileRouteExtra(
        subAccountId: m['subAccountId']?.toString(),
        avatar: m['avatar']?.toString(),
        displayName: m['displayName']?.toString(),
        backgroundImage: m['backgroundImage']?.toString(),
      );
    }
    return appRoutePage<void>(
      state: state,
      child: OtherProfilePage(
        username: username,
        subAccountId: extra?.safeSubAccountId,
        initialAvatarUrl: extra?.safeAvatar,
        initialDisplayName: extra?.safeDisplayName,
        initialBackgroundImageUrl: extra?.safeBackgroundImage,
        referralSource: profileReferralSource,
        onBack: onBack,
      ),
    );
  },
);
