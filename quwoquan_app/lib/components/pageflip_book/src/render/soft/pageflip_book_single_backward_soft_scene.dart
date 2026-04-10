import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_raster_snapshot.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_single_backward_soft_frame.dart';
import 'package:quwoquan_app/components/pageflip_book/src/scene/pageflip_book_scene_contract.dart';

@immutable
class PageflipBookSingleBackwardSoftScene {
  PageflipBookSingleBackwardSoftScene({
    required this.pageRect,
    required this.pageSize,
    required this.sheetBinding,
    required this.surfaces,
    required this.frame,
    required this.shadowColor,
    required this.highlightColor,
    required this.paperTintColor,
    this.rasterBundle,
  }) : assert(
         surfaces.containsKey(PageflipBookSurfaceRole.turningFront),
         'turningFront surface is required',
       ),
       assert(
         surfaces.containsKey(PageflipBookSurfaceRole.turningBack),
         'turningBack surface is required',
       );

  final Rect pageRect;
  final Size pageSize;
  final PageflipBookSheetBinding sheetBinding;
  final Map<PageflipBookSurfaceRole, Widget> surfaces;
  final PageflipBookSingleBackwardSoftFrame frame;
  final Color shadowColor;
  final Color highlightColor;
  final Color paperTintColor;
  final PageflipBookSingleBackwardRasterBundle? rasterBundle;

  Widget? surfaceFor(PageflipBookSurfaceRole role) => surfaces[role];

  Widget get turningFrontSurface =>
      surfaces[PageflipBookSurfaceRole.turningFront]!;

  Widget get turningBackSurface =>
      surfaces[PageflipBookSurfaceRole.turningBack]!;

  Widget? get coveredCurrentSurface =>
      surfaces[PageflipBookSurfaceRole.coveredCurrent];
}
