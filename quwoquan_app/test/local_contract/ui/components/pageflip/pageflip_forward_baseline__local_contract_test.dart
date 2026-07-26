import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/geometry.dart';
import 'package:quwoquan_app/components/pageflip/types.dart';

void main() {
  group('Forward pageflip baseline', () {
    test('keeps canonical forward frame bundle stable', () {
      final calculation = StPageFlipCalculation(
        direction: StPageFlipDirection.forward,
        corner: StPageFlipCorner.top,
        pageWidth: 400,
        pageHeight: 600,
      );

      expect(calculation.calc(const Offset(120, 80)), isTrue);
      final canonical = calculation.getCanonicalFoldGeometry();
      expect(canonical, isNotNull);
      expect(canonical!.direction, StPageFlipDirection.forward);
      expect(calculation.getAngle(), lessThan(0));
      expect(calculation.getActiveCorner(), calculation.getRect().topLeft);
      expect(calculation.getBottomPagePosition(), Offset.zero);
      expect(calculation.getFlippingClipArea().length, greaterThanOrEqualTo(3));
      expect(calculation.getBottomClipArea().length, greaterThanOrEqualTo(3));
      expect(
        canonical.foldLine.$1.dy,
        lessThanOrEqualTo(canonical.foldLine.$2.dy),
      );
      expect(canonical.freeEdgeLine, (
        calculation.getRect().topRight,
        calculation.getRect().bottomRight,
      ));
    });

    test(
      'host keeps forward and BACK on the shared soft projection pipeline',
      () {
        final source = File(
          'lib/ui/content/article_reader/pageflip/host/'
          'article_read_only_book_deck_diagnostic_geometry.dart',
        ).readAsStringSync();
        final dynamicGeometryStart = source.indexOf(
          'SoftPageLayerGeometry? _resolveDynamicLayerGeometry',
        );
        expect(dynamicGeometryStart, isNonNegative);
        final dynamicGeometryEnd = source.indexOf(
          '_BackwardDiagnosticGeometry? _resolveBackwardDiagnosticGeometry',
          dynamicGeometryStart,
        );
        expect(dynamicGeometryEnd, greaterThan(dynamicGeometryStart));
        final dynamicGeometrySource = source.substring(
          dynamicGeometryStart,
          dynamicGeometryEnd,
        );

        expect(
          dynamicGeometrySource,
          contains('visualGeometryDirection'),
          reason:
              'BACK may use forward-isomorphic frame geometry, but the host must '
              'still feed the same soft projection resolver instead of cloning '
              'a second projection path.',
        );
        expect(
          dynamicGeometrySource,
          contains('convertBookPointToViewport('),
          reason:
              'forward projection must stay anchored in StPageFlip geometry.',
        );
        expect(
          dynamicGeometrySource,
          isNot(contains('resolveBackwardSoftPageGeometry(')),
        );
      },
    );
  });
}
