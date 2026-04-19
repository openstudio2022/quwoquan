import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

void main() {
  test('forward bottom projection band stays on the fold-left side', () {
    const pageRect = Rect.fromLTWH(16, 64, 398, 553);
    final frame = const ArticlePageCurlMeshBuilder().build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: const Offset(92, 520),
      progress: 0.74,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
    );

    final foldX = pageRect.left + pageRect.width * frame.foldXNormalized;
    final band = resolveArticlePageBottomProjectionBand(
      pageRect,
      frame.foldXNormalized,
    );

    expect(
      band.left,
      lessThan(foldX),
      reason: 'projection band must extend to the left of the fold',
    );
    expect(
      band.right,
      lessThanOrEqualTo(foldX),
      reason: 'projection band should not cross to the right side of the fold',
    );
    expect(
      band.center.dx,
      lessThan(foldX),
      reason: 'projection band should be biased toward the left side',
    );
    expect(
      band.width / pageRect.width,
      closeTo(0.16, 0.02),
      reason: 'the band spans only the left-side highlight width',
    );
  });
}
