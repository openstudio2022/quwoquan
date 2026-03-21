import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// Shared conversation page shell used by chat- and assistant-owned pages.
class ConversationPageScaffold extends StatelessWidget {
  const ConversationPageScaffold({
    super.key,
    required this.embedded,
    required this.backgroundColor,
    required this.body,
    this.navigationBar,
    this.overlays = const <Widget>[],
  });

  final bool embedded;
  final Color backgroundColor;
  final Widget body;
  final ObstructingPreferredSizeWidget? navigationBar;
  final List<Widget> overlays;

  @override
  Widget build(BuildContext context) {
    final pageContent = embedded
        ? Container(color: backgroundColor, child: body)
        : AppScaffold(
            backgroundColor: backgroundColor,
            navigationBar: navigationBar,
            body: body,
          );

    if (overlays.isEmpty) {
      return pageContent;
    }
    return Stack(
      children: <Widget>[
        pageContent,
        ...overlays,
      ],
    );
  }
}
