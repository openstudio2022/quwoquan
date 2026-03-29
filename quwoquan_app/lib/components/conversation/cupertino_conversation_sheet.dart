import 'package:flutter/cupertino.dart';
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
    final clampedMaxHeight = maxHeightFactor.clamp(0.3, 0.92);
    final brightness =
        CupertinoTheme.of(context).brightness ??
        MediaQuery.platformBrightnessOf(context);
    final isDark = brightness == Brightness.dark;
    final outer = SettingsSemanticConstants.conversationSheetOuterHorizontalPadding;

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor:
          SettingsSemanticConstants.conversationSheetPanelBackground(isDark),
      maxHeightRatio: clampedMaxHeight,
      contentPadding: EdgeInsets.fromLTRB(
        outer,
        0,
        outer,
        viewInsets.bottom + outer,
      ),
      child: child,
    );
  }
}
