import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';

/// 一方地点（`location.place`）落地页路由参数。
///
/// `location.place` 是被内容引用、但尚未绑定实体主页的自由文本地点（spec 单一真相源：
/// 未提升=location.place、已提升=entity.homepage）。命中详情来自搜索结果 payload，
/// 落地页本身无独立后端 operation；提升动作复用 `suggestHomepage` surface。
class LocationPlaceLandingPageRouteExtra {
  const LocationPlaceLandingPageRouteExtra({
    this.placeName = '',
    this.address = '',
    this.snippet = '',
    this.referralSource = ReferralSource.search,
  });

  final String placeName;
  final String address;
  final String snippet;
  final ReferralSource referralSource;
}

/// 临时地点卡 + “提升为实体主页”引导（R-S05e-1）。
class LocationPlaceLandingPage extends ConsumerStatefulWidget {
  const LocationPlaceLandingPage({
    super.key,
    required this.placeId,
    this.placeName = '',
    this.address = '',
    this.snippet = '',
    this.referralSource = ReferralSource.search,
  });

  final String placeId;
  final String placeName;
  final String address;
  final String snippet;
  final ReferralSource referralSource;

  @override
  ConsumerState<LocationPlaceLandingPage> createState() =>
      _LocationPlaceLandingPageState();
}

class _LocationPlaceLandingPageState
    extends ConsumerState<LocationPlaceLandingPage> {
  late final JourneyEventTracker _journeyTracker;

  String get _displayName => widget.placeName.trim().isNotEmpty
      ? widget.placeName.trim()
      : UITextConstants.locationPlaceLandingTitle;

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackJourney('enter');
    });
  }

  @override
  void dispose() {
    // 进入/离开成对事件即停留信号，停留时长由两条事件的时间戳在云侧计算。
    _trackJourney('exit');
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final address = widget.address.trim().isNotEmpty
        ? widget.address.trim()
        : widget.snippet.trim();
    return CupertinoPageScaffold(
      key: TestKeys.locationPlaceLandingPage,
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      navigationBar: CupertinoNavigationBar(
        middle: const Text(UITextConstants.locationPlaceLandingTitle),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _handleClose,
          child: const Icon(CupertinoIcons.chevron_back),
        ),
      ),
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
            AppSpacing.interGroupLg,
          ),
          children: <Widget>[
            _LocationPlaceCard(
              displayName: _displayName,
              address: address,
              isDark: isDark,
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              UITextConstants.locationPlaceLandingDescription,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                height: AppTypography.lineHeightRelaxed,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            CupertinoButton.filled(
              key: TestKeys.locationPlaceLandingPromoteButton,
              onPressed: _promoteToHomepage,
              child: const Text(
                UITextConstants.locationPlaceLandingPromoteCta,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _promoteToHomepage() {
    _trackJourney('promote_click');
    context.push(
      AppRoutePaths.suggestHomepage(query: _displayName),
    );
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.globalSearch);
  }

  void _trackJourney(String action) {
    unawaited(
      _journeyTracker.trackAction(
        journey: 'location_place_landing',
        action: action,
        pageName: 'location_place_landing',
        targetType: 'location_place',
        targetKey: widget.placeId,
        entityType: 'location_place',
        entityId: widget.placeId,
      ),
    );
  }
}

class _LocationPlaceCard extends StatelessWidget {
  const _LocationPlaceCard({
    required this.displayName,
    required this.address,
    required this.isDark,
  });

  final String displayName;
  final String address;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  CupertinoIcons.location_solid,
                  size: AppSpacing.iconMedium,
                  color: AppColors.iosAccent(context),
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(
                  child: Text(
                    displayName,
                    style: TextStyle(
                      fontSize: AppTypography.iosTitle3,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ),
                _TempBadge(isDark: isDark),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              address.isNotEmpty
                  ? address
                  : UITextConstants.locationPlaceLandingMissingAddress,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TempBadge extends StatelessWidget {
  const _TempBadge({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.intraGroupSm,
          vertical: AppSpacing.intraGroupXs,
        ),
        child: Text(
          UITextConstants.locationPlaceLandingTempBadge,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            fontWeight: AppTypography.medium,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}
