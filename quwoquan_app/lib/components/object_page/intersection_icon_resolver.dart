import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/impact_help_type_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
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
      case 'placeHere':
        return CupertinoIcons.map_pin_ellipse;
      case 'circle':
        return CupertinoIcons.person_3_fill;
      case 'people':
        return CupertinoIcons.person_2_fill;
      case 'contact':
        return CupertinoIcons.person_crop_circle_badge_checkmark;
      case 'followHere':
        return CupertinoIcons.person_2_square_stack_fill;
      case 'viewing':
        return CupertinoIcons.eye_fill;
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
      case 'attention':
        return CupertinoIcons.star_fill;
      // 影响 helpType → iconKey 闭集（registry.helpTypes[].iconKey ∪ cascadePath 兜底）。
      // glyph 由端设计层定；闭集覆盖由 verify_impact_help_type_registry.py 守护。
      case 'connect':
        return CupertinoIcons.link;
      case 'communityJoin':
        return CupertinoIcons.person_3_fill;
      case 'decisionCompass':
        return CupertinoIcons.location_north_fill;
      case 'knowledgeRead':
        return CupertinoIcons.book_fill;
      case 'spreadShare':
        return CupertinoIcons.arrowshape_turn_up_right_fill;
      case 'audienceReach':
        return CupertinoIcons.eye_fill;
      case 'cascadePath':
        return CupertinoIcons.link;
      default:
        return null;
    }
  }

  /// sourceRef（注册表标准 kind）→ iconKey：codegen [IntersectionKindMetadata] 单一真相源
  /// （registry.kinds.iconKey）。端不再硬编码 kind→iconKey switch（§23 去桥接）。
  static String _iconKeyForSourceRef(String sourceRef) =>
      IntersectionKindMetadata.of(sourceRef.trim())?.iconKey ?? '';

  /// dimension（5 维闭集）→ iconKey 末级回退：codegen [intersectionIconKeyByDimension]
  /// 单一真相源（registry.iconKeyByDimension）。端不再硬编码 dimension→iconKey switch（§23 去桥接）。
  static String _iconKeyForDimension(String dimension) =>
      intersectionIconKeyByDimension[dimension.trim()] ?? '';

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

  static String _toneKey({
    String iconKey = '',
    String sourceRef = '',
    String dimension = '',
  }) {
    final viaSource = _iconKeyForSourceRef(sourceRef);
    final resolvedKey = iconKey.trim().isNotEmpty
        ? iconKey.trim()
        : viaSource.trim().isNotEmpty
        ? viaSource
        : _iconKeyForDimension(dimension);
    // 交集 iconKey → tone：codegen intersectionVisualToneByIconKey 单一真相源
    // （registry.visualToneByIconKey）；端不再硬编码交集色调 switch。
    final intersectionTone = intersectionVisualToneByIconKey[resolvedKey];
    if (intersectionTone != null) {
      return intersectionTone;
    }
    // 影响（impact）iconKey → tone：codegen impactToneByIconKey 单一真相源
    // （impact_help_type_registry.toneByIconKey）；端不再硬编码 impact 色调 switch（§23 去桥接）。
    return impactToneByIconKey[resolvedKey] ?? impactDefaultTone;
  }

  static Color toneColor(
    BuildContext context, {
    String iconKey = '',
    String sourceRef = '',
    String dimension = '',
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return switch (_toneKey(
      iconKey: iconKey,
      sourceRef: sourceRef,
      dimension: dimension,
    )) {
      'tea' =>
        isDark
            ? AppColors.profileIntersectionTeaDark
            : AppColors.profileIntersectionTeaLight,
      'sage' =>
        isDark
            ? AppColors.profileIntersectionSageDark
            : AppColors.profileIntersectionSageLight,
      'clay' =>
        isDark
            ? AppColors.profileIntersectionClayDark
            : AppColors.profileIntersectionClayLight,
      'mist' =>
        isDark
            ? AppColors.profileIntersectionMistDark
            : AppColors.profileIntersectionMistLight,
      _ =>
        isDark
            ? AppColors.profileIntersectionStoneDark
            : AppColors.profileIntersectionStoneLight,
    };
  }
}

/// 槽① 类型图标件（§21.5.1 单行交集卡 leading）。
///
/// 渲染在结论句最前，语义来自 [IntersectionIconResolver]；柔和圆形底 + 低饱和语义色，
/// 避免把交集资产误读为主品牌 CTA，不与句内 inline 头像（槽②）抢视觉重心。
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
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final iconColor = IntersectionIconResolver.toneColor(
      context,
      iconKey: iconKey,
      sourceRef: sourceRef,
      dimension: dimension,
    );
    final fill = iconColor.withValues(alpha: isDark ? 0.20 : 0.13);
    return Container(
      width: diameter,
      height: diameter,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: fill,
        shape: BoxShape.circle,
        border: Border.all(
          color: iconColor.withValues(alpha: isDark ? 0.22 : 0.18),
          width: AppSpacing.hairline,
        ),
      ),
      child: Icon(
        IntersectionIconResolver.resolve(
          iconKey: iconKey,
          sourceRef: sourceRef,
          dimension: dimension,
        ),
        size: diameter * 0.5,
        color: iconColor,
      ),
    );
  }
}
