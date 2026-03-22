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

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: CupertinoDynamicColor.resolve(
        CupertinoColors.systemBackground,
        context,
      ),
      maxHeightRatio: clampedMaxHeight,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        0,
        AppSpacing.containerSm,
        viewInsets.bottom + AppSpacing.containerSm,
      ),
      child: child,
    );
  }
}
