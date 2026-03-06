import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class AssistantSessionHeader extends StatelessWidget {
  const AssistantSessionHeader({
    super.key,
    required this.fgPrimary,
    required this.showWelcome,
  });

  final Color fgPrimary;
  final bool showWelcome;

  @override
  Widget build(BuildContext context) {
    if (!showWelcome) return const SizedBox.shrink();
    return _buildWelcomeHeader();
  }

  Widget _buildWelcomeHeader() {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.containerSm,
        AppSpacing.xs,
      ),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          UITextConstants.assistantWelcomeHeadline,
          style: TextStyle(
            fontSize: AppTypography.xxl,
            fontWeight: FontWeight.w700,
            color: fgPrimary,
          ),
        ),
      ),
    );
  }

}
