import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/impact_help_type_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 交集类型图标语义解析器（canonical 交集设计 · A–E 横切复用）。
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
    String tone = '',
  }) {
    // 云侧直出色号优先（IntersectionReason.tone）。云侧只指派色板 token 名，
    // 具体色值由端持 light/dark 成对调色板决定——同一色值在明暗两种模式下明度是
    // 反的，下发色值必然在某一模式下不可读。给新 kind 指派已有色调因此零发版。
    final explicit = tone.trim();
    if (explicit.isNotEmpty) {
      return explicit;
    }
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
    String tone = '',
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return switch (_toneKey(
      iconKey: iconKey,
      sourceRef: sourceRef,
      dimension: dimension,
      tone: tone,
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
    this.tone = '',
    this.assetUrl = '',
    this.size,
  });

  final String iconKey;
  final String sourceRef;
  final String dimension;

  /// 云侧指派的色板 token 名（`IntersectionReason.tone`）；空则按 iconKey 查本地表。
  final String tone;

  /// 云侧下发的远程图标资源（`IntersectionReason.typeVisual.imageUrl`，alpha 蒙版图）。
  /// 空、加载中或加载失败一律退回本地 glyph，冷缓存与断网表现与改造前一致。
  final String assetUrl;

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
      tone: tone,
    );
    final fill = iconColor.withValues(alpha: isDark ? 0.20 : 0.13);
    final glyphSize = diameter * 0.5;
    final glyph = Icon(
      IntersectionIconResolver.resolve(
        iconKey: iconKey,
        sourceRef: sourceRef,
        dimension: dimension,
      ),
      size: glyphSize,
      color: iconColor,
    );
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
      child: _glyphOrRemote(glyph, glyphSize, iconColor),
    );
  }

  Widget _glyphOrRemote(Widget glyph, double glyphSize, Color iconColor) {
    final url = assetUrl.trim();
    if (url.isEmpty) return glyph;
    // 远程图标是 alpha 蒙版图：用 srcIn 把 tone 刷进不透明像素，让远程新图标与
    // 圆底填充/描边保持同一套设计语言，而不是变成一枚全彩贴纸。
    return ColorFiltered(
      colorFilter: ColorFilter.mode(iconColor, BlendMode.srcIn),
      child: AppCachedNetworkImage(
        imageUrl: url,
        width: glyphSize,
        height: glyphSize,
        fit: BoxFit.contain,
        cdnPreset: CdnImagePreset.avatar,
        placeholder: glyph,
        errorWidget: glyph,
      ),
    );
  }
}
