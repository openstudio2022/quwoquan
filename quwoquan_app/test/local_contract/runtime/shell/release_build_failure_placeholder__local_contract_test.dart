// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-013
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/recovery/release_build_failure_placeholder.dart';

void main() {
  testWidgets('占位组件在无 Directionality/主题 ancestor 时自足渲染', (tester) async {
    // ErrorWidget.builder 可能在任意层级被调用：直接裸 pump，不包任何 App 壳。
    await tester.pumpWidget(const ReleaseBuildFailurePlaceholder());

    expect(tester.takeException(), isNull);
    expect(find.text(SearchText.recoveryInvalidContentTitle), findsOneWidget);
  });

  testWidgets('占位组件只含中性文案，不暴露技术字段或图标', (tester) async {
    await tester.pumpWidget(const ReleaseBuildFailurePlaceholder());

    expect(find.byType(Icon), findsNothing);
    final texts = tester
        .widgetList<Text>(find.byType(Text))
        .map((text) => text.data ?? '')
        .join('\n');
    expect(texts, SearchText.recoveryInvalidContentTitle);
    expect(texts.contains('Exception'), isFalse);
    expect(texts.contains('Stack'), isFalse);
    expect(RegExp('[A-Z]+\\.[A-Z]+\\.').hasMatch(texts), isFalse);
  });
}
