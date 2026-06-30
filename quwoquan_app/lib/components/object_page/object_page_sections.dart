import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_content_preview.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_relation_edge.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum ObjectIdentityKind { user, circle, entity }

class ObjectContextTabSpec {
  const ObjectContextTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

/// 唯一身份头底座（对象/圈子/用户主页共享）。
///
/// 单一真相源：用户主页 `ProfileHeader` 的版式下沉而来 —— 头像左侧 1/3 上探，
/// 头像右侧只渲染「名字 + 类型/标签副标题」；认证勾、二维码、空标签提示等
/// 用户专属元素经 [titleTrailing] / [trailing] / [subtitleOverride] 插槽注入。
///
/// 头像由调用方通过 [media] 传入（推荐 [ObjectIdentityAvatar]），尺寸需等于
/// [avatarOuterExtent]，以保证与四类主页一致的上探/留白几何。
class ObjectIdentityHeader extends StatelessWidget {
  const ObjectIdentityHeader({
    super.key,
    required this.title,
    required this.media,
    this.titleTrailing,
    this.subtitle,
    this.subtitleOverride,
    this.trailing,
    this.avatarOuterExtent = avatarOuterExtentDefault,
    this.avatarOverlapRatio = avatarOverlapRatioDefault,
  });

  final String title;

  /// 头像/封面（含边框、阴影），尺寸应为 [avatarOuterExtent]。
  final Widget media;

  /// 名字右侧插槽（认证勾 / 官方标）。
  final Widget? titleTrailing;

  /// 类型/标签单行副标题（业务侧以 ` · ` 拼接）。
  final String? subtitle;

  /// 副标题替换插槽（如用户主页空标签提示按钮）；非空时优先于 [subtitle]。
  final Widget? subtitleOverride;

  /// 名字行尾部插槽（二维码 / 更多）。
  final Widget? trailing;

  final double avatarOuterExtent;
  final double avatarOverlapRatio;

  static const double avatarInnerExtent = AppSpacing.xl * 2;
  static const double avatarBorder = AppSpacing.three;
  static const double avatarOuterExtentDefault =
      avatarInnerExtent + avatarBorder * 2;
  static const double avatarOverlapRatioDefault = 0.333;

  double get _avatarOverlapPx => avatarOuterExtent * avatarOverlapRatio;

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);

    final subtitleSection = <Widget>[];
    if (subtitleOverride != null) {
      subtitleSection
        ..add(SizedBox(height: AppSpacing.intraGroupXs))
        ..add(subtitleOverride!);
    } else if ((subtitle ?? '').trim().isNotEmpty) {
      subtitleSection
        ..add(SizedBox(height: AppSpacing.intraGroupXs))
        ..add(
          Text(
            subtitle!.trim(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
              letterSpacing: -0.08,
            ),
          ),
        );
    }

    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(left: avatarOuterExtent + AppSpacing.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: <Widget>[
                        Flexible(
                          child: Text(
                            title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosTitle3,
                              fontWeight: AppTypography.regular,
                              color: fg.withValues(alpha: 0.94),
                              letterSpacing: -0.24,
                              height: AppSpacing.textLineHeightDense,
                            ),
                          ),
                        ),
                        if (titleTrailing != null) ...<Widget>[
                          SizedBox(width: AppSpacing.intraGroupXs),
                          titleTrailing!,
                        ],
                      ],
                    ),
                    ...subtitleSection,
                  ],
                ),
              ),
              if (trailing != null) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupXs),
                trailing!,
              ],
            ],
          ),
        ),
        Positioned(top: -_avatarOverlapPx, left: 0, child: media),
      ],
    );
  }
}

class ObjectHighlightSection extends StatelessWidget {
  const ObjectHighlightSection({
    super.key,
    required this.items,
    required this.isDark,
    this.title = '看点',
    this.emptyMessage = '还没有可展示的高质量内容',
    this.onTap,
  });

