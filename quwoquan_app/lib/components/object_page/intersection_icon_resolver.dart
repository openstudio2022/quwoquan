import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 交集类型图标语义解析器（架构基线 v2 §21.5.2 · A–E 横切复用）。
///
/// 唯一真相源是云侧下发的 `iconKey`（注册表 `intersection_kind_registry.iconKey`
/// 与 author/circle impact 的 `iconKey`）。端只做「语义键 → 设计系统图标」映射，
/// 禁止在业务/页面代码里写 `switch(sourceRef)` 自造第二套图标规则。
///
/// 当 `iconKey` 缺省时按降级链回退：`sourceRef`（注册表标准 kind）→ `dimension`（5 维闭集）
/// → 通用占位，保证旧数据/灰度期不空图标。
class IntersectionIconResolver {
  const IntersectionIconResolver._();

  /// §21.5.2 交集 iconKey → 图标闭集。未知键返回 null（由上层走回退）。
  static IconData? _iconForKey(String iconKey) {
    switch (iconKey.trim()) {
      case 'place':
        return CupertinoIcons.location_solid;
      case 'circle':
        return CupertinoIcons.person_3_fill;
      case 'people':
        return CupertinoIcons.person_2_fill;
      case 'alumni':
        return CupertinoIcons.book_solid;
      case 'work':
        return CupertinoIcons.briefcase_fill;
      case 'discussion':
        return CupertinoIcons.chat_bubble_2_fill;
      case 'share':
        return CupertinoIcons.arrowshape_turn_up_right_fill;
      case 'like':
        return CupertinoIcons.heart_fill;
      case 'interest':
        return CupertinoIcons.sparkles;
      // 影响 helpType → iconKey 闭集
      case 'connect':
        return CupertinoIcons.link;
      case 'compass':
        return CupertinoIcons.location_north_fill;
      case 'read':
        return CupertinoIcons.book_fill;
      default:
        return null;
    }
  }

  /// sourceRef（注册表标准 kind）→ iconKey 回退映射（与 §21.5.2 表对齐）。
  static String _iconKeyForSourceRef(String sourceRef) {
    switch (sourceRef.trim()) {
      case 'coVisitedEntity':
      case 'followeeVisited':
      case 'coWishlistedEntity':
        return 'place';
      case 'sharedCircle':
      case 'coMemberCircle':
        return 'circle';
      case 'sharedFollowees':
      case 'commonFollower':
      case 'commonContact':
      case 'followeeInObject':
      case 'followeeViewing':
        return 'people';
      case 'sameSchool':
      case 'sameDepartment':
      case 'sameMajor':
      case 'sameCohort':
      case 'alumni':
      case 'alumniHere':
        return 'alumni';
      case 'sameCompany':
      case 'sameTeam':
      case 'sameIndustry':
      case 'colleagueHere':
      case 'coCreatedContent':
        return 'work';
      case 'sharedDiscussion':
      case 'coCommented':
      case 'followeeDiscussedThis':
        return 'discussion';
      case 'coSharedContent':
        return 'share';
      case 'coLiked':
        return 'like';
      case 'sharedTagSample':
      case 'sharedEntityAttention':
        return 'interest';
      default:
        return '';
    }
  }

  /// dimension（5 维闭集）→ iconKey 末级回退。
  static String _iconKeyForDimension(String dimension) {
    switch (dimension.trim()) {
      case 'location':
        return 'place';
      case 'content':
        return 'discussion';
      case 'relationship':
        return 'people';
      case 'identity':
        return 'alumni';
      case 'interest':
        return 'interest';
      default:
        return '';
    }
  }

  /// 解析交集/影响行的类型图标（降级链 iconKey → sourceRef → dimension → 通用占位）。
  static IconData resolve({
    String iconKey = '',
    String sourceRef = '',
    String dimension = '',
  }) {
    final direct = _iconForKey(iconKey);
    if (direct != null) {
      return direct;
    }
    final viaSource = _iconForKey(_iconKeyForSourceRef(sourceRef));
    if (viaSource != null) {
      return viaSource;
    }
    final viaDimension = _iconForKey(_iconKeyForDimension(dimension));
    if (viaDimension != null) {
      return viaDimension;
    }
    return CupertinoIcons.link;
  }
}

/// 槽① 类型图标件（§21.5.1 单行交集卡 leading）。
///
/// 渲染在结论句最前，语义来自 [IntersectionIconResolver]；柔和圆形底 + accent 图标，
/// 弱化但可识别，不与句内 inline 头像（槽②）抢视觉重心。
class IntersectionTypeIcon extends StatelessWidget {
  const IntersectionTypeIcon({
    super.key,
    this.iconKey = '',
    this.sourceRef = '',
    this.dimension = '',
    this.size,
  });

  final String iconKey;
  final String sourceRef;
  final String dimension;
  final double? size;

  @override
  Widget build(BuildContext context) {
    final diameter = size ?? AppSpacing.avatarUserSm;
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      width: diameter,
      height: diameter,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        shape: BoxShape.circle,
      ),
      child: Icon(
        IntersectionIconResolver.resolve(
          iconKey: iconKey,
          sourceRef: sourceRef,
          dimension: dimension,
        ),
        size: diameter * 0.5,
        color: accent,
      ),
    );
  }
}
