import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/fold_axis_state_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/leaf_pose_v2.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/page_touch_state_v2.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class PageflipBookIsolatedScene {
  const PageflipBookIsolatedScene({
    required this.stageSize,
    required this.pageRect,
    required this.pageSize,
    required this.layout,
    required this.visibleSpread,
    required this.currentPageIndex,
    required this.sheetBinding,
    this.direction,
    this.corner,
    this.touchState,
    this.foldAxisState,
    this.pose,
    this.coveredCurrentPageIndex,
    this.turningFrontPageIndex,
    this.turningBackPageIndex,
    this.nextUnderPageIndex,
  });
  final Size stageSize;
  final Rect pageRect;
  final Size pageSize;
  final StPageFlipLayout layout;
  final StPageFlipVisibleSpread visibleSpread;
  final int currentPageIndex;
  final PageflipBookIsolatedSheetBinding? sheetBinding;
  final PageflipBookIsolatedDirection? direction;
  final PageflipBookIsolatedCorner? corner;
  final PageTouchStateV2? touchState;
  final FoldAxisStateV2? foldAxisState;
  final LeafPoseV2? pose;
  final int? coveredCurrentPageIndex;
  final int? turningFrontPageIndex;
  final int? turningBackPageIndex;
  final int? nextUnderPageIndex;

  bool get isInteractive =>
      direction != null &&
      corner != null &&
      sheetBinding != null &&
      pose != null &&
      touchState != null &&
      foldAxisState != null;

  bool get drawsCoveredCurrentPage =>
      coveredCurrentPageIndex != null &&
      turningFrontPageIndex != null &&
      coveredCurrentPageIndex != turningFrontPageIndex;

  Path buildBottomClipPath() {
    final foldAxis = foldAxisState;
    if (foldAxis == null) {
      return Path()..addRect(pageRect);
    }
    return foldAxis.bottomClipPath.shift(pageRect.topLeft);
  }
}
