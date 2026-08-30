// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018.t3
import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_caption_widgets.dart';

Widget _host(Widget child, {double width = 320}) => CupertinoApp(
  home: CupertinoPageScaffold(
    child: Center(child: SizedBox(width: width, child: child)),
  ),
);

Finder _captionRichText() => find.byWidgetPredicate(
  (widget) =>
      widget is RichText &&
      widget.text.toPlainText().contains(CommunityText.fullText),
);

TextSpan? _findSpanWithText(InlineSpan root, String text) {
  TextSpan? found;
  root.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      found = span;
      return false;
    }
    return true;
  });
  return found;
}

void main() {
  Future<void> pumpCollapsed(
    WidgetTester tester,
    String caption, {
    double width = 320,
  }) async {
    await tester.pumpWidget(
      _host(
        MediaCaptionBlock(
          title: '',
          caption: caption,
          isExpanded: false,
          onToggle: () {},
        ),
        width: width,
      ),
    );
    await tester.pump();
  }

  testWidgets('收起态「全文」入口为沉浸次级白而非品牌色', (tester) async {
    await pumpCollapsed(tester, '这是一段足够长的说明文字。' * 20);

    final richText = tester.widget<RichText>(_captionRichText());
    final entrySpan = _findSpanWithText(richText.text, CommunityText.fullText);
    expect(entrySpan, isNotNull);
    expect(entrySpan!.style!.color, isNot(AppColors.primaryColor));
    expect(
      entrySpan.style!.color,
      AppColors.immersiveForeground.withValues(alpha: 0.7),
    );
  });

  testWidgets('展开态「收起」入口为沉浸次级白而非品牌色', (tester) async {
    await tester.pumpWidget(
      _host(
        MediaCaptionBlock(
          title: '',
          caption: '这是一段足够长的说明文字。' * 20,
          isExpanded: true,
          onToggle: () {},
        ),
      ),
    );
    await tester.pump();

    final richText = tester.widget<RichText>(
      find.byWidgetPredicate(
        (widget) =>
            widget is RichText &&
            widget.text.toPlainText().contains(CommunityText.collapse),
      ),
    );
    final entrySpan = _findSpanWithText(richText.text, CommunityText.collapse);
    expect(entrySpan, isNotNull);
    expect(entrySpan!.style!.color, isNot(AppColors.primaryColor));
    expect(
      entrySpan.style!.color,
      AppColors.immersiveForeground.withValues(alpha: 0.7),
    );
  });

  testWidgets('收起态「全文」恒在末行行尾单行呈现，不断字不换行', (tester) async {
    final samples = <String>[
      '乐山大佛景区位于四川省乐山市市中区，地处岷江、青衣江、大渡河三江交汇处，是世界文化与自然双重遗产。' * 3,
      '混排 sample 包含 verylongenglishtoken${'x' * 24} 与中文标点，用来逼出宽度不足时的回退路径。' * 3,
      '带 emoji 的说明🏔️🌊内容也不能把入口挤下去或者断字。' * 6,
    ];

    for (final caption in samples) {
      for (final width in <double>[280, 320, 375]) {
        await pumpCollapsed(tester, caption, width: width);

        final paragraph = tester.renderObject<RenderParagraph>(
          _captionRichText(),
        );
        final plainText = paragraph.text.toPlainText();
        final entryStart = plainText.lastIndexOf(CommunityText.fullText);
        expect(entryStart, greaterThan(0));

        final allBoxes = paragraph.getBoxesForSelection(
          TextSelection(baseOffset: 0, extentOffset: plainText.length),
        );
        final lineTops = allBoxes.map((box) => box.top.round()).toSet();
        expect(
          lineTops.length,
          lessThanOrEqualTo(3),
          reason: '收起态整段 rich text（含入口）不得超过 3 行。caption=$caption width=$width',
        );

        final entryBoxes = paragraph.getBoxesForSelection(
          TextSelection(
            baseOffset: entryStart,
            extentOffset: entryStart + CommunityText.fullText.length,
          ),
        );
        final entryTops = entryBoxes.map((box) => box.top.round()).toSet();
        expect(
          entryTops.length,
          1,
          reason: '「全文」不得断字跨行。caption=$caption width=$width',
        );
        expect(
          entryTops.single,
          lineTops.reduce((a, b) => a > b ? a : b),
          reason: '「全文」必须落在收起态最后一行。caption=$caption width=$width',
        );
      }
    }
  });
}
