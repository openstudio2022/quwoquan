import 'dart:math' show max;

import 'package:flutter/widgets.dart';

import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 沉浸作品页的交集信息与操作栏共用的垂直空间。
final class WorksImmersiveContentLayout {
  const WorksImmersiveContentLayout._();

  static double intersectionLineHeight(BuildContext context) {
    return AppTypography.xxs * AppSpacing.textLineHeightFootnote;
  }

  static double intersectionBottomClearance(BuildContext context) {
    return ImmersiveEngagementBar.overlayClearance(
      context,
      gap: AppSpacing.intraGroupXs,
    );
  }

  static double overlayBottomClearance(
    BuildContext context, {
    required bool includeIntersection,
    required double gap,
  }) {
    if (!includeIntersection) {
      return ImmersiveEngagementBar.overlayClearance(context, gap: gap);
    }
    return ImmersiveEngagementBar.reservedHeight(context) +
        AppSpacing.intraGroupXs +
        intersectionLineHeight(context) +
        gap;
  }
}

class WorksImmersiveVerticalPagePhysics extends PageScrollPhysics {
  const WorksImmersiveVerticalPagePhysics({
    required this.currentPage,
    this.holdVerticalScroll,
    super.parent,
  });

  static const double _commitFraction = 0.20;

  final int Function() currentPage;
  final bool Function()? holdVerticalScroll;

  @override
  WorksImmersiveVerticalPagePhysics applyTo(ScrollPhysics? ancestor) {
    return WorksImmersiveVerticalPagePhysics(
      currentPage: currentPage,
      holdVerticalScroll: holdVerticalScroll,
      parent: buildParent(ancestor),
    );
  }

  @override
  bool shouldAcceptUserOffset(ScrollMetrics position) {
    if (holdVerticalScroll?.call() ?? false) {
      return false;
    }
    return super.shouldAcceptUserOffset(position);
  }

  @override
  double applyPhysicsToUserOffset(ScrollMetrics position, double offset) {
    if (holdVerticalScroll?.call() ?? false) {
      return 0;
    }
    return super.applyPhysicsToUserOffset(position, offset);
  }

  @override
  Simulation? createBallisticSimulation(
    ScrollMetrics position,
    double velocity,
  ) {
    if ((velocity <= 0.0 && position.pixels <= position.minScrollExtent) ||
        (velocity >= 0.0 && position.pixels >= position.maxScrollExtent)) {
      return super.createBallisticSimulation(position, velocity);
    }
    final tolerance = toleranceFor(position);
    final target = _targetPixels(position, tolerance, velocity);
    if ((target - position.pixels).abs() < tolerance.distance) {
      return null;
    }
    return ScrollSpringSimulation(
      spring,
      position.pixels,
      target,
      velocity,
      tolerance: tolerance,
    );
  }

  double _targetPixels(
    ScrollMetrics position,
    Tolerance tolerance,
    double velocity,
  ) {
    final anchorPage = currentPage().toDouble();
    final currentScrollPage = _pageForPixels(position, position.pixels);
    var targetPage = anchorPage;
    final deltaFromAnchor = currentScrollPage - anchorPage;
    if (deltaFromAnchor >= _commitFraction) {
      targetPage = anchorPage + 1;
    } else if (deltaFromAnchor <= -_commitFraction) {
      targetPage = anchorPage - 1;
    } else if (velocity < -tolerance.velocity) {
      targetPage = anchorPage + 1;
    } else if (velocity > tolerance.velocity) {
      targetPage = anchorPage - 1;
    }

    final minPage = _pageForPixels(position, position.minScrollExtent);
    final maxPage = _pageForPixels(position, position.maxScrollExtent);
    final clampedPage = targetPage.clamp(minPage, maxPage).toDouble();
    return _pixelsForPage(
      position,
      clampedPage,
    ).clamp(position.minScrollExtent, position.maxScrollExtent).toDouble();
  }

  double _pageForPixels(ScrollMetrics position, double pixels) {
    if (position is PageMetrics && position.page != null) {
      final extent = _pageExtent(position);
      return extent <= 0 ? 0 : pixels / extent;
    }
    final viewport = position.viewportDimension;
    return viewport <= 0 ? 0 : pixels / viewport;
  }

  double _pixelsForPage(ScrollMetrics position, double page) {
    return page * _pageExtent(position);
  }

  double _pageExtent(ScrollMetrics position) {
    final fraction = position is PageMetrics ? position.viewportFraction : 1.0;
    return max(1.0, position.viewportDimension * fraction);
  }
}
