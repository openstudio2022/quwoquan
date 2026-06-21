import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ProfileSloganCard extends StatefulWidget {
  const ProfileSloganCard({
    super.key,
    required this.isDark,
    required this.bio,
    this.showEmptyPrompt = false,
    this.onTap,
  });

  final bool isDark;
  final String? bio;
  final bool showEmptyPrompt;
  final VoidCallback? onTap;

  @override
  State<ProfileSloganCard> createState() => _ProfileSloganCardState();
}

class _ProfileSloganCardState extends State<ProfileSloganCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final rawText = widget.bio?.trim() ?? '';
    final isPrompt = rawText.isEmpty;
    if (isPrompt && !widget.showEmptyPrompt) {
      return const SizedBox.shrink();
    }
    final text = isPrompt ? UITextConstants.profileEmptyBioPrompt : rawText;
    final surfaceStart = widget.isDark
        ? AppColors.profileSloganSurfaceStartDark
        : AppColors.profileSloganSurfaceStartLight;
    final surfaceEnd = widget.isDark
        ? AppColors.profileSloganSurfaceEndDark
        : AppColors.profileSloganSurfaceEndLight;
    final inkColor = isPrompt
        ? AppColors.iosSecondaryLabel(context)
        : (widget.isDark
              ? AppColors.profileSloganInkDark
              : AppColors.profileSloganInkLight);
    final accent = widget.isDark
        ? AppColors.profileSloganAccentDark
        : AppColors.profileSloganAccentLight;
    final textStyle = TextStyle(
      fontSize: AppTypography.iosSubheadline,
      height: AppSpacing.textLineHeightFootnote,
      color: inkColor,
      fontWeight: AppTypography.regular,
      letterSpacing: -0.08,
    );
    final card = Container(
      key: const ValueKey<String>('profile-slogan-card'),
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerXs,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: <Color>[
            surfaceStart.withValues(alpha: widget.isDark ? 0.92 : 0.86),
            surfaceEnd.withValues(alpha: widget.isDark ? 0.86 : 0.94),
          ],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: accent.withValues(alpha: widget.isDark ? 0.30 : 0.20),
          width: AppSpacing.hairline,
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final painter = TextPainter(
            text: TextSpan(text: text, style: textStyle),
            textDirection: Directionality.of(context),
            maxLines: 2,
          )..layout(maxWidth: constraints.maxWidth);
          final overflowed = painter.didExceedMaxLines;
          return Stack(
            children: <Widget>[
              Text(
                text,
                maxLines: _expanded ? null : 2,
                overflow: _expanded
                    ? TextOverflow.visible
                    : TextOverflow.ellipsis,
                style: textStyle,
              ),
              if (overflowed && !_expanded)
                PositionedDirectional(
                  end: 0,
                  bottom: 0,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => setState(() => _expanded = true),
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: surfaceEnd.withValues(
                          alpha: widget.isDark ? 0.96 : 0.98,
                        ),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.largeBorderRadius,
                        ),
                      ),
                      child: Padding(
                        padding: EdgeInsetsDirectional.only(
                          start: AppSpacing.intraGroupXs,
                        ),
                        child: Text(
                          '...全部',
                          style: textStyle.copyWith(
                            color: accent.withValues(
                              alpha: widget.isDark ? 0.94 : 0.86,
                            ),
                            fontWeight: AppTypography.regular,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
    if (widget.onTap == null) {
      return card;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: widget.onTap,
      child: card,
    );
  }
}
