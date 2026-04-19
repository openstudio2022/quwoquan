import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_mode.dart';
import 'package:quwoquan_app/components/pageflip/src/core/pageflip_state.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';

@immutable
class PageflipRenderFrame {
  const PageflipRenderFrame({
    required this.mode,
    required this.direction,
    required this.roleState,
    required this.canonicalFrame,
  });

  final PageflipMode mode;
  final PageflipDirection direction;
  final PageflipRoleState roleState;
  final StPageFlipRenderFrame canonicalFrame;

  double get angle => canonicalFrame.angle;
  double get progress => canonicalFrame.progress;
  bool get usesThreeStageBackflow => canonicalFrame.usesThreeStageBackflow;
}
