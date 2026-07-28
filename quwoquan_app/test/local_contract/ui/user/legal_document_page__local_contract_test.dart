import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/remote/user/legal_document_remote.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/legal_document_page.dart';

void main() {
  Widget host({required LegalDocumentAvailabilityProbe availabilityProbe}) {
    return ProviderScope(
      child: CupertinoApp(
        home: LegalDocumentPage(
          title: FoundationText.userAgreement,
          url: 'https://api.alpha.quwoquan.com:17000/legal/user-agreement',
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

      expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
      expect(find.text(SearchText.recoveryReloadLaterMessage), findsOneWidget);
      expect(find.text(SearchText.reload), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
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

    await tester.tap(find.text(SearchText.reload));
    await tester.pumpAndSettle();

    expect(probeCount, 2);
    expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
  });

  test(
    'decodes UTF-8 legal document bytes without relying on charset',
    () async {
      final html = await defaultLegalDocumentHtmlLoader(
        Uri.parse(
          'https://api.alpha.quwoquan.com:17000/legal/user-agreement',
        ),
        client: _FakeHttpClient(
          (_) async => http.Response.bytes(
            utf8.encode('<html><body><h1>趣我圈用户协议</h1></body></html>'),
            200,
            headers: const <String, String>{'content-type': 'text/html'},
          ),
        ),
      );

      expect(html, contains('趣我圈用户协议'));
    },
  );
}

class _FakeHttpClient extends http.BaseClient {
  _FakeHttpClient(this._handler);

  final Future<http.Response> Function(http.BaseRequest request) _handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await _handler(request);
    return http.StreamedResponse(
      Stream<List<int>>.value(response.bodyBytes),
      response.statusCode,
      contentLength: response.contentLength,
      request: request,
      headers: response.headers,
      isRedirect: response.isRedirect,
      persistentConnection: response.persistentConnection,
      reasonPhrase: response.reasonPhrase,
    );
  }
}
