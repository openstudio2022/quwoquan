import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 统一可交互交集句渲染器（统一交互子契约 · A–E 横切复用，Phase 0 §20.7）。
///
/// 只读消费云侧 [IntersectionTextSpan] 列表——它是 `primaryText` / `briefText` 的「同一句话
/// 结构化富文本切分」，端侧不在此拼装任何结论句（G2）。
///
/// 降级链（spans → primaryText → 隐藏）：
/// - `spans` 非空：`Text.rich` 逐段渲染；`role=object/count` 且提供了 [onSpanTap] 的片段用
///   低饱和 slogan-accent 蓝（[AppColors.profileSloganAccentLight]/[AppColors.profileSloganAccentDark]）
///   常规字重 + 点击态（命中 [onSpanTap]，轻量、不整句变蓝、也不用高饱和 systemBlue），
///   其余片段为 [AppColors.iosLabel] 常规文本不可点击；
/// - `spans` 为空但 [fallbackText] 非空：渲染纯文本，整行命中 [onFallbackTap]；
/// - 两者皆空：渲染 [SizedBox.shrink]（隐藏）。
///
/// 可点击判定只看「角色 + 是否提供 onSpanTap」，**不再要求 span.target 非空**：
/// `target` 仅决定「默认导航去哪」，而消费方对片段动作拥有最终解释权——典型如
/// 我的交集的 count 片段携带 myIntersections target（进维度下钻列表），
/// 打动模块的 count 片段不依赖 target、由消费方拦截为打开影响明细 sheet。
/// 这样三个角色（object/count）的可点击语义统一，避免「有 onSpanTap 动作却因
/// 无 target 而失去点击态」的矛盾（消费方负责对 target 为空的 object 片段优雅降级）。
///
/// 槽②句内头像（canonical 交集设计）：当某片段携带 [IntersectionTextSpan.visual]
/// 且 `imageUrl` 非空时，在该片段文字**前**以 [WidgetSpan] 渲染一枚行内小头像（不带
/// 文本、PlaceholderAlignment.middle）。它是装饰性视觉，不向句子注入任何字符，因此
/// `join(spans.text) == primaryText` 不变量保持成立；行内头像与其文字共享同一 [onSpanTap]
/// 命中动作（点头像 = 点名字）。
class InteractiveIntersectionText extends StatefulWidget {
  const InteractiveIntersectionText({
    super.key,
    required this.spans,
    required this.fallbackText,
    this.onSpanTap,
    this.onFallbackTap,
    this.baseStyle,
    this.accentFontWeight = AppTypography.regular,
    this.maxLines = 1,
    this.overflow = TextOverflow.ellipsis,
    this.textAlign = TextAlign.start,
  });

  /// 云侧结构化切分；为空触发降级。
  final List<IntersectionTextSpan> spans;

  /// 单通道真相源（primaryText / briefText），spans 缺省时整行降级渲染。
  final String fallbackText;

  /// 命中可点击片段（role=object/count 且 target!=null）。
  final void Function(IntersectionTextSpan span)? onSpanTap;

  /// spans 缺省、整行降级时的点击回调。
  final VoidCallback? onFallbackTap;

  final TextStyle? baseStyle;
  final FontWeight accentFontWeight;
  final int maxLines;
  final TextOverflow overflow;
  final TextAlign textAlign;

  @override
  State<InteractiveIntersectionText> createState() =>
      _InteractiveIntersectionTextState();
}

