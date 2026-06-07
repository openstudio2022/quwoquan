import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/web_page_max_width_frame.dart';

const Color _sideColor = Color(0xFF112233);
const Key _childKey = ValueKey<String>('frame-child');

Widget _host({required Size size, required PlatformCapabilities capability}) {
  return ProviderScope(
    overrides: [platformCapabilitiesProvider.overrideWithValue(capability)],
    child: MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(size: size),
        child: const WebPageMaxWidthFrame(
          sideColor: _sideColor,
          child: SizedBox(key: _childKey, height: 120, width: 4000),
        ),
      ),
    ),
  );
}

bool _hasMaxWidthConstraint(WidgetTester tester) {
  return tester
      .widgetList<ConstrainedBox>(find.byType(ConstrainedBox))
      .any(
        (box) => box.constraints.maxWidth == AppSpacing.webPageContentMaxWidth,
      );
}

bool _hasSideColorBox(WidgetTester tester) {
  return tester
      .widgetList<ColoredBox>(find.byType(ColoredBox))
      .any((box) => box.color == _sideColor);
}

void main() {
  group('WebPageMaxWidthFrame', () {
    testWidgets('宽屏 Web 能力下约束最大宽度并填充左右侧背景', (tester) async {
      await tester.pumpWidget(
        _host(size: const Size(1280, 900), capability: CapabilityProfile.web),
      );
      await tester.pump();

      expect(find.byKey(_childKey), findsOneWidget);
      expect(_hasMaxWidthConstraint(tester), isTrue);
      expect(_hasSideColorBox(tester), isTrue);
      // 中间内容区被收敛到统一 token 宽度，不再铺满整窗。
      final childWidth = tester.getSize(find.byKey(_childKey)).width;
      expect(childWidth, lessThanOrEqualTo(AppSpacing.webPageContentMaxWidth));
    });

    testWidgets('窄屏（移动宽度）下原样透传，不加最大宽度与侧栏背景', (tester) async {
      await tester.pumpWidget(
        _host(size: const Size(390, 844), capability: CapabilityProfile.web),
      );
      await tester.pump();

      expect(find.byKey(_childKey), findsOneWidget);
      expect(_hasMaxWidthConstraint(tester), isFalse);
      expect(_hasSideColorBox(tester), isFalse);
    });

    testWidgets('非宽屏能力（移动端）下即使宽窗也原样透传', (tester) async {
      await tester.pumpWidget(
        _host(
          size: const Size(1280, 900),
          capability: CapabilityProfile.mobile,
        ),
      );
      await tester.pump();

      expect(find.byKey(_childKey), findsOneWidget);
      expect(_hasMaxWidthConstraint(tester), isFalse);
      expect(_hasSideColorBox(tester), isFalse);
    });
  });
}
