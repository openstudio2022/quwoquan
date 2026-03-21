import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class CupertinoConversationSheet extends StatelessWidget {
  const CupertinoConversationSheet({
    super.key,
    required this.child,
    this.maxHeightFactor = 0.72,
  });

  final Widget child;
  final double maxHeightFactor;

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.viewInsetsOf(context);
    final maxHeight = MediaQuery.sizeOf(context).height *
        math.min(math.max(maxHeightFactor, 0.3), 0.92);

    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerSm,
          AppSpacing.containerSm,
          AppSpacing.containerSm,
          viewInsets.bottom + AppSpacing.containerSm,
        ),
        child: Align(
          alignment: Alignment.bottomCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: maxHeight),
            child: CupertinoPopupSurface(
              isSurfacePainted: true,
              child: Material(
                color: CupertinoDynamicColor.resolve(
                  CupertinoColors.systemBackground,
                  context,
                ),
                child: child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
