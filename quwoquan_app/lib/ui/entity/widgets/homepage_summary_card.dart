import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class HomepageSummaryCard extends StatelessWidget {
  const HomepageSummaryCard({
    super.key,
    required this.summary,
    this.onTap,
    this.isSelected = false,
    this.showChevron = true,
    this.addShadow = true,
  });

  final HomepageSummary summary;
  final VoidCallback? onTap;
  final bool isSelected;
  final bool showChevron;
  final bool addShadow;

  @override
  Widget build(BuildContext context) {
    final ratingValue = summary.averageRating?.toStringAsFixed(1);
    final borderColor = isSelected
        ? AppColors.iosAccent(context).withValues(alpha: 0.28)
        : AppColors.iosSeparator(context).withValues(alpha: 0.16);
    final card = SizedBox(
      width: double.infinity,
      child: ProfileIosSectionCard(
        addShadow: addShadow,
        radius: AppSpacing.radiusTwentyEight,
        backgroundColor: AppColors.iosProfileSurface(context),
        borderColor: borderColor,
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _HomepageCardIdentityHeader(
              title: summary.title,
              subtitle: (summary.subtitle ?? '').trim(),
              metaLine: _locationLine(summary),
              coverUrl: summary.coverUrl,
              trailing: _buildTrailing(context),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: <Widget>[
                _HomepageMetaChip(
                  label: _homepageTypeLabel(summary.homepageType),
                ),
                _HomepageMetaChip(label: _homepageStatusLabel(summary.status)),
                _HomepageMetaChip(
                  label: ratingValue == null ? '待积累口碑' : '$ratingValue 分',
                  accent: ratingValue != null,
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            _HomepageSummaryMetrics(
              ratingValue: ratingValue ?? '--',
              ratingCount: summary.ratingCount,
              status: _homepageStatusLabel(summary.status),
            ),
          ],
        ),
      ),
    );
    if (onTap == null) {
      return card;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: card,
    );
  }

  Widget? _buildTrailing(BuildContext context) {
    if (isSelected) {
      return const Icon(
        CupertinoIcons.check_mark_circled_solid,
        size: AppSpacing.iconMedium,
        color: AppColors.primaryColor,
      );
    }
    if (showChevron) {
      return Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconSmall,
        color: AppColors.iosSecondaryLabel(context),
      );
    }
    return null;
  }
}

class _HomepageCardIdentityHeader extends StatelessWidget {
  const _HomepageCardIdentityHeader({
    required this.title,
    required this.subtitle,
    required this.metaLine,
    this.coverUrl,
    this.trailing,
  });

  final String title;
  final String subtitle;
  final String metaLine;
  final String? coverUrl;
  final Widget? trailing;

  static const double _coverBorder = AppSpacing.three;
  static const double _coverExtent = AppSpacing.avatarCircleXl;
  static const double _coverRadius = AppSpacing.radiusTwenty;
  static const double _coverOverlapRatio = 0.34;

  static double get _coverOuterExtent => _coverExtent + (_coverBorder * 2);
  static double get _coverIntrusion => _coverOuterExtent * _coverOverlapRatio;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(left: _coverOuterExtent + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.bold,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  if (trailing != null) ...<Widget>[
                    SizedBox(width: AppSpacing.containerSm),
                    trailing!,
                  ],
                ],
              ),
              if (subtitle.isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
              if (metaLine.isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  metaLine,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
              ],
            ],
          ),
        ),
        Positioned(
          top: -_coverIntrusion,
          left: 0,
          child: _HomepageCardCover(coverUrl: coverUrl),
        ),
      ],
    );
  }
}

class _HomepageCardCover extends StatelessWidget {
  const _HomepageCardCover({required this.coverUrl});

  final String? coverUrl;

  @override
  Widget build(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(
          _HomepageCardIdentityHeader._coverRadius,
        ),
      ),
      child: Icon(
        CupertinoIcons.photo_fill_on_rectangle_fill,
        size: AppSpacing.iconLarge,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(
          _HomepageCardIdentityHeader._coverRadius +
              _HomepageCardIdentityHeader._coverBorder,
        ),
        border: Border.all(
          color: AppColors.iosProfileSurface(context),
          width: _HomepageCardIdentityHeader._coverBorder,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.12),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(
          _HomepageCardIdentityHeader._coverRadius,
        ),
        child: SizedBox(
          width: _HomepageCardIdentityHeader._coverExtent,
          height: _HomepageCardIdentityHeader._coverExtent,
          child: (coverUrl ?? '').trim().isEmpty
              ? fallback
              : CircleMediaImage(
                  imageSource: coverUrl!,
                  fit: BoxFit.cover,
                  placeholder: fallback,
                  errorWidget: fallback,
                ),
        ),
      ),
    );
  }
}

class _HomepageMetaChip extends StatelessWidget {
  const _HomepageMetaChip({required this.label, this.accent = false});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final accentColor = AppColors.iosAccent(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: accent
            ? accentColor.withValues(alpha: 0.12)
            : AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: accent ? accentColor : AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _HomepageSummaryMetrics extends StatelessWidget {
  const _HomepageSummaryMetrics({
    required this.ratingValue,
    required this.ratingCount,
    required this.status,
  });

  final String ratingValue;
  final int ratingCount;
  final String status;

  @override
  Widget build(BuildContext context) {
    final dividerColor = AppColors.iosSeparator(
      context,
    ).withValues(alpha: 0.12);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: dividerColor, width: AppSpacing.hairline),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: _HomepageMetricItem(label: '评分', value: ratingValue),
          ),
          _HomepageMetricDivider(color: dividerColor),
          Expanded(
            child: _HomepageMetricItem(label: '口碑', value: '$ratingCount'),
          ),
          _HomepageMetricDivider(color: dividerColor),
          Expanded(
            child: _HomepageMetricItem(label: '状态', value: status),
          ),
        ],
      ),
    );
  }
}

class _HomepageMetricItem extends StatelessWidget {
  const _HomepageMetricItem({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}

class _HomepageMetricDivider extends StatelessWidget {
  const _HomepageMetricDivider({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.hairline,
      height: AppSpacing.iconButtonMinSizeMd,
      color: color,
    );
  }
}

String _homepageTypeLabel(String type) {
  switch (type.trim()) {
    case 'hotel':
      return '酒店';
    case 'restaurant':
      return '餐厅';
    case 'vehicle':
      return '车型';
    case 'sight':
      return '景点';
    default:
      return '主页';
  }
}

String _homepageStatusLabel(String? status) {
  switch ((status ?? '').trim()) {
    case 'candidate':
      return '待发布';
    case 'offline':
      return '已下线';
    case 'published':
      return '已发布';
    default:
      return '主页';
  }
}

String _locationLine(HomepageSummary summary) {
  return <String>[
    if ((summary.city ?? '').trim().isNotEmpty) summary.city!.trim(),
    if ((summary.address ?? '').trim().isNotEmpty) summary.address!.trim(),
  ].join(' · ');
}
