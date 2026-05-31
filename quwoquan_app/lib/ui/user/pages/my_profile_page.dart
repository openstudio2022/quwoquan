import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 我的主页入口；`ProfileShell` 经 UserProfileRepository 加载 SubAccountProfileViewData。
///
/// 路由：/profile（MainAppShell IndexedStack 第4项）
/// 也可通过 /user/:username（当前用户）push 进入，此时传入 onBack 显示返回按钮。
/// 进入时自动加载当前用户档案，确保 displayName、avatar、background 正确展示。
class MyProfilePage extends ConsumerStatefulWidget {
  const MyProfilePage({super.key, this.onBack});

  final VoidCallback? onBack;

  @override
  ConsumerState<MyProfilePage> createState() => _MyProfilePageState();
}

class _MyProfilePageState extends ConsumerState<MyProfilePage> {
  bool _didTriggerLoad = false;
  bool _didTrackImpression = false;
  final Stopwatch _dwell = Stopwatch();
  String _trackedUserId = '';
  // 在 build（ref 可用）时缓存 tracker，dispose 不得再触碰 ref。
  ContentBehaviorTracker? _behaviorTracker;

  @override
  void initState() {
    super.initState();
    _dwell.start();
  }

  @override
  void dispose() {
    _dwell.stop();
    final seconds = _dwell.elapsedMilliseconds / 1000.0;
    if (_trackedUserId.isNotEmpty && seconds >= 1) {
      _behaviorTracker?.trackDwell(
        _trackedUserId,
        durationSeconds: seconds,
        contentType: 'user',
        referralSource: ReferralSource.authorProfile,
      );
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authSessionControllerProvider);
    if (!auth.isAuthenticated) {
      return const _LoggedOutProfilePrompt();
    }
    if (!_didTriggerLoad) {
      _didTriggerLoad = true;
      final currentUserId = ref.read(currentUserIdProvider);
      ref.read(userDataProvider.notifier).loadUser(currentUserId);
    }
    final userData = ref.watch(userDataProvider);
    final currentUserId = ref.watch(currentUserIdProvider);
    final userId = userData?.id ?? currentUserId;
    _trackedUserId = userId;
    final tracker = ref.read(contentBehaviorTrackerProvider);
    _behaviorTracker = tracker;
    if (!_didTrackImpression && userId.isNotEmpty) {
      _didTrackImpression = true;
      tracker.trackImpression(
        userId,
        contentType: 'user',
        referralSource: ReferralSource.authorProfile,
      );
    }

    return ProfileShell(
      mode: ProfileMode.mine,
      userId: userId,
      initialAvatarUrl: userData?.avatar ?? userData?.avatarUrl,
      initialDisplayName: userData?.displayName,
      initialBackgroundUrl: userData?.backgroundImage,
      onBack: widget.onBack,
    );
  }
}

class _LoggedOutProfilePrompt extends StatelessWidget {
  const _LoggedOutProfilePrompt();