class _InteractiveIntersectionTextState
    extends State<InteractiveIntersectionText> {
  final List<TapGestureRecognizer> _recognizers = <TapGestureRecognizer>[];

  void _clearRecognizers() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
  }

  @override
  void dispose() {
    _clearRecognizers();
    super.dispose();
  }

  bool _isTappable(IntersectionTextSpan span) =>
      widget.onSpanTap != null &&
      (span.role == 'object' || span.role == 'count');

  @override
  Widget build(BuildContext context) {
    // 每帧重建 recognizer，先释放上一帧，避免泄漏。
    _clearRecognizers();

    final base =
        widget.baseStyle ??
        TextStyle(
          fontSize: AppTypography.iosSubheadline,
          fontWeight: AppTypography.regular,
          height: AppSpacing.textLineHeightFootnote,
          color: AppColors.iosLabel(context),
          letterSpacing: -0.08,
        );

    if (widget.spans.isEmpty) {
      final text = widget.fallbackText.trim();
      if (text.isEmpty) {
        return const SizedBox.shrink();
      }
      final child = Text(
        text,
        maxLines: widget.maxLines,
        overflow: widget.overflow,
        textAlign: widget.textAlign,
        style: base,
      );
      if (widget.onFallbackTap == null) {
        return child;
      }
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onFallbackTap,
        child: child,
      );
    }

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final accent = base.copyWith(
      color: isDark
          ? AppColors.profileSloganAccentDark
          : AppColors.profileSloganAccentLight,
      fontWeight: widget.accentFontWeight,
    );
    // 槽② 行内头像直径：随正文字号缩放，约文字 cap-height 的 ~1.3x，行内对齐居中。
    final inlineAvatarSize =
        (base.fontSize ?? AppTypography.iosSubheadline) + AppSpacing.xs;
    final children = <InlineSpan>[];
    for (final span in widget.spans) {
      final tappable = _isTappable(span);
      final recognizer = tappable
          ? (TapGestureRecognizer()..onTap = () => widget.onSpanTap!(span))
          : null;
      if (recognizer != null) {
        _recognizers.add(recognizer);
      }
      final visual = span.visual;
      if (visual != null && visual.imageUrl.trim().isNotEmpty) {
        children.add(
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Padding(
              padding: EdgeInsets.only(right: AppSpacing.intraGroupXs / 2),
              child: _InlineVisualAvatar(
                visual: visual,
                size: inlineAvatarSize,
                onTap: tappable ? () => widget.onSpanTap!(span) : null,
              ),
            ),
          ),
        );
      }
      children.add(
        TextSpan(
          text: span.text,
          style: tappable ? accent : base,
          recognizer: recognizer,
        ),
      );
    }
    return Text.rich(
      TextSpan(style: base, children: children),
      maxLines: widget.maxLines,
      overflow: widget.overflow,
      textAlign: widget.textAlign,
    );
  }
}

/// 槽② 行内小头像（句内人物/对象视觉，§21.5.1）。
///
/// 圆形（avatar/circleAvatar 等）或小圆角矩形（cover/thumbnail），不带描边/计数，
/// 仅在 [IntersectionTextSpan.visual] 携带 `imageUrl` 时由 [InteractiveIntersectionText]
/// 内联渲染。点击复用所属片段的 onSpanTap（点头像 = 点名字）。
class _InlineVisualAvatar extends StatelessWidget {
  const _InlineVisualAvatar({
    required this.visual,
    required this.size,
    this.onTap,
  });

  final IntersectionVisual visual;
  final double size;
  final VoidCallback? onTap;

  bool get _isCircle {
    switch (visual.assetKind.trim()) {
      case 'avatar':
      case 'circleAvatar':
      case 'emblem':
      case 'logo':
      case 'icon':
        return true;
      default:
        return false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final radius = _isCircle
        ? BorderRadius.circular(size)
        : BorderRadius.circular(AppSpacing.xs);
    final inner = ClipRRect(
      borderRadius: radius,
      child: AppCachedNetworkImage(
        imageUrl: visual.imageUrl.trim(),
        width: size,
        height: size,
        fit: BoxFit.cover,
        cdnPreset: _isCircle ? CdnImagePreset.avatar : CdnImagePreset.thumbnail,
        errorWidget: const SizedBox.shrink(),
      ),
    );
    final label = visual.displayName.trim();
    if (onTap == null) {
      return Semantics(label: label, child: inner);
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(label: label, button: true, child: inner),
    );
  }
}