  final List<HomepageContentPreview> items;
  final bool isDark;
  final String title;
  final String emptyMessage;
  final void Function(HomepageContentPreview item)? onTap;

  @override
  Widget build(BuildContext context) {
    final visible = items.take(4).toList(growable: false);
    return _ObjectSectionCard(
      isDark: isDark,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _ObjectSectionTitle(icon: CupertinoIcons.sparkles, title: title),
          SizedBox(height: AppSpacing.intraGroupSm),
          if (visible.isEmpty)
            ObjectPageEmptyState(
              icon: CupertinoIcons.square_stack_3d_up,
              message: emptyMessage,
              isDark: isDark,
            )
          else
            ...visible.map(
              (item) => _ObjectHighlightTile(item: item, onTap: onTap),
            ),
        ],
      ),
    );
  }
}

class ObjectContextTabBar extends StatelessWidget {
  const ObjectContextTabBar({
    super.key,
    required this.tabs,
    required this.selectedId,
    required this.onSelected,
    this.isPinned = false,
  });

  final List<ObjectContextTabSpec> tabs;
  final String selectedId;
  final ValueChanged<String> onSelected;
  final bool isPinned;

  @override
  Widget build(BuildContext context) {
    if (tabs.isEmpty) {
      return const SizedBox.shrink();
    }
    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(
          context,
        ).withValues(alpha: isPinned ? 0.96 : 0),
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.1),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        itemBuilder: (context, index) {
          final tab = tabs[index];
          final selected = tab.id == selectedId;
          return CupertinoButton(
            minimumSize: const Size(
              AppSpacing.buttonHeightSm,
              AppSpacing.buttonHeightSm,
            ),
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            onPressed: () => onSelected(tab.id),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  tab.label,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: selected
                        ? AppTypography.semiBold
                        : AppTypography.medium,
                    color: selected
                        ? AppColors.iosLabel(context)
                        : AppColors.iosSecondaryLabel(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  width: selected ? AppSpacing.twenty : AppSpacing.zero,
                  height: AppSpacing.primaryTabUnderlineHeight,
                  decoration: BoxDecoration(
                    color: AppColors.iosAccent(context),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusNinetyNine,
                    ),
                  ),
                ),
              ],
            ),
          );
        },
        separatorBuilder: (context, index) =>
            SizedBox(width: AppSpacing.intraGroupXs),
        itemCount: tabs.length,
      ),
    );
  }
}

class ObjectBreadcrumbTrail extends StatelessWidget {
  const ObjectBreadcrumbTrail({super.key, required this.items, this.onTap});

  final List<String> items;
  final ValueChanged<int>? onTap;

  @override
  Widget build(BuildContext context) {
    final visible = items
        .where((item) => item.trim().isNotEmpty)
        .take(4)
        .toList(growable: false);
    if (visible.isEmpty) {
      return const SizedBox.shrink();
    }
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.intraGroupXs,
      runSpacing: AppSpacing.intraGroupXs,
      children: <Widget>[
        Icon(
          CupertinoIcons.location_solid,
          size: AppSpacing.iconSmall,
          color: AppColors.iosSecondaryLabel(context),
        ),
        for (var i = 0; i < visible.length; i += 1) ...<Widget>[
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap == null ? null : () => onTap!(i),
            child: Text(
              visible[i],
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.medium,
                color: i == visible.length - 1
                    ? AppColors.iosLabel(context)
                    : AppColors.iosSecondaryLabel(context),
              ),
            ),
          ),
          if (i != visible.length - 1)
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.fourteen,
              color: AppColors.iosSecondaryLabel(context),
            ),
        ],
      ],
    );
  }
}

