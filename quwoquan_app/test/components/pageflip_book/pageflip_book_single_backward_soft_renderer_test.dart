import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';

void main() {
  const pageRect = Rect.fromLTWH(12, 16, 180, 260);
  const pageSize = Size(180, 260);
  const frontKey = ValueKey<String>('turning_front');
  const backKey = ValueKey<String>('turning_back');
  const coveredKey = ValueKey<String>('covered_current');

  PageflipBookSingleBackwardSoftScene buildScene(
    PageflipBookSingleBackwardSoftFrame frame,
  ) {
    return PageflipBookSingleBackwardSoftScene(
      pageRect: pageRect,
      pageSize: pageSize,
      sheetBinding: const PageflipBookSheetBinding(
        direction: PageflipBookDirection.backward,
        rectoPageIndex: 1,
        versoPageIndex: 2,
        bottomPageIndex: 2,
      ),
      surfaces: <PageflipBookSurfaceRole, Widget>{
        PageflipBookSurfaceRole.coveredCurrent: Container(key: coveredKey),
        PageflipBookSurfaceRole.turningFront: Container(key: frontKey),
        PageflipBookSurfaceRole.turningBack: Container(key: backKey),
      },
      frame: frame,
      shadowColor: const Color(0xCC000000),
      highlightColor: const Color(0x33FFFFFF),
      paperTintColor: const Color(0xFFF5F1E8),
    );
  }

  Widget buildHarness(PageflipBookSingleBackwardSoftFrame frame) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: SizedBox(
        width: 240,
        height: 320,
        child: Stack(
          children: <Widget>[
            PageflipBookSingleBackwardSoftRenderer(scene: buildScene(frame)),
          ],
        ),
      ),
    );
  }

  testWidgets('renderer covers emerge unroll and settle phases', (tester) async {
    await tester.pumpWidget(
      buildHarness(
        const PageflipBookSingleBackwardSoftFrame(
          phase: PageflipBookSingleBackwardSoftPhase.emerge,
          emergenceProgress: 0.56,
          unrollProgress: 0.0,
          settleProgress: 0.0,
          coveredWidthNormalized: 0.16,
          laidDownWidthNormalized: 0.0,
          curlWidthNormalized: 0.16,
          rectoRevealWidthNormalized: 0.04,
          curlPivotNormalized: 0.08,
          edgeLift: 0.24,
          liftDirection: -1,
          shadowAxisNormalized: 0.12,
          commitProgress: 0.16,
        ),
      ),
    );

    expect(find.byType(PageflipBookSingleBackwardSoftRenderer), findsOneWidget);
    expect(find.byKey(coveredKey), findsOneWidget);
    expect(find.byKey(backKey), findsWidgets);
    expect(find.byKey(frontKey), findsWidgets);
    expect(find.byType(Transform), findsWidgets);

    await tester.pumpWidget(
      buildHarness(
        const PageflipBookSingleBackwardSoftFrame(
          phase: PageflipBookSingleBackwardSoftPhase.unroll,
          emergenceProgress: 1.0,
          unrollProgress: 0.62,
          settleProgress: 0.0,
          coveredWidthNormalized: 0.7,
          laidDownWidthNormalized: 0.56,
          curlWidthNormalized: 0.14,
          rectoRevealWidthNormalized: 0.05,
          curlPivotNormalized: 0.63,
          edgeLift: 0.18,
          liftDirection: 1,
          shadowAxisNormalized: 0.68,
          commitProgress: 0.7,
        ),
      ),
    );

    expect(find.byKey(coveredKey), findsOneWidget);
    expect(find.byKey(backKey), findsWidgets);
    expect(find.byKey(frontKey), findsWidgets);
    expect(find.byType(Transform), findsWidgets);

    await tester.pumpWidget(
      buildHarness(
        const PageflipBookSingleBackwardSoftFrame(
          phase: PageflipBookSingleBackwardSoftPhase.settle,
          emergenceProgress: 1.0,
          unrollProgress: 1.0,
          settleProgress: 1.0,
          coveredWidthNormalized: 1.0,
          laidDownWidthNormalized: 1.0,
          curlWidthNormalized: 0.0,
          rectoRevealWidthNormalized: 0.0,
          curlPivotNormalized: 1.0,
          edgeLift: 0.08,
          liftDirection: 1,
          shadowAxisNormalized: 1.0,
          commitProgress: 1.0,
        ),
      ),
    );

    expect(find.byKey(frontKey), findsOneWidget);
    expect(find.byKey(backKey), findsNothing);
    expect(find.byKey(coveredKey), findsOneWidget);
    expect(find.byType(Transform), findsWidgets);
  });
}
