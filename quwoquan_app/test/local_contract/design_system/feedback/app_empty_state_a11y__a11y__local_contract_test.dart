// 共享空态组件的 a11y 闭集断言（触控目标 / 可点目标语义标签 / 文本对比度）。
//
// a11y 断言闭集由 test-pyramid spec 声明；本样板证明组件级 a11y 基建可
// 复制。页面级（首页）断言当前存在真实存量违规，缺口登记于
// specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#open-003，
// 修复后按同一断言集落地页面级测试。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';

Widget _host({required Brightness brightness}) {
  return CupertinoApp(
    theme: CupertinoThemeData(brightness: brightness),
    home: CupertinoPageScaffold(
      child: Center(
        child: AppEmptyState(
          icon: CupertinoIcons.doc_plaintext,
          title: '暂无草稿',
          subtitle: '你的创作会自动保存到这里',
          actionLabel: '去创作',
          onAction: () {},
        ),
      ),
    ),
  );
}

void main() {
  for (final brightness in <Brightness>[Brightness.light, Brightness.dark]) {
    testWidgets('AppEmptyState ${brightness.name} 主题满足 a11y 闭集', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      await tester.pumpWidget(_host(brightness: brightness));
      await tester.pump();

      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
    });

    testWidgets('AppEmptyState ${brightness.name} 主题文本对比度达标', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();

      // 副标题已迁移到 secondaryLabelAccessible（白底约 6.3:1）。
      // CTA 主色（iOS 系统蓝，白底约 3.65:1）与 WCAG AA 的张力属于
      // 设计系统级裁决，登记于 page-horizontal-quality spec OPEN-003；
      // 本用例以无 CTA 变体守护标题与副标题的文本对比度闭集。
      await tester.pumpWidget(
        CupertinoApp(
          theme: CupertinoThemeData(brightness: brightness),
          home: const CupertinoPageScaffold(
            child: Center(
              child: AppEmptyState(
                icon: CupertinoIcons.doc_plaintext,
                title: '暂无草稿',
                subtitle: '你的创作会自动保存到这里',
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await expectLater(tester, meetsGuideline(textContrastGuideline));
      semantics.dispose();
    });
  }
}
