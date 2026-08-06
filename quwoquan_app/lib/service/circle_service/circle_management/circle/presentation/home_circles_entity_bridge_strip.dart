import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

double _measureSingleLineTextHeight(BuildContext context, TextStyle style) {
  final painter = TextPainter(
    text: TextSpan(text: 'Hg', style: style),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 1,
  )..layout();
  return painter.height;
}

double _measureTwoLineTextHeight(BuildContext context, TextStyle style) {
  final painter = TextPainter(
    text: TextSpan(text: 'Hg\nHg', style: style),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 2,
  )..layout();
  return painter.height;
}

class HomeCirclesEntityBridgeStrip extends StatelessWidget {
  const HomeCirclesEntityBridgeStrip({
    super.key,
    required this.isDark,
    required this.onEntityTap,
  });

  final bool isDark;
  final ValueChanged<String> onEntityTap;

  static const List<_HomeCirclesEntityBridgeItem> _items =
      <_HomeCirclesEntityBridgeItem>[
        _HomeCirclesEntityBridgeItem(
          title: CreationText.homepageTypeUniversity,
          hint: CreationText.homepageTypeUniversityHint,
          query: CreationText.homepageTypeUniversity,
          icon: CupertinoIcons.building_2_fill,
        ),
        _HomeCirclesEntityBridgeItem(
          title: CreationText.homepageTypeTravelPhoto,
          hint: CreationText.homepageTypeTravelPhotoHint,
          query: CreationText.homepageTypeTravelPhoto,
          icon: CupertinoIcons.photo_fill_on_rectangle_fill,
        ),
        _HomeCirclesEntityBridgeItem(
          title: CreationText.homepageTypeHotel,
          hint: CreationText.homepageTypeHotelHint,
          query: CreationText.homepageTypeHotel,
          icon: CupertinoIcons.bed_double_fill,
        ),
      ];

  double _cardWidth(BuildContext context) {
    return AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.bottomNavHeight * 2.8,
      regular: AppSpacing.bottomNavHeight * 3.0,
      expanded: AppSpacing.bottomNavHeight * 3.2,
    );
  }

  double _stripHeight(BuildContext context) {
    final designHeight = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.bottomNavHeight * 2.25,
      regular: AppSpacing.bottomNavHeight * 2.35,
      expanded: AppSpacing.bottomNavHeight * 2.45,
    );
    final titleHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.smPlus,
        fontWeight: AppTypography.semiBold,
      ),
    );
    final hintHeight = _measureTwoLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.xsPlus,
        height: AppTypography.lineHeightTight,
      ),
    );
    final iconRowHeight = AppSpacing.avatarCircleSm + AppSpacing.intraGroupXs;
    final contentSpacing = AppSpacing.intraGroupSm + AppSpacing.oneHalf;
    final verticalPadding = AppSpacing.containerSm * 2;
    // 保护文本缩放后的像素取整误差，避免窄屏大字号时卡片底部溢出。
    final layoutRoundingCompensation = AppSpacing.two;
    final measuredHeight =
        iconRowHeight +
        contentSpacing +
        titleHeight +
        hintHeight +
        verticalPadding +
        layoutRoundingCompensation;
    return measuredHeight > designHeight ? measuredHeight : designHeight;
  }

  @override
  Widget build(BuildContext context) {
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final cardWidth = _cardWidth(context);

    return Container(
      color: cardSurface,
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.containerXs,
        horizontal,
        AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                CommunityText.circlesEntitySectionTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.medium,
                  color: fgSecondary.withValues(alpha: 0.82),
                  decoration: TextDecoration.none,
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Flexible(
                child: Text(
                  CommunityText.circlesEntitySectionHint,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.end,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    color: fgSecondary.withValues(alpha: 0.7),
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            height: _stripHeight(context),
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              itemCount: _items.length,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupMd),
              itemBuilder: (context, index) {
                final item = _items[index];
                return _HomeCirclesEntityBridgeCard(
                  width: cardWidth,
                  isDark: isDark,
                  borderColor: borderColor,
                  foregroundPrimary: fgPrimary,
                  foregroundSecondary: fgSecondary,
                  item: item,
                  onTap: () => onEntityTap(item.query),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeCirclesEntityBridgeItem {
  const _HomeCirclesEntityBridgeItem({
    required this.title,
    required this.hint,
    required this.query,
    required this.icon,
  });

  final String title;
  final String hint;
  final String query;
  final IconData icon;
}

class _HomeCirclesEntityBridgeCard extends StatelessWidget {
  const _HomeCirclesEntityBridgeCard({
    required this.width,
    required this.isDark,
    required this.borderColor,
    required this.foregroundPrimary,
    required this.foregroundSecondary,
    required this.item,
    required this.onTap,
  });

  final double width;
  final bool isDark;
  final Color borderColor;
  final Color foregroundPrimary;
  final Color foregroundSecondary;
  final _HomeCirclesEntityBridgeItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        width: width,
        decoration: BoxDecoration(
          color: SettingsSemanticConstants.conversationSheetCardSurface(isDark),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(
            color: borderColor.withValues(alpha: 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Container(
                  width: AppSpacing.avatarCircleSm + AppSpacing.intraGroupXs,
                  height: AppSpacing.avatarCircleSm + AppSpacing.intraGroupXs,
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(alpha: 0.12),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    item.icon,
                    size: AppSpacing.iconMedium,
                    color: AppColors.primaryColor,
                  ),
                ),
                const Expanded(child: SizedBox.shrink()),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: foregroundSecondary.withValues(alpha: 0.72),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              item.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.smPlus,
                fontWeight: AppTypography.semiBold,
                color: foregroundPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.oneHalf),
            Text(
              item.hint,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.xsPlus,
                color: foregroundSecondary,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
