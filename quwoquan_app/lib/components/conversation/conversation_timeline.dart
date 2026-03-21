import 'package:flutter/material.dart';

/// Shared conversation timeline container with optional overlay slots.
class ConversationTimeline extends StatelessWidget {
  const ConversationTimeline({
    super.key,
    required this.controller,
    required this.padding,
    required this.itemCount,
    required this.itemBuilder,
    required this.backgroundColor,
    this.overlays = const <Widget>[],
  });

  final ScrollController controller;
  final EdgeInsetsGeometry padding;
  final int itemCount;
  final IndexedWidgetBuilder itemBuilder;
  final Color backgroundColor;
  final List<Widget> overlays;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: <Widget>[
        Container(
          color: backgroundColor,
          child: ListView.builder(
            controller: controller,
            padding: padding,
            itemCount: itemCount,
            itemBuilder: itemBuilder,
          ),
        ),
        ...overlays,
      ],
    );
  }
}
