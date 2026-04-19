import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_state.dart';
import 'package:quwoquan_app/components/pageflip/src/layout/pageflip_layout_resolver.dart';
import 'package:quwoquan_app/components/pageflip/src/render/pageflip_render_frame.dart';

@immutable
class PageflipScene {
  const PageflipScene({
    required this.stageSize,
    required this.pageRect,
    required this.pageSize,
    required this.layout,
    required this.state,
    this.renderFrame,
  });

  final Size stageSize;
  final Rect pageRect;
  final Size pageSize;
  final PageflipLayout layout;
  final PageflipState state;
  final PageflipRenderFrame? renderFrame;

  PageflipMode get mode => state.mode;
  int get currentPageIndex => state.currentPageIndex;
  bool get isInteractive => state.isInteractive;
  PageflipDirection? get direction => state.direction;
  PageflipRoleState? get roleState => state.roleState;

  int? get underlayPageIndex => roleState?.underlayPageIndex;
  int? get turningPageIndex => roleState?.turningPageIndex;
  int? get coveredPageIndex => roleState?.coveredPageIndex;

  PageflipScene copyWith({
    Size? stageSize,
    Rect? pageRect,
    Size? pageSize,
    PageflipLayout? layout,
    PageflipState? state,
    PageflipRenderFrame? renderFrame,
  }) {
    return PageflipScene(
      stageSize: stageSize ?? this.stageSize,
      pageRect: pageRect ?? this.pageRect,
      pageSize: pageSize ?? this.pageSize,
      layout: layout ?? this.layout,
      state: state ?? this.state,
      renderFrame: renderFrame ?? this.renderFrame,
    );
  }

  Path buildBottomClipPath() {
    return Path()..addRect(pageRect);
  }
}
