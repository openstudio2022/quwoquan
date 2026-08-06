import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

void main() {
  testWidgets('慢提示只由一个 liveRegion 语义节点表达', (tester) async {
    await tester.pumpWidget(_host(AppRequestFeedback.page(showSlowHint: true)));

    expect(find.text(FoundationText.requestWaitSlow), findsOneWidget);
    final semantics = tester.widget<Semantics>(find.byType(Semantics).last);
    expect(semantics.properties.liveRegion, isTrue);
    expect(semantics.properties.label, FoundationText.requestWaitSlow);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('app-request-placeholder-0')),
      findsOneWidget,
    );
  });

  testWidgets('reduced-motion 下不循环播放 spinner 且布局不消失', (tester) async {
    await tester.pumpWidget(
      _host(AppRequestFeedback.section(), disableAnimations: true),
    );

    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('app-request-placeholder-0')),
      findsOneWidget,
    );
    expect(find.byType(AppRequestFeedback), findsOneWidget);
  });

  testWidgets('progress 使用确定型进度而不是无限 spinner', (tester) async {
    await tester.pumpWidget(
      _host(AppRequestFeedback.progress(progress: 0.4, stageLabel: '上传中')),
    );

    final indicator = tester.widget<CupertinoActivityIndicator>(
      find.byType(CupertinoActivityIndicator),
    );
    expect(indicator.progress, 0.4);
    expect(find.text('上传中'), findsOneWidget);
  });

  testWidgets('progress 未提供阶段时显示百分比', (tester) async {
    await tester.pumpWidget(_host(AppRequestFeedback.progress(progress: 0.4)));

    expect(find.text('40%'), findsOneWidget);
  });

  testWidgets('已有 skeleton 时可只显示慢提示而不制造第二个 indicator', (tester) async {
    await tester.pumpWidget(
      _host(AppRequestFeedback.page(showSlowHint: true, showIndicator: false)),
    );

    expect(find.text(FoundationText.requestWaitSlow), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
  });

  testWidgets('inline indicator 在 16px 媒体占位中收缩且不溢出', (tester) async {
    await tester.pumpWidget(
      _host(SizedBox.square(dimension: 16, child: AppRequestFeedback.inline())),
    );

    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Widget _host(Widget child, {bool disableAnimations = false}) {
  return CupertinoApp(
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: CupertinoPageScaffold(child: child),
    ),
  );
}