class ObjectPageEmptyState extends StatelessWidget {
  const ObjectPageEmptyState({
    super.key,
    required this.icon,
    required this.message,
    required this.isDark,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String message;
  final bool isDark;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerLg),
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context).withValues(alpha: 0.44),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            icon,
            size: AppSpacing.iconLarge,
            color: AppColors.iosSecondaryLabel(context),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
              height: AppSpacing.textLineHeightBody,
            ),
          ),
          if ((actionLabel ?? '').trim().isNotEmpty && onAction != null)
            Padding(
              padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
              child: CupertinoButton(
                minimumSize: const Size(
                  AppSpacing.buttonHeightSm,
                  AppSpacing.buttonHeightSm,
                ),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                ),
                color: AppColors.iosAccent(context),
                borderRadius: BorderRadius.circular(
                  AppSpacing.radiusNinetyNine,
                ),
                onPressed: onAction,
                child: Text(
                  actionLabel!.trim(),
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                    color: CupertinoColors.white,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class ObjectPageSkeleton extends StatelessWidget {
  const ObjectPageSkeleton({super.key, required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.iosSecondaryFill(
      context,
    ).withValues(alpha: isDark ? 0.32 : 0.56);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            _SkeletonBlock(
              width: AppSpacing.avatarUserXl,
              height: AppSpacing.avatarUserXl,
              radius: AppSpacing.radiusTwenty,
              color: color,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _SkeletonBlock(
                    width: double.infinity,
                    height: AppSpacing.twenty,
                    radius: AppSpacing.radiusTen,
                    color: color,
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  _SkeletonBlock(
                    width: AppSpacing.twoHundredTwenty,
                    height: AppSpacing.fourteen,
                    radius: AppSpacing.radiusTen,
                    color: color,
                  ),
                ],
              ),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.containerMd),
        _SkeletonBlock(
          width: double.infinity,
          height: AppSpacing.homeObjectCardRailHeight,
          radius: AppSpacing.radiusTwenty,
          color: color,
        ),
      ],
    );
  }
}

/// 身份头底座配套头像（实体=圆形，圈子=圆角方，用户=圆形）。
///
/// 尺寸固定为 [ObjectIdentityHeader.avatarOuterExtent]（含边框），上探/留白几何由
/// [ObjectIdentityHeader] 统一负责；与用户主页头像同源的边框、阴影语义。
class ObjectIdentityAvatar extends StatelessWidget {
  const ObjectIdentityAvatar({
    super.key,
    required this.kind,
    this.child,
    this.borderColor,
  });

  final ObjectIdentityKind kind;

  /// 头像内容（图片）；缺省回退为类型占位图标。
  final Widget? child;

  /// 边框色；缺省与卡面同源（`conversationSheetCardSurface`）。
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    const inner = ObjectIdentityHeader.avatarInnerExtent;
    const border = ObjectIdentityHeader.avatarBorder;
    final resolvedBorder =
        borderColor ??
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final innerRadius = switch (kind) {
      ObjectIdentityKind.user => inner,
      ObjectIdentityKind.entity => inner,
      ObjectIdentityKind.circle => inner * AppSpacing.avatarCircleBorderRadiusRatio,
    };
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(innerRadius + border),
        border: Border.all(color: resolvedBorder, width: border),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.18 : 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(innerRadius),
        child: SizedBox(
          width: inner,
          height: inner,
          child: child ?? _ObjectIdentityFallback(kind: kind),
        ),
      ),
    );
  }
}

class _ObjectIdentityFallback extends StatelessWidget {
  const _ObjectIdentityFallback({required this.kind});

  final ObjectIdentityKind kind;

  @override
  Widget build(BuildContext context) {
    final icon = switch (kind) {
      ObjectIdentityKind.user => CupertinoIcons.person_fill,
      ObjectIdentityKind.circle => CupertinoIcons.person_3_fill,
      ObjectIdentityKind.entity => CupertinoIcons.photo_fill_on_rectangle_fill,
    };
    return DecoratedBox(
      decoration: BoxDecoration(color: AppColors.iosSecondaryFill(context)),
      child: Center(
        child: Icon(
          icon,
          size: AppSpacing.iconLarge,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _ObjectSectionCard extends StatelessWidget {
  const _ObjectSectionCard({required this.child, required this.isDark});

  final Widget child;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
          width: AppSpacing.hairline,
        ),
      ),
      child: child,
    );
  }
}

class _ObjectSectionTitle extends StatelessWidget {
  const _ObjectSectionTitle({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(
          icon,
          size: AppSpacing.iconSmall,
          color: AppColors.iosAccent(context),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
      ],
    );
  }
}

class _ObjectHighlightTile extends StatelessWidget {
  const _ObjectHighlightTile({required this.item, this.onTap});

