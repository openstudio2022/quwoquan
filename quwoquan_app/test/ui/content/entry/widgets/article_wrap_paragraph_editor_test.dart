import 'package:flutter/cupertino.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_wrap_paragraph_editor.dart';

class _WrapEditorHarness extends StatefulWidget {
  const _WrapEditorHarness({
    required this.initialNarrowText,
    required this.initialBelowText,
    this.autofocusSegment,
    this.autofocusSelectionOffset,
    this.onChanged,
    this.onSelectionChanged,
  });

  final String initialNarrowText;
  final String initialBelowText;
  final ArticleWrapEditorSegment? autofocusSegment;
  final int? autofocusSelectionOffset;
  final void Function(String narrowText, String belowText)? onChanged;
  final void Function(ArticleWrapEditorSegment segment, int offset)?
      onSelectionChanged;

  @override
  State<_WrapEditorHarness> createState() => _WrapEditorHarnessState();
}

class _WrapEditorHarnessState extends State<_WrapEditorHarness> {
  late String _narrowText;
  late String _belowText;

  @override
  void initState() {
    super.initState();
    _narrowText = widget.initialNarrowText;
    _belowText = widget.initialBelowText;
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoApp(
      home: CupertinoPageScaffold(
        child: Center(
          child: SizedBox(
            width: 220,
            child: ArticleWrapParagraphEditor(
              groupId: 'para_0',
              narrowText: _narrowText,
              belowText: _belowText,
              imageChild: Container(
                width: 96,
                height: 40,
                color: CupertinoColors.systemGrey4,
              ),
              imageWidth: 96,
              narrowWidth: 96,
              gap: 8,
              isLeft: true,
              floatHeight: 40,
              style: const TextStyle(fontSize: 16, height: 1.5),
              placeholderStyle: const TextStyle(
                fontSize: 16,
                color: CupertinoColors.placeholderText,
              ),
              placeholder: '+ 想写点什么',
              autofocusSegment: widget.autofocusSegment,
              autofocusSelectionOffset: widget.autofocusSelectionOffset,
              belowSpacing: articleParagraphSpacing(),
              onChanged: (narrowText, belowText) {
                setState(() {
                  _narrowText = narrowText;
                  _belowText = belowText;
                });
                widget.onChanged?.call(narrowText, belowText);
              },
              onFocused: (_) {},
              onSelectionChanged: (segment, offset) {
                widget.onSelectionChanged?.call(segment, offset);
              },
            ),
          ),
        ),
      ),
    );
  }
}

TextEditingController? _controllerByKey(WidgetTester tester, String key) {
  final finder = find.byKey(ValueKey<String>(key));
  if (!tester.any(finder)) {
    return null;
  }
  final widget = tester.widget(finder);
  if (widget is EditableText) {
    return widget.controller;
  }
  final descendant = find.descendant(
    of: finder,
    matching: find.byType(EditableText),
  );
  if (tester.any(descendant)) {
    return tester.widget<EditableText>(descendant).controller;
  }
  return null;
}

String _textByKey(WidgetTester tester, String key) {
  final finder = find.byKey(ValueKey<String>(key));
  if (!tester.any(finder)) {
    return '';
  }
  final widget = tester.widget(finder);
  if (widget is EditableText) {
    return widget.controller.text;
  }
  if (widget is Text) {
    return widget.data ?? '';
  }
  final descendant = find.descendant(
    of: finder,
    matching: find.byType(EditableText),
  );
  if (tester.any(descendant)) {
    return tester.widget<EditableText>(descendant).controller.text;
  }
  final textDescendant = find.descendant(of: finder, matching: find.byType(Text));
  if (tester.any(textDescendant)) {
    return tester.widget<Text>(textDescendant.first).data ?? '';
  }
  return '';
}

FocusNode? _focusNodeByKey(WidgetTester tester, String key) {
  final finder = find.byKey(ValueKey<String>(key));
  if (!tester.any(finder)) {
    return null;
  }
  final widget = tester.widget(finder);
  if (widget is EditableText) {
    return widget.focusNode;
  }
  final descendant = find.descendant(
    of: finder,
    matching: find.byType(EditableText),
  );
  if (tester.any(descendant)) {
    return tester.widget<EditableText>(descendant).focusNode;
  }
  return null;
}

int _focusedEditableTextCount(WidgetTester tester) {
  final focusedNodes = <FocusNode>{};
  for (final element in find.byType(EditableText).evaluate()) {
    final widget = element.widget as EditableText;
    if (widget.focusNode.hasFocus) {
      focusedNodes.add(widget.focusNode);
    }
  }
  return focusedNodes.length;
}

({String narrow, String below}) _splitSeedText(String text) {
  const style = TextStyle(fontSize: 16, height: 1.5);
  const lineHeight = 16 * 1.5;
  final splitOffset = resolveWrappedSplitIndex(
    text: text,
    sideWidth: 96,
    style: style,
    maxLines: (40 / lineHeight).floor().clamp(1, 24),
  );
  return (
    narrow: text.substring(0, splitOffset),
    below: text.substring(splitOffset),
  );
}

