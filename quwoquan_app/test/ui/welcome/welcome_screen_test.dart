import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

/// 欢迎页 widget 测试（T2）：覆盖主动式 AI Native slogan 升级后的双层口吻
/// 与花瓣呼吸光心，并断言旧文案彻底无残留。
///
/// 设计要点（与 specs/00_PRODUCT_CONCEPT_SYSTEM.md §2.2 对齐）：
/// - 中央主 slogan：品牌口吻「遇见同趣，绽放热爱」
/// - 底部小趣寄语：第一人称口吻「✨ 小趣 / 专注你的热爱，剩下的交给我」
void main() {
  Widget wrap({VoidCallback? onFinish, WelcomeLoginPromptConfig? loginPrompt}) {
    return CupertinoApp(
      home: WelcomeScreen(
        onFinish: onFinish ?? () {},
        loginPrompt: loginPrompt,
      ),
    );
  }

  /// 推进足够时长让欢迎页短动画完成并自动进入首页。
  ///
  /// `runSequence()` 内部交替使用 `Future.delayed` 和 `AnimationController.forward()`，
  /// 单次大跨度 `pump(Duration(seconds: N))` 无法让逐段串行的 await 正确恢复——
  /// 必须按 frame 节奏多次推进，让每段 microtask/动画都拿到调度机会。
  Future<void> settle(WidgetTester tester) async {
    // 总计 ~3s，覆盖欢迎页短动画链路并留出充足 buffer。
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 50));
    }
  }

  Future<void> pumpUntilLoginPrompt(WidgetTester tester) async {
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find
          .text(UITextConstants.welcomeLoginPromptTitle)
          .evaluate()
          .isNotEmpty) {
        break;
      }
    }
  }

  group('WelcomeScreen · 主动式 AI Native 升级', () {
    testWidgets('首帧即展示可识别品牌内容，花瓣不再从纯空状态开始', (tester) async {
      await tester.pumpWidget(wrap());

      expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
      expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);

      final flower = tester.widget<WelcomeFlowerMark>(
        find.byType(WelcomeFlowerMark),
      );
      expect(flower.petalProgresses, hasLength(8));
      expect(flower.petalProgresses.every((value) => value > 0.7), isTrue);

      await settle(tester);
    });

    testWidgets('中央渲染新主 slogan「遇见同趣，绽放热爱」', (tester) async {
      await tester.pumpWidget(wrap());
      await tester.pump();

      expect(UITextConstants.welcomeMainSlogan, '遇见同趣，绽放热爱');
      expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);

      await settle(tester);
    });

    testWidgets('花瓣图标使用曲线花瓣，花蕊由根部渐变自然叠出', (tester) async {
      await tester.pumpWidget(wrap());
      await tester.pump();

      expect(AppSpacing.welcomePetalWidth, 52);
      expect(AppSpacing.welcomePetalHeight, 94);
      expect(AppSpacing.welcomePetalRadialOffset, 54);

      // 欢迎页与应用图标必须共用同一个花瓣 painter，避免两套视觉漂移。
      expect(find.byType(WelcomeFlowerMark), findsOneWidget);
      expect(WelcomeFlowerMarkPainter.petalCount, 8);
      expect(WelcomeFlowerMarkPainter.flowerVisualDiameter, 202);

      // 不应再单独绘制中心底色/光圈；花蕊由 8 片花瓣根部渐变叠加形成。
      final squareLayers = tester.widgetList<SizedBox>(find.byType(SizedBox));
      bool hasSquare(double dimension) => squareLayers.any(
        (s) => s.width == dimension && s.height == dimension,
      );
      expect(hasSquare(48), isFalse);
      expect(hasSquare(88), isFalse);
      expect(hasSquare(56), isFalse);
      expect(hasSquare(24), isFalse);

      await settle(tester);
    });

    testWidgets('底部小趣注脚：单行内联渲染 sparkle + 「小趣」 + 寄语', (tester) async {
      await tester.pumpWidget(wrap());
      await tester.pump();

      // 文案常量正确（防止后续误改回前一版）
      expect(UITextConstants.assistantWhisperSignature, '小趣');
      expect(UITextConstants.assistantWhisperLine, '专注你的热爱，剩下的交给我');

      // 单行注脚使用 Text.rich，文字内容会被合并到一个 RichText/Text 节点中
      // 因此用 findsWidgets（>=1）+ richTextContains 断言文案被完整渲染
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is RichText &&
              w.text.toPlainText().contains(
                UITextConstants.assistantWhisperSignature,
              ) &&
              w.text.toPlainText().contains(
                UITextConstants.assistantWhisperLine,
              ),
        ),
        findsOneWidget,
      );

      // 主 slogan 末端不再放 sparkles；底部注脚内只剩 1 个
      expect(find.byIcon(CupertinoIcons.sparkles), findsOneWidget);

      await settle(tester);
    });

    testWidgets('小趣注脚整组居中对齐（与上方版面节奏一致）', (tester) async {
      await tester.pumpWidget(wrap());
      await tester.pump();

      // 单行注脚由 Text.rich 渲染，textAlign 必须为 center
      final richText = tester
          .widgetList<RichText>(find.byType(RichText))
          .firstWhere(
            (w) => w.text.toPlainText().contains(
              UITextConstants.assistantWhisperLine,
            ),
          );
      expect(richText.textAlign, TextAlign.center);

      // 整组不再左对齐：不应存在直接以 Alignment.centerLeft 包裹寄语文本的 Align
      final sparkleIcon = find.byIcon(CupertinoIcons.sparkles);
      final leftAligns = find
          .ancestor(of: sparkleIcon, matching: find.byType(Align))
          .evaluate()
          .map((e) => e.widget as Align)
          .where((a) => a.alignment == Alignment.centerLeft);
      expect(leftAligns, isEmpty);

      await settle(tester);
    });

    testWidgets('旧文案（subtitle/footer/旧 main slogan）彻底无残留', (tester) async {
      await tester.pumpWidget(wrap());
      await tester.pump();

      expect(find.text('以兴趣为半径，画出我们的交集'), findsNothing);
      expect(find.text('小趣私人助手 · 与你相伴'), findsNothing);
      expect(find.text('专注你的热爱，其余交给小趣'), findsNothing);
      expect(find.text('同趣相连，世界更近'), findsNothing);
      expect(find.text('遇见同趣，世界更近'), findsNothing);
      expect(find.text('专注你的兴趣，剩下的交给我'), findsNothing);

      await settle(tester);
    });

    testWidgets('短动画结束后直接调用 onFinish，且不再显示倒计时数字', (tester) async {
      var finishedCount = 0;
      await tester.pumpWidget(wrap(onFinish: () => finishedCount++));

      await settle(tester);
      expect(finishedCount, 1);
      expect(find.text('3'), findsNothing);
      expect(find.text('2'), findsNothing);
      expect(find.text('1'), findsNothing);
    });

    testWidgets('未登录时在欢迎页内展示登录与先不登录倒计时', (tester) async {
      var loginCount = 0;
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () => loginCount++,
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);

      expect(
        find.text(UITextConstants.welcomeLoginPromptTitle),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.login), findsOneWidget);
      expect(find.textContaining('先不登录'), findsOneWidget);

      await tester.tap(find.text(UITextConstants.login));
      await tester.pump();

      expect(loginCount, 1);
      expect(guestCount, 0);
    });

    testWidgets('点击先不登录会继续进入 App', (tester) async {
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () {},
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);
      await tester.tap(find.textContaining('先不登录'));
      await tester.pump();

      expect(guestCount, 1);
    });

    testWidgets('倒计时结束后自动按先不登录进入 App', (tester) async {
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () {},
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(seconds: 1));
      }

      expect(guestCount, 1);
    });

    testWidgets('未登录时在欢迎页内展示登录与先不登录倒计时', (tester) async {
      var loginCount = 0;
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () => loginCount++,
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);

      expect(
        find.text(UITextConstants.welcomeLoginPromptTitle),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.login), findsOneWidget);
      expect(find.textContaining('先不登录'), findsOneWidget);

      await tester.tap(find.text(UITextConstants.login));
      await tester.pump();

      expect(loginCount, 1);
      expect(guestCount, 0);
    });

    testWidgets('点击先不登录会继续进入 App', (tester) async {
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () {},
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);
      await tester.tap(find.textContaining('先不登录'));
      await tester.pump();

      expect(guestCount, 1);
    });

    testWidgets('倒计时结束后自动按先不登录进入 App', (tester) async {
      var guestCount = 0;
      await tester.pumpWidget(
        wrap(
          loginPrompt: WelcomeLoginPromptConfig(
            title: UITextConstants.welcomeLoginPromptTitle,
            subtitle: UITextConstants.welcomeLoginPromptSubtitle,
            onLogin: () {},
            onContinueAsGuest: () => guestCount++,
          ),
        ),
      );

      await pumpUntilLoginPrompt(tester);
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(seconds: 1));
      }

      expect(guestCount, 1);
    });
  });
}
