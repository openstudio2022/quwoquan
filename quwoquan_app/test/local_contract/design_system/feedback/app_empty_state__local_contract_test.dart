// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#open-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-016.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-016.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-016.t3
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-016.t4
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-016.t5

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

Widget _host(Widget child) => CupertinoApp(home: Center(child: child));

void main() {
  group('AppEmptyState — 共享空态合约', () {
    testWidgets('渲染 icon + 标题；副标题与动作缺省时不渲染', (tester) async {
      await tester.pumpWidget(
        _host(
          const AppEmptyState(icon: CupertinoIcons.flag, title: '暂无举报'),
        ),
      );
      expect(find.byIcon(CupertinoIcons.flag), findsOneWidget);
      expect(find.text('暂无举报'), findsOneWidget);
      expect(find.byType(CupertinoButton), findsNothing);
    });

    testWidgets('副标题与主动作成对出现且动作可点', (tester) async {
      var tapped = 0;
      await tester.pumpWidget(
        _host(
          AppEmptyState(
            icon: CupertinoIcons.doc_plaintext,
            title: '暂无草稿',
            subtitle: '你的创作会自动保存到这里',
            actionLabel: '去创作',
            onAction: () => tapped += 1,
          ),
        ),
      );
      expect(find.text('你的创作会自动保存到这里'), findsOneWidget);
      await tester.tap(find.text('去创作'));
      expect(tapped, 1);
    });

    testWidgets('只给 actionLabel 不给回调时不渲染动作（成对约束）', (tester) async {
      await tester.pumpWidget(
        _host(
          const AppEmptyState(
            icon: CupertinoIcons.flag,
            title: '空',
            actionLabel: '动作',
          ),
        ),
      );
      expect(find.byType(CupertinoButton), findsNothing);
    });

    testWidgets('空态不出现重试文案、错误语气或错误码技术字段', (tester) async {
      await tester.pumpWidget(
        _host(
          AppEmptyState(
            icon: CupertinoIcons.doc_plaintext,
            title: MediaText.noDraft,
            subtitle: CreationText.localDraftEmptySubtitle,
            actionLabel: ProfileText.profileShareReceivedEmptyAction,
            onAction: () {},
          ),
        ),
      );

      final texts = tester
          .widgetList<Text>(find.byType(Text))
          .map((text) => text.data ?? '')
          .join('\n');
      // 空态是健康终态：不得出现恢复组重试文案或旧式「重试」语气。
      expect(texts.contains(ContentText.tryAgain), isFalse);
      expect(texts.contains(SearchText.reload), isFalse);
      expect(texts.contains(FoundationText.retry), isFalse);
      expect(texts.contains(FoundationText.loadFailed), isFalse);
      // 不泄漏 MODULE.KIND.reason 形态错误码等技术字段。
      expect(RegExp('[A-Z]+\\.[A-Z]+\\.').hasMatch(texts), isFalse);
    });

    testWidgets('失败场景不进入空态组件：错误载体与空态载体物理分离', (tester) async {
      // AppEmptyState 的公开 API 无失败/错误/重试入口（仅
      // icon/title/subtitle/actionLabel/onAction）；失败场景由
      // AppPageErrorState 独立承载，空态渲染面不存在错误载体。
      await tester.pumpWidget(
        _host(
          const AppEmptyState(icon: CupertinoIcons.flag, title: '暂无举报'),
        ),
      );
      expect(find.byType(AppPageErrorState), findsNothing);
      expect(find.byType(AppEmptyState), findsOneWidget);
    });

    testWidgets('副标题在浅色底满足 WCAG AA 4.5:1 对比度', (tester) async {
      await tester.pumpWidget(
        _host(
          const AppEmptyState(
            icon: CupertinoIcons.doc_plaintext,
            title: '空',
            subtitle: '说明文字',
          ),
        ),
      );

      final subtitle = tester.widget<Text>(find.text('说明文字'));
      final context = tester.element(find.text('说明文字'));
      final foreground = CupertinoDynamicColor.resolve(
        subtitle.style!.color!,
        context,
      );
      final background = CupertinoDynamicColor.resolve(
        CupertinoColors.systemBackground,
        context,
      );
      final lighter = foreground.computeLuminance() >
              background.computeLuminance()
          ? foreground
          : background;
      final darker = identical(lighter, foreground) ? background : foreground;
      final contrast = (lighter.computeLuminance() + 0.05) /
          (darker.computeLuminance() + 0.05);
      expect(contrast, greaterThanOrEqualTo(4.5));
    });

    testWidgets('dense 密度：次级小字、无图标、紧凑留白（sheet 区块轻空态）', (tester) async {
      await tester.pumpWidget(
        _host(
          const AppEmptyState(
            icon: CupertinoIcons.doc_plaintext,
            title: '还没有内容',
            density: AppEmptyStateDensity.dense,
          ),
        ),
      );

      // dense 形态不渲染图标，标题降为次级小字。
      expect(find.byIcon(CupertinoIcons.doc_plaintext), findsNothing);
      final title = tester.widget<Text>(find.text('还没有内容'));
      final context = tester.element(find.text('还没有内容'));
      expect(title.style!.fontSize, lessThan(15));
      expect(title.style!.fontWeight, isNot(FontWeight.w600));
      // 次级色仍满足正文级对比要求（复用 secondaryLabelAccessible token）。
      final foreground = CupertinoDynamicColor.resolve(
        title.style!.color!,
        context,
      );
      final background = CupertinoDynamicColor.resolve(
        CupertinoColors.systemBackground,
        context,
      );
      final lighter =
          foreground.computeLuminance() > background.computeLuminance()
          ? foreground
          : background;
      final darker = identical(lighter, foreground) ? background : foreground;
      final contrast =
          (lighter.computeLuminance() + 0.05) /
          (darker.computeLuminance() + 0.05);
      expect(contrast, greaterThanOrEqualTo(4.5));
    });

    testWidgets('dense 密度双模式：标题色随深浅主题变化', (tester) async {
      Future<Color> pumpAndRead(Brightness brightness) async {
        await tester.pumpWidget(
          CupertinoApp(
            theme: CupertinoThemeData(brightness: brightness),
            home: const Center(
              child: AppEmptyState(
                title: '还没有内容',
                density: AppEmptyStateDensity.dense,
              ),
            ),
          ),
        );
        final title = tester.widget<Text>(find.text('还没有内容'));
        return CupertinoDynamicColor.resolve(
          title.style!.color!,
          tester.element(find.text('还没有内容')),
        );
      }

      final light = await pumpAndRead(Brightness.light);
      final dark = await pumpAndRead(Brightness.dark);
      expect(light, isNot(dark));
    });
  });
}
