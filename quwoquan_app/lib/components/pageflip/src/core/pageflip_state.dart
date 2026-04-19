import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/render/pageflip_render_frame.dart';

@immutable
class PageflipRoleState {
  const PageflipRoleState({
    required this.currentPageIndex,
    required this.turningPageIndex,
    this.underlayPageIndex,
    this.coveredPageIndex,
    this.leftPageIndex,
    this.rightPageIndex,
  });

  final int currentPageIndex;
  final int turningPageIndex;
  final int? underlayPageIndex;
  final int? coveredPageIndex;
  final int? leftPageIndex;
  final int? rightPageIndex;

  List<int> get prioritizedPageIndices {
    final indices = <int>[];
    void addUnique(int? index) {
      if (index == null || indices.contains(index)) {
        return;
      }
      indices.add(index);
    }

    addUnique(currentPageIndex);
    addUnique(turningPageIndex);
    addUnique(underlayPageIndex);
    addUnique(coveredPageIndex);
    addUnique(leftPageIndex);
    addUnique(rightPageIndex);
    return List<int>.unmodifiable(indices);
  }
}

@immutable
class PageflipState {
  const PageflipState({
    required this.mode,
    required this.currentPageIndex,
    this.direction,
    this.roleState,
    this.renderFrame,
    this.isInteractive = false,
    this.isSettling = false,
  });

  final PageflipMode mode;
  final int currentPageIndex;
  final PageflipDirection? direction;
  final PageflipRoleState? roleState;
  final PageflipRenderFrame? renderFrame;
  final bool isInteractive;
  final bool isSettling;

  PageflipState copyWith({
    PageflipMode? mode,
    int? currentPageIndex,
    PageflipDirection? direction,
    PageflipRoleState? roleState,
    PageflipRenderFrame? renderFrame,
    bool? isInteractive,
    bool? isSettling,
  }) {
    return PageflipState(
      mode: mode ?? this.mode,
      currentPageIndex: currentPageIndex ?? this.currentPageIndex,
      direction: direction ?? this.direction,
      roleState: roleState ?? this.roleState,
      renderFrame: renderFrame ?? this.renderFrame,
      isInteractive: isInteractive ?? this.isInteractive,
      isSettling: isSettling ?? this.isSettling,
    );
  }
}