  final HomepageContentPreview item;
  final void Function(HomepageContentPreview item)? onTap;

  @override
  Widget build(BuildContext context) {
    final title = item.title.trim();
    final summary = item.summary?.trim() ?? '';
    return CupertinoButton(
      minimumSize: const Size(
        AppSpacing.buttonHeightSm,
        AppSpacing.buttonHeightSm,
      ),
      padding: EdgeInsets.zero,
      onPressed: onTap == null ? null : () => onTap!(item),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.forty,
              height: AppSpacing.forty,
              decoration: BoxDecoration(
                color: AppColors.iosSecondaryFill(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              ),
              child: Icon(
                _contentIcon(item.contentType ?? ''),
                size: AppSpacing.iconSmall,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    title.isEmpty ? '对象内容' : title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.medium,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (summary.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      summary,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }

  static IconData _contentIcon(String contentType) {
    return switch (contentType) {
      'video' => CupertinoIcons.play_rectangle_fill,
      'photo' => CupertinoIcons.photo_fill,
      'article' => CupertinoIcons.doc_text_fill,
      _ => CupertinoIcons.square_stack_3d_up_fill,
    };
  }
}

class _SkeletonBlock extends StatelessWidget {
  const _SkeletonBlock({
    required this.width,
    required this.height,
    required this.radius,
    required this.color,
  });

  final double width;
  final double height;
  final double radius;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

class ObjectRelationRibbon extends StatelessWidget {
  const ObjectRelationRibbon({
    super.key,
    required this.edges,
    required this.isDark,
    this.title = '与你相关',
    this.maxVisible = 3,
  });

  final List<ObjectRelationEdge> edges;
  final bool isDark;
  final String title;
  final int maxVisible;

  @override
  Widget build(BuildContext context) {
    final usable = edges
        .where((edge) => edge.edgeType.trim().isNotEmpty)
        .take(maxVisible)
        .toList(growable: false);
    if (usable.isEmpty) {
      return const SizedBox.shrink();
    }
    final accent = AppColors.iosAccent(context);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
          width: AppSpacing.hairline,
        ),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                CupertinoIcons.link,
                size: AppSpacing.iconSmall,
                color: accent,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                title,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...usable.map(
            (edge) => Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
              child: Row(
                children: <Widget>[
                  Container(
                    width: AppSpacing.intraGroupSm,
                    height: AppSpacing.intraGroupSm,
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.72),
                      shape: BoxShape.circle,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Expanded(
                    child: Text(
                      _edgeLabel(edge),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: fgSecondary,
                        height: AppSpacing.textLineHeightBody,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _edgeLabel(ObjectRelationEdge edge) {
    final verb = switch (edge.edgeType.trim()) {
      'author_of' => '创作了',
      'posted_to_circle' => '发布到圈子',
      'reshared_to_circle' => '转发到圈子',
      'mentions_entity' => '提到了这个主页',
      'comment_about_entity' => '评论了这个主页',
      'circle_under_entity' => '圈子围绕这个主页',
      'member_of' => '成员关系',
      'co_tagged' => '共同标签',
      'review_of' => '口碑评价',
      _ => edge.edgeType,
    };
    final source = edge.sourceObjectType.isEmpty
        ? edge.sourceObjectId
        : '${edge.sourceObjectType}:${edge.sourceObjectId}';
    final target = edge.targetObjectType.isEmpty
        ? edge.targetObjectId
        : '${edge.targetObjectType}:${edge.targetObjectId}';
    return '$source · $verb · $target';
  }
}
