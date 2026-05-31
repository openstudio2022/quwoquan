import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_sheet_partition.dart';

void main() {
  group('BackwardCanonicalSheetFaces', () {
    test('keeps recto and verso alive from the same fold/free source', () {
      const pageSize = Size(400, 600);
      final faces = resolveBackwardCanonicalSheetFaces(
        const BackwardCanonicalSheetInput(
          pageSize: pageSize,
          sheetLocalFoldLine: (Offset(180, 0), Offset(180, 600)),
          sheetLocalFreeEdgeLine: (Offset(260, 0), Offset(260, 600)),
          sheetLocalPolygon: <Offset>[
            Offset.zero,
            Offset(400, 0),
            Offset(400, 600),
            Offset(0, 600),
          ],
          sheetAreaPolygon: <Offset>[
            Offset.zero,
            Offset(400, 0),
            Offset(400, 600),
            Offset(0, 600),
          ],
          currentResidualPagePolygon: <Offset>[],
        ),
      );

      expect(faces.failureReason, BackwardCanonicalSheetFailureReason.none);
      expect(faces.rectoFailureReason, BackwardCanonicalFaceFailureReason.none);
      expect(faces.versoFailureReason, BackwardCanonicalFaceFailureReason.none);
      expect(
        faces.previousFrontRectoLocalPolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        faces.previousBackVersoLocalPolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(faces.rectoArea, greaterThan(1000));
      expect(faces.versoArea, greaterThan(1000));
      expect(
        faces.rectoVersoOverlap,
        lessThan(1),
        reason: 'recto/front and verso/back must be complementary faces.',
      );
    });

    test(
      'keeps zero-angle faces complementary without a synthetic limit band',
      () {
        const pageSize = Size(400, 600);
        final faces = resolveBackwardCanonicalSheetFaces(
          const BackwardCanonicalSheetInput(
            pageSize: pageSize,
            sheetLocalFoldLine: (Offset(240, 0), Offset(240, 600)),
            sheetLocalFreeEdgeLine: (Offset(241, 0), Offset(241, 600)),
            sheetLocalPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            sheetAreaPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            currentResidualPagePolygon: <Offset>[],
          ),
        );

        final frontBounds = polygonBounds(faces.previousFrontRectoLocalPolygon);
        final backBounds = polygonBounds(faces.previousBackVersoLocalPolygon);
        expect(faces.failureReason, BackwardCanonicalSheetFailureReason.none);
        expect(
          faces.rectoFailureReason,
          BackwardCanonicalFaceFailureReason.none,
        );
        expect(
          faces.versoFailureReason,
          BackwardCanonicalFaceFailureReason.none,
        );
        expect(frontBounds, isNotNull);
        expect(backBounds, isNotNull);
        expect(
          frontBounds!.width,
          greaterThan(pageSize.width * 0.25),
          reason: 'zero-angle BACK must keep previous-front recto visible.',
        );
        expect(
          backBounds!.width,
          lessThan(pageSize.width * 0.75),
          reason: 'zero-angle BACK must not treat the whole sheet as verso.',
        );
        expect(
          backBounds!.width,
          lessThan(pageSize.width * 0.88),
          reason: 'canonical BACK verso must not own the whole sheet.',
        );
      },
    );

    test(
      'reports missing fold/free inputs instead of drawing a one-sided sheet',
      () {
        const pageSize = Size(400, 600);
        final missingFold = resolveBackwardCanonicalSheetFaces(
          const BackwardCanonicalSheetInput(
            pageSize: pageSize,
            sheetLocalFoldLine: null,
            sheetLocalFreeEdgeLine: (Offset(260, 0), Offset(260, 600)),
            sheetLocalPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            sheetAreaPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            currentResidualPagePolygon: <Offset>[],
          ),
        );
        final missingFree = resolveBackwardCanonicalSheetFaces(
          const BackwardCanonicalSheetInput(
            pageSize: pageSize,
            sheetLocalFoldLine: (Offset(180, 0), Offset(180, 600)),
            sheetLocalFreeEdgeLine: null,
            sheetLocalPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            sheetAreaPolygon: <Offset>[
              Offset.zero,
              Offset(400, 0),
              Offset(400, 600),
              Offset(0, 600),
            ],
            currentResidualPagePolygon: <Offset>[],
          ),
        );

        expect(
          missingFold.failureReason,
          BackwardCanonicalSheetFailureReason.foldMissing,
        );
        expect(
          missingFree.failureReason,
          BackwardCanonicalSheetFailureReason.freeEdgeMissing,
        );
        expect(missingFold.previousFrontRectoLocalPolygon, isEmpty);
        expect(missingFree.previousBackVersoLocalPolygon, isEmpty);
      },
    );

    test('keeps low-angle BACK edge without vertical budget clipping', () {
      const pageSize = Size(376, 522.2);
      final faces = resolveBackwardCanonicalSheetFaces(
        const BackwardCanonicalSheetInput(
          pageSize: pageSize,
          sheetLocalFoldLine: (Offset(146.9, 64.4), Offset(-13.2, 564.4)),
          sheetLocalFreeEdgeLine: (Offset(344.4, 150.8), Offset(135.0, 629.2)),
          sheetLocalPolygon: <Offset>[
            Offset.zero,
            Offset(147.2, 64.5),
            Offset(-12.7, 564.5),
            Offset(-209.4, 478.4),
          ],
          sheetAreaPolygon: <Offset>[
            Offset.zero,
            Offset(147.2, 64.5),
            Offset(-12.7, 564.5),
            Offset(-209.4, 478.4),
          ],
          currentResidualPagePolygon: <Offset>[],
        ),
      );

      final frontBounds = polygonBounds(faces.previousFrontRectoLocalPolygon);
      final backBounds = polygonBounds(faces.previousBackVersoLocalPolygon);
      final sheetBounds = polygonBounds(faces.sheetLocalPolygon);
      expect(faces.rectoFailureReason, BackwardCanonicalFaceFailureReason.none);
      expect(faces.versoFailureReason, BackwardCanonicalFaceFailureReason.none);
      expect(frontBounds, isNotNull);
      expect(backBounds, isNotNull);
      expect(sheetBounds, isNotNull);
      expect(
        backBounds!.width,
        lessThan(sheetBounds!.width * 0.92),
        reason:
            'low-angle verso/back must stay complementary to recto/front, not '
            'fall back to the whole sheet.',
      );
      expect(
        frontBounds!.width,
        greaterThan(sheetBounds!.width * 0.18),
        reason: 'previous-front recto must remain visible in low-angle BACK.',
      );
      expect(
        backBounds.width,
        lessThan(sheetBounds.width * 0.88),
        reason: 'previous-back verso must not equal the full moving sheet.',
      );
    });

    test('rejects screenshot regression: recto line and full-sheet verso', () {
      const pageSize = Size(376, 522.2);
      final faces = resolveBackwardCanonicalSheetFaces(
        const BackwardCanonicalSheetInput(
          pageSize: pageSize,
          sheetLocalFoldLine: (Offset(146.9, 64.4), Offset(-13.2, 564.4)),
          sheetLocalFreeEdgeLine: (Offset(344.4, 150.8), Offset(135.0, 629.2)),
          sheetLocalPolygon: <Offset>[
            Offset.zero,
            Offset(147.2, 64.5),
            Offset(-12.7, 564.5),
            Offset(-209.4, 478.4),
          ],
          sheetAreaPolygon: <Offset>[
            Offset.zero,
            Offset(147.2, 64.5),
            Offset(-12.7, 564.5),
            Offset(-209.4, 478.4),
          ],
          currentResidualPagePolygon: <Offset>[],
        ),
      );

      final frontBounds = polygonBounds(faces.previousFrontRectoLocalPolygon);
      final backBounds = polygonBounds(faces.previousBackVersoLocalPolygon);
      final sheetBounds = polygonBounds(faces.sheetLocalPolygon);
      expect(frontBounds, isNotNull);
      expect(backBounds, isNotNull);
      expect(sheetBounds, isNotNull);
      expect(
        frontBounds!.width,
        greaterThan(sheetBounds!.width * 0.18),
        reason: 'screenshot regression had sheetRectoFront as a narrow line.',
      );
      expect(
        backBounds!.width,
        lessThan(sheetBounds.width * 0.88),
        reason: 'screenshot regression had sheetVersoBack as the full sheet.',
      );
    });
  });
}
