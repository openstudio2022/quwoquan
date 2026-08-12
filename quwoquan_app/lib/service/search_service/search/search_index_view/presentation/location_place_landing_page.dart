import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/location_place_read_query.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';

/// 一方地点（`location.place`）落地页路由参数。
///
/// `location.place` 是被内容引用、但尚未绑定实体主页的自由文本地点（spec 单一真相源：
/// 未提升=location.place、已提升=entity.homepage）。命中详情来自搜索结果 payload，
/// 冷启动、深链和进程恢复没有 route extra 时，必须按 `placeId` 重新读取。
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
class LocationPlaceLandingPage extends StatefulWidget {
  const LocationPlaceLandingPage({
    super.key,
    required this.placeId,
    this.placeName = '',
    this.address = '',
    this.snippet = '',
    this.referralSource = ReferralSource.search,
    this.requiresCanonicalRead = false,
    required this.locationPlaceReadQuery,
    required this.journeyEventTracker,
  });

  final String placeId;
  final String placeName;
  final String address;
  final String snippet;
  final ReferralSource referralSource;
  final bool requiresCanonicalRead;
  final LocationPlaceReadQuery locationPlaceReadQuery;
  final JourneyEventTracker journeyEventTracker;

  @override
  State<LocationPlaceLandingPage> createState() =>
      _LocationPlaceLandingPageState();
}

class _LocationPlaceLandingPageState extends State<LocationPlaceLandingPage> {
  late final JourneyEventTracker _journeyTracker;
  LocationPlaceReadResult? _resolved;
  Object? _loadFailure;
  bool _loading = false;

  String get _displayName => switch (_resolved) {
    LocationPlaceReadFound(:final place) => place.name.trim(),
    _ =>
      widget.placeName.trim().isNotEmpty
          ? widget.placeName.trim()
          : CreationText.locationPlaceLandingTitle,
  };

  String get _address => switch (_resolved) {
    LocationPlaceReadFound(:final place) => place.address?.trim() ?? '',
    _ =>
      widget.address.trim().isNotEmpty
          ? widget.address.trim()
          : widget.snippet.trim(),
  };

  bool get _needsCanonicalRead => widget.requiresCanonicalRead;

  @override
  void didUpdateWidget(covariant LocationPlaceLandingPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.placeId != widget.placeId ||
        (!oldWidget.requiresCanonicalRead && _needsCanonicalRead)) {
      _startCanonicalRead();
    }
  }

  @override
  void initState() {
    super.initState();
    _journeyTracker = widget.journeyEventTracker;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackJourney('enter');
      if (_needsCanonicalRead) {
        _startCanonicalRead();
      }
    });
  }

  Future<void> _startCanonicalRead() async {
    if (!_needsCanonicalRead || _loading) {
      return;
    }
    setState(() {
      _loading = true;
      _loadFailure = null;
    });
    try {
      final result = await widget.locationPlaceReadQuery.readById(
        widget.placeId,
      );
      if (!mounted) {
        return;
      }
      if (result case LocationPlaceReadHomepageRedirect(:final homepageId)) {
        _trackJourney('promoted_redirect');
        context.go(AppRoutePaths.homepageDetail(id: homepageId));
        return;
      }
      setState(() {
        _resolved = result;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loadFailure = error;
        _loading = false;
      });
    }
  }

  @override
  void dispose() {
    // 进入/离开成对事件即停留信号，停留时长由两条事件的时间戳在云侧计算。
    _trackJourney('exit');
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final readUnavailable = _resolved is LocationPlaceReadUnavailable;
    if (_loading) {
      return CupertinoPageScaffold(child: AppRequestFeedback.page());
    }
    if (_loadFailure != null || readUnavailable) {
      final semantic = _loadFailure == null
          ? AppUserRecoveryContract.semanticFor(
              group: AppUserRecoveryGroup.contentUnavailable,
              category: UiErrorCategory.notFound,
              scope: UiErrorScope.page,
              sourceSurfaceId: 'location_place_landing',
            )
          : runtimeErrorSemantic(
              context,
              error: _loadFailure!,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            );
      return CupertinoPageScaffold(
        navigationBar: CupertinoNavigationBar(
          middle: const Text(CreationText.locationPlaceLandingTitle),
          leading: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: _handleClose,
            child: const Icon(CupertinoIcons.chevron_back),
          ),
        ),
        child: SafeArea(
          child: AppPageErrorState(
            semantic: _loadFailure == null
                ? semantic
                : ensureRetryUiErrorSemantic(semantic),
            onRecovery: (action) async {
              if (action.type == UiErrorActionType.retry) {
                await _startCanonicalRead();
                return _loadFailure == null &&
                        _resolved is! LocationPlaceReadUnavailable
                    ? UiRecoveryOutcome.recovered
                    : UiRecoveryOutcome.stillBlocked;
              }
              _handleClose();
              return UiRecoveryOutcome.handedOff;
            },
          ),
        ),
      );
    }

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return CupertinoPageScaffold(
      key: TestKeys.locationPlaceLandingPage,
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      navigationBar: CupertinoNavigationBar(
        middle: const Text(CreationText.locationPlaceLandingTitle),
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
              address: _address,
              isDark: isDark,
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              CreationText.locationPlaceLandingDescription,
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
              child: const Text(CreationText.locationPlaceLandingPromoteCta),
            ),
          ],
        ),
      ),
    );
  }

  void _promoteToHomepage() {
    _trackJourney('promote_click');
    context.push(
      AppRoutePaths.suggestHomepage(
        query: _displayName,
        sourcePlaceId: widget.placeId,
      ),
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
                  : CreationText.locationPlaceLandingMissingAddress,
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
          CreationText.locationPlaceLandingTempBadge,
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
