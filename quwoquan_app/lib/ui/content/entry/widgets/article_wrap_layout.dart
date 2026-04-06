import 'package:flutter/widgets.dart';

class ArticleWrapLayout extends StatelessWidget {
  const ArticleWrapLayout({
    super.key,
    required this.imageWidth,
    required this.gap,
    required this.isLeft,
    required this.imageChild,
    required this.sideChild,
    this.aboveChild,
    this.belowChild,
    this.sideMinHeight = 0,
    this.belowSpacing = 0,
  });

  final double imageWidth;
  final double gap;
  final bool isLeft;
  final Widget imageChild;
  final Widget sideChild;
  final Widget? aboveChild;
  final Widget? belowChild;
  final double sideMinHeight;
  /// 下方全宽区与 Row 之间的间距（行间距，非段间距）。
  final double belowSpacing;

  @override
  Widget build(BuildContext context) {
    final image = SizedBox(width: imageWidth, child: imageChild);
    final side = Expanded(
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: sideMinHeight),
        child: sideChild,
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (aboveChild != null) aboveChild!,
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: isLeft
              ? <Widget>[image, SizedBox(width: gap), side]
              : <Widget>[side, SizedBox(width: gap), image],
        ),
        if (belowChild != null) ...[
          if (belowSpacing > 0) SizedBox(height: belowSpacing),
          belowChild!,
        ],
      ],
    );
  }
}