void main() {
  testWidgets('窄文输入超过图片高度后会把溢出文字移到下文并切换焦点', (tester) async {
    final seed = _splitSeedText('这是一段为了填满窄文区的初始文本');
    String? latestNarrow;
    String? latestBelow;

    await tester.pumpWidget(
      _WrapEditorHarness(
        initialNarrowText: seed.narrow,
        initialBelowText: '',
        onChanged: (narrowText, belowText) {
          latestNarrow = narrowText;
          latestBelow = belowText;
        },
      ),
    );
    await tester.pumpAndSettle();

    final narrowFinder = find.byKey(const ValueKey<String>('wrap_narrow_para_0'));
    await tester.tap(narrowFinder);
    await tester.pumpAndSettle();
    await tester.enterText(narrowFinder, '${seed.narrow}新增下文');
    await tester.pumpAndSettle();

    expect(latestNarrow, isNotNull);
    expect(latestBelow, isNotNull);
    expect(latestNarrow!.length, lessThan('${seed.narrow}新增下文'.length));
    expect(latestBelow, contains('新增下文'));
    final belowFocus = _focusNodeByKey(tester, 'wrap_below_para_0');
    expect(belowFocus, isNotNull);
    expect(belowFocus!.hasFocus, isTrue);
  });

  testWidgets('下文为空时点击下文区并输入首字后仍留在下文', (tester) async {
    final seed = _splitSeedText('这是一段为了填满窄文区的初始文本');
    String? latestNarrow;
    String? latestBelow;

    await tester.pumpWidget(
      _WrapEditorHarness(
        initialNarrowText: seed.narrow,
        initialBelowText: '',
        onChanged: (narrowText, belowText) {
          latestNarrow = narrowText;
          latestBelow = belowText;
        },
      ),
    );
    await tester.pumpAndSettle();

    final belowFinder = find.byKey(const ValueKey<String>('wrap_below_para_0'));
    await tester.tap(belowFinder);
    await tester.pumpAndSettle();

    final belowFocus = _focusNodeByKey(tester, 'wrap_below_para_0');
    expect(belowFocus, isNotNull);
    expect(belowFocus!.hasFocus, isTrue);

    await tester.enterText(belowFinder, '首字');
    await tester.pumpAndSettle();

    expect(latestNarrow, seed.narrow);
    expect(latestBelow, '首字');
    final belowFocusAfter = _focusNodeByKey(tester, 'wrap_below_para_0');
    expect(belowFocusAfter, isNotNull);
    expect(belowFocusAfter!.hasFocus, isTrue);
    expect(_textByKey(tester, 'wrap_narrow_para_0'), seed.narrow);
    expect(_textByKey(tester, 'wrap_below_para_0'), '首字');
  });

  testWidgets('below 有焦点时点击窄文区可切换到窄文且保持单焦点', (tester) async {
    final seed = _splitSeedText('这是一段足够长的图文混排正文，用来验证双段焦点切换。');

    await tester.pumpWidget(
      _WrapEditorHarness(
        initialNarrowText: seed.narrow,
        initialBelowText: seed.below,
        autofocusSegment: ArticleWrapEditorSegment.below,
        autofocusSelectionOffset: seed.below.length,
      ),
    );
    await tester.pumpAndSettle();

    expect(_focusNodeByKey(tester, 'wrap_below_para_0')?.hasFocus, isTrue);

    await tester.tap(find.byKey(const ValueKey<String>('wrap_narrow_para_0')));
    await tester.pumpAndSettle();

    expect(_focusNodeByKey(tester, 'wrap_narrow_para_0')?.hasFocus, isTrue);
    expect(_focusedEditableTextCount(tester), equals(1));
  });

  testWidgets('窄文为空时点击 sideChild 可获得输入焦点', (tester) async {
    await tester.pumpWidget(
      const _WrapEditorHarness(
        initialNarrowText: '',
        initialBelowText: '',
      ),
    );
    await tester.pumpAndSettle();

    final narrowFinder = find.byKey(const ValueKey<String>('wrap_narrow_para_0'));
    await tester.tap(narrowFinder);
    await tester.pumpAndSettle();

    expect(_focusNodeByKey(tester, 'wrap_narrow_para_0')?.hasFocus, isTrue);
  });

  testWidgets('autofocusSegment 会把焦点落到下文并回传局部 offset', (tester) async {
    final seed = _splitSeedText('这是一段足够长的图文混排正文，用来验证下文光标映射。');
    ArticleWrapEditorSegment? lastSegment;
    int? lastOffset;

    await tester.pumpWidget(
      _WrapEditorHarness(
        initialNarrowText: seed.narrow,
        initialBelowText: seed.below,
        autofocusSegment: ArticleWrapEditorSegment.below,
        autofocusSelectionOffset: seed.below.length,
        onSelectionChanged: (segment, offset) {
          lastSegment = segment;
          lastOffset = offset;
        },
      ),
    );
    await tester.pumpAndSettle();

    expect(lastSegment, ArticleWrapEditorSegment.below);
    expect(lastOffset, seed.below.length);
    expect(_focusNodeByKey(tester, 'wrap_below_para_0')?.hasFocus, isTrue);
  });
}
