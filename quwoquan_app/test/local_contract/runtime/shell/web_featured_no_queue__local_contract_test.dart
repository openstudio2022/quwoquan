import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/runtime/shell/web/web_shell_test_harness.dart';
import '../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  testWidgets('Web 工具栏不再提供独立视频书入口，首页上下文保留视频书文本频道', (tester) async {
    WebShellTestHarness.suppressExpectedErrors();
    WebShellTestHarness.useWideViewport(tester);

    await tester.pumpWidget(
      WebShellTestHarness.build(
        authenticated: true,
        businessOverrides: mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
        ),
      ),
    );
    await WebShellTestHarness.enterToolbar(tester);

    expect(
      find.byKey(const ValueKey<String>('web-primary-featured')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('web-context-tab-featured')),
      findsOneWidget,
    );
    expect(find.text(DiscoveryText.homeTabFeatured), findsOneWidget);
    expect(find.text(DiscoveryText.webPcSearchHintFeatured), findsNothing);
  });
}
