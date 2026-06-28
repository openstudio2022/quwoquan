import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/legal_document_page.dart';

void main() {
  Widget host({required LegalDocumentAvailabilityProbe availabilityProbe}) {
    return ProviderScope(
      child: CupertinoApp(
        home: LegalDocumentPage(
          title: UITextConstants.userAgreement,
          url: 'https://alpha-api.quwoquan-env.test:17000/legal/user-agreement',
          availabilityProbe: availabilityProbe,
          webViewBuilder: (_, _) => const Text('legal body'),
        ),
      ),
    );
  }

  testWidgets(
    'shows native semantic error when legal document is unavailable',
    (tester) async {
      await tester.pumpWidget(host(availabilityProbe: (_) async => false));
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.legalUnavailableTitle), findsOneWidget);
      expect(
        find.text(UITextConstants.legalUnavailableMessage),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.tryAgain), findsOneWidget);
      expect(find.text(UITextConstants.back), findsWidgets);
      expect(find.text('api mock route is not ready'), findsNothing);
      expect(find.text('Error response'), findsNothing);
    },
  );

  testWidgets('retry re-runs legal document preflight without blocking page', (
    tester,
  ) async {
    var probeCount = 0;
    await tester.pumpWidget(
      host(
        availabilityProbe: (_) async {
          probeCount += 1;
          return false;
        },
      ),
    );
    await tester.pumpAndSettle();
    expect(probeCount, 1);

    await tester.tap(find.text(UITextConstants.tryAgain));
    await tester.pumpAndSettle();

    expect(probeCount, 2);
    expect(find.text(UITextConstants.legalUnavailableTitle), findsOneWidget);
  });
}
