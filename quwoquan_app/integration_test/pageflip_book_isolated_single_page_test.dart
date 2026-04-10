import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/pageflip_book.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'hidden isolated entry uses mesh renderer for backward and forward',
    (tester) async {
      await tester.pumpWidget(const PageflipBookIsolatedDiagnosticsApp());
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();

      final stageFinder = find.byKey(PageflipBookIsolatedTestKeys.stage);
      expect(stageFinder, findsOneWidget);

      final stageRect = tester.getRect(stageFinder);
      final backwardStart = Offset(
        stageRect.center.dx - 110,
        stageRect.center.dy + 120,
      );
      final backwardSteps = <Offset>[
        backwardStart.translate(40, 0),
        backwardStart.translate(90, 0),
        backwardStart.translate(150, 0),
      ];

      final backwardGesture = await tester.startGesture(backwardStart);
      await tester.pump(const Duration(milliseconds: 48));
      for (final step in backwardSteps) {
        await backwardGesture.moveTo(step);
        await tester.pump(const Duration(milliseconds: 48));
        expect(find.byType(PageflipBookIsolatedMeshRenderer), findsOneWidget);
      }
      await backwardGesture.up();
      await tester.pumpAndSettle();
      await tester.tapAt(Offset(stageRect.left + 40, stageRect.center.dy));
      await tester.pumpAndSettle();
      expect(find.text('前言'), findsOneWidget);

      final forwardStart = Offset(
        stageRect.center.dx + 120,
        stageRect.center.dy + 120,
      );
      final forwardSteps = <Offset>[
        forwardStart.translate(-40, 0),
        forwardStart.translate(-90, 0),
        forwardStart.translate(-150, 0),
      ];

      final forwardGesture = await tester.startGesture(forwardStart);
      await tester.pump(const Duration(milliseconds: 48));
      for (final step in forwardSteps) {
        await forwardGesture.moveTo(step);
        await tester.pump(const Duration(milliseconds: 48));
        expect(find.byType(PageflipBookIsolatedMeshRenderer), findsOneWidget);
      }
      await forwardGesture.up();
      await tester.pumpAndSettle();
      await tester.tapAt(Offset(stageRect.right - 40, stageRect.center.dy));
      await tester.pumpAndSettle();
      expect(find.text('第一章'), findsOneWidget);
    },
  );
}