  @override
  Widget build(BuildContext context) {
    final bottomPadding =
        AppSpacing.bottomNavHeight +
        MediaQuery.viewPaddingOf(context).bottom +
        AppSpacing.interGroupLg;
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      body: DefaultTextStyle.merge(
        style: const TextStyle(
          decoration: TextDecoration.none,
          decorationThickness: 0,
        ),
        child: Stack(
          children: <Widget>[
            const _LoggedOutProfileBackdrop(),
            SafeArea(
              child: CustomScrollView(
                physics: const BouncingScrollPhysics(
                  parent: AlwaysScrollableScrollPhysics(),
                ),
                slivers: <Widget>[
                  SliverToBoxAdapter(
                    child: SizedBox(height: AppSpacing.twoHundredTwenty),
                  ),
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerLg,
                      ),
                      child: Transform.translate(
                        offset: const Offset(0, -AppSpacing.radiusTwenty),
                        child: const _LoggedOutProfileSummaryCard(),
                      ),
                    ),
                  ),
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(
                        AppSpacing.containerLg,
                        AppSpacing.zero,
                        AppSpacing.containerLg,
                        bottomPadding,
                      ),
                      child: const _LoggedOutProfileContentPreview(),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoggedOutProfileBackdrop extends StatelessWidget {
  const _LoggedOutProfileBackdrop();

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: Column(
        children: <Widget>[
          Container(
            height: AppSpacing.twoHundredTwenty + AppSpacing.radiusTwenty,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: <Color>[
                  AppColors.brandBlue50,
                  AppColors.brandBlue100.withValues(alpha: 0.86),
                  AppColors.iosPageBackground(context),
                ],
              ),
            ),
          ),
          Expanded(
            child: ColoredBox(color: AppColors.iosPageBackground(context)),
          ),
        ],
      ),
    );
  }
}

class _LoggedOutProfileSummaryCard extends StatelessWidget {
  const _LoggedOutProfileSummaryCard();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.06),
            blurRadius: AppSpacing.thirtySix,
            offset: const Offset(AppSpacing.zero, AppSpacing.ten),
          ),
        ],
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          children: <Widget>[
            Container(
              width: AppSpacing.avatarUserXl,
              height: AppSpacing.avatarUserXl,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.iosSecondaryFill(context),
              ),
              child: Icon(
                CupertinoIcons.person_crop_circle,
                size: AppSpacing.avatarUserLg,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              UITextConstants.profileLoggedOutDisplayName,
              style: TextStyle(
                fontSize: AppTypography.iosTitle2,
                fontWeight: AppTypography.bold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              UITextConstants.profileLoginCardSubtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                height: AppSpacing.textLineHeightBody,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupLg),
            CupertinoButton(
              color: AppColors.primaryColor,
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.buttonHeightLg,
              ),
              onPressed: () => context.push(
                AppRoutePaths.login(
                  reason: AuthPromptReason.actionRequired.name,
                  redirect: AppRoutePaths.profile,
                ),
              ),
              child: Text(
                UITextConstants.profileLoginNow,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoggedOutProfileContentPreview extends StatelessWidget {
  const _LoggedOutProfileContentPreview();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            const _LoggedOutStatsRow(),
            SizedBox(height: AppSpacing.interGroupLg),
            Divider(
              height: AppSpacing.one,
              color: AppColors.iosSeparator(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: const <Widget>[
                _LoggedOutTabLabel(UITextConstants.creationFilterWork),
                _LoggedOutTabLabel(UITextConstants.favorite),
                _LoggedOutTabLabel(UITextConstants.profileLikedTab),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupLg),
            const _LoggedOutEmptyHint(),
          ],
        ),
      ),
    );
  }
}

class _LoggedOutStatsRow extends StatelessWidget {
  const _LoggedOutStatsRow();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: const <Widget>[
        _LoggedOutStatItem(label: UITextConstants.creationFilterWork),
        _LoggedOutStatItem(label: UITextConstants.favorite),
        _LoggedOutStatItem(label: UITextConstants.follow),
      ],
    );
  }
}

class _LoggedOutStatItem extends StatelessWidget {
  const _LoggedOutStatItem({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Text(
          '--',
          style: TextStyle(
            fontSize: AppTypography.iosTitle3,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _LoggedOutTabLabel extends StatelessWidget {
  const _LoggedOutTabLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        fontSize: AppTypography.iosCallout,
        fontWeight: AppTypography.semiBold,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );
  }
}

class _LoggedOutEmptyHint extends StatelessWidget {
  const _LoggedOutEmptyHint();

  @override
  Widget build(BuildContext context) {
    return Container(
      alignment: Alignment.center,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupLg),
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
      ),
      child: Text(
        UITextConstants.profileLoggedOutTimelineHint,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: AppTypography.iosCallout,
          height: AppSpacing.textLineHeightBody,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}
