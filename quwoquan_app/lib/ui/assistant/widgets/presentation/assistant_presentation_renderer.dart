import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_presentation_document.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_presentation_node.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

part 'assistant_presentation_validation.dart';

typedef AssistantPresentationMarkdownBuilder = Widget Function(String markdown);
typedef AssistantPresentationMediaUrlResolver =
    String? Function(AssistantPresentationMediaRefWire media);
typedef AssistantPresentationActionHandler =
    void Function(AssistantActionIntentWire action);
typedef AssistantPresentationActionPredicate =
    bool Function(AssistantActionIntentWire action);
typedef AssistantPresentationFallbackObserver =
    void Function(String reason, AssistantPresentationDocumentWire document);

enum AssistantPresentationViewportClass { compact, standard, expanded }

@immutable
class AssistantPresentationRenderCapabilities {
  const AssistantPresentationRenderCapabilities({
    required this.viewportClass,
    required this.platform,
    required this.darkTheme,
    required this.textScale,
    required this.reducedMotion,
    required this.offline,
    this.mediaEnabled = false,
    this.actionsEnabled = false,
  });

  final AssistantPresentationViewportClass viewportClass;
  final TargetPlatform platform;
  final bool darkTheme;
  final double textScale;
  final bool reducedMotion;
  final bool offline;
  final bool mediaEnabled;
  final bool actionsEnabled;

  static AssistantPresentationRenderCapabilities fromContext(
    BuildContext context, {
    bool mediaEnabled = false,
    bool actionsEnabled = false,
    bool offline = false,
  }) {
    final media = MediaQuery.of(context);
    final width = media.size.width;
    final viewportClass = width < AppSpacing.markdownCompactBreakpoint
        ? AssistantPresentationViewportClass.compact
        : width < AppSpacing.expandedBreakpoint
        ? AssistantPresentationViewportClass.standard
        : AssistantPresentationViewportClass.expanded;
    return AssistantPresentationRenderCapabilities(
      viewportClass: viewportClass,
      platform: defaultTargetPlatform,
      darkTheme: Theme.of(context).brightness == Brightness.dark,
      textScale:
          media.textScaler.scale(AppTypography.base) / AppTypography.base,
      reducedMotion: media.disableAnimations,
      offline: offline,
      mediaEnabled: mediaEnabled,
      actionsEnabled: actionsEnabled,
    );
  }

  Set<AssistantPresentationNodeKind> get supportedNodeKinds => {
    AssistantPresentationNodeKind.card,
    AssistantPresentationNodeKind.column,
    AssistantPresentationNodeKind.row,
    AssistantPresentationNodeKind.grid,
    AssistantPresentationNodeKind.list,
    AssistantPresentationNodeKind.carousel,
    AssistantPresentationNodeKind.markdown,
    AssistantPresentationNodeKind.text,
    AssistantPresentationNodeKind.icon,
    AssistantPresentationNodeKind.badge,
    AssistantPresentationNodeKind.divider,
    AssistantPresentationNodeKind.stat,
    AssistantPresentationNodeKind.keyValue,
    AssistantPresentationNodeKind.entityReference,
    AssistantPresentationNodeKind.sourceReference,
    AssistantPresentationNodeKind.timeline,
    AssistantPresentationNodeKind.comparisonTable,
    AssistantPresentationNodeKind.sourceList,
    AssistantPresentationNodeKind.callout,
    if (mediaEnabled && !offline) ...{
      AssistantPresentationNodeKind.media,
      AssistantPresentationNodeKind.mediaGallery,
    },
    if (actionsEnabled) ...{
      AssistantPresentationNodeKind.actionGroup,
      AssistantPresentationNodeKind.choiceChips,
      AssistantPresentationNodeKind.dateTimeInput,
      AssistantPresentationNodeKind.confirmationCard,
    },
  };
}

/// Flutter-native renderer for the canonical Assistant presentation AST.
///
/// The server supplies semantics only. This registry owns every concrete
/// widget, color, spacing, typography and interaction binding. Any unsupported
/// or invalid document deterministically falls back to the same answer text.
class AssistantPresentationRenderer extends StatefulWidget {
  const AssistantPresentationRenderer({
    super.key,
    required this.document,
    required this.markdownBuilder,
    required this.textColor,
    this.mediaUrlResolver,
    this.onAction,
    this.canHandleAction,
    this.onFallback,
    this.offline = false,
  });

  final AssistantPresentationDocumentWire document;
  final AssistantPresentationMarkdownBuilder markdownBuilder;
  final Color textColor;
  final AssistantPresentationMediaUrlResolver? mediaUrlResolver;
  final AssistantPresentationActionHandler? onAction;
  final AssistantPresentationActionPredicate? canHandleAction;
  final AssistantPresentationFallbackObserver? onFallback;
  final bool offline;

  @override
  State<AssistantPresentationRenderer> createState() =>
      _AssistantPresentationRendererState();
}

class _AssistantPresentationRendererState
    extends State<AssistantPresentationRenderer> {
  String _runtimeFallbackReason = '';
  String _observedFallbackReason = '';

  @override
  void didUpdateWidget(covariant AssistantPresentationRenderer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.document.templateRef != widget.document.templateRef ||
        oldWidget.document.revision != widget.document.revision ||
        oldWidget.document.dataDigest != widget.document.dataDigest) {
      _runtimeFallbackReason = '';
      _observedFallbackReason = '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final capabilities = AssistantPresentationRenderCapabilities.fromContext(
      context,
      mediaEnabled: widget.mediaUrlResolver != null,
      actionsEnabled: widget.onAction != null,
      offline: widget.offline,
    );
    final validation = _validateDocument(
      widget.document,
      capabilities: capabilities,
      mediaUrlResolver: widget.mediaUrlResolver,
      hasActionHandler: widget.onAction != null,
      canHandleAction: widget.canHandleAction,
    );
    final fallbackReason = _runtimeFallbackReason.isNotEmpty
        ? _runtimeFallbackReason
        : validation.reason;
    if (fallbackReason.isNotEmpty) {
      _observeFallback(fallbackReason);
      return _buildFallback();
    }
    final byParent = <String, List<AssistantPresentationNodeWire>>{};
    for (final node in widget.document.nodes) {
      byParent.putIfAbsent(node.parentNodeId, () => []).add(node);
    }
    for (final children in byParent.values) {
      children.sort((left, right) {
        final order = left.order.compareTo(right.order);
        return order != 0 ? order : left.nodeId.compareTo(right.nodeId);
      });
    }
    final registry = _AssistantPresentationRendererRegistry(
      context: context,
      capabilities: capabilities,
      textColor: widget.textColor,
      markdownBuilder: widget.markdownBuilder,
      mediaUrlResolver: widget.mediaUrlResolver,
      onAction: widget.onAction,
      onMediaFailed: _handleMediaFailed,
      byParent: byParent,
    );
    return Semantics(container: true, child: registry.render(validation.root!));
  }

  Widget _buildFallback() {
    final markdown = widget.document.fallbackMarkdown.trim();
    if (markdown.isNotEmpty) {
      return widget.markdownBuilder(markdown);
    }
    return SelectableText(
      widget.document.fallbackPlainText.trim(),
      style: TextStyle(
        color: widget.textColor,
        fontSize: AppTypography.base,
        height: AppTypography.lineHeightRelaxed,
      ),
    );
  }

  void _handleMediaFailed(Object _) {
    if (_runtimeFallbackReason.isNotEmpty || !mounted) return;
    setState(() => _runtimeFallbackReason = 'media_load_failed');
  }

  void _observeFallback(String reason) {
    if (_observedFallbackReason == reason) return;
    _observedFallbackReason = reason;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _observedFallbackReason != reason) return;
      widget.onFallback?.call(reason, widget.document);
    });
  }
}

class _AssistantPresentationRendererRegistry {
  const _AssistantPresentationRendererRegistry({
    required this.context,
    required this.capabilities,
    required this.textColor,
    required this.markdownBuilder,
    required this.mediaUrlResolver,
    required this.onAction,
    required this.onMediaFailed,
    required this.byParent,
  });

  final BuildContext context;
  final AssistantPresentationRenderCapabilities capabilities;
  final Color textColor;
  final AssistantPresentationMarkdownBuilder markdownBuilder;
  final AssistantPresentationMediaUrlResolver? mediaUrlResolver;
  final AssistantPresentationActionHandler? onAction;
  final void Function(Object error) onMediaFailed;
  final Map<String, List<AssistantPresentationNodeWire>> byParent;

  Widget render(AssistantPresentationNodeWire node) {
    final children = byParent[node.nodeId] ?? const [];
    final rendered = switch (node.kind) {
      AssistantPresentationNodeKind.card => _card(node, children),
      AssistantPresentationNodeKind.column => _column(node, children),
      AssistantPresentationNodeKind.row => _row(node, children),
      AssistantPresentationNodeKind.grid => _grid(node, children),
      AssistantPresentationNodeKind.list => _list(node, children),
      AssistantPresentationNodeKind.carousel => _carousel(node, children),
      AssistantPresentationNodeKind.markdown => markdownBuilder(node.body),
      AssistantPresentationNodeKind.text => _text(node),
      AssistantPresentationNodeKind.icon => _icon(node),
      AssistantPresentationNodeKind.media => _media(node),
      AssistantPresentationNodeKind.badge => _badge(node),
      AssistantPresentationNodeKind.divider => _divider(node),
      AssistantPresentationNodeKind.stat => _stat(node),
      AssistantPresentationNodeKind.keyValue => _keyValue(node),
      AssistantPresentationNodeKind.entityReference => _reference(node),
      AssistantPresentationNodeKind.sourceReference => _reference(node),
      AssistantPresentationNodeKind.timeline => _timeline(node, children),
      AssistantPresentationNodeKind.comparisonTable => _comparisonTable(node),
      AssistantPresentationNodeKind.sourceList => _list(node, children),
      AssistantPresentationNodeKind.mediaGallery => _carousel(node, children),
      AssistantPresentationNodeKind.callout => _callout(node, children),
      AssistantPresentationNodeKind.actionGroup => _actionGroup(node, children),
      AssistantPresentationNodeKind.choiceChips => _choiceChips(node, children),
      AssistantPresentationNodeKind.dateTimeInput => _actionTile(node),
      AssistantPresentationNodeKind.confirmationCard => _confirmation(
        node,
        children,
      ),
      AssistantPresentationNodeKind.unknown => const SizedBox.shrink(),
    };
    final accessibility = node.accessibility;
    if (accessibility.excludeFromSemantics) {
      return ExcludeSemantics(child: rendered);
    }
    if (accessibility.semanticLabel.isEmpty &&
        accessibility.semanticHint.isEmpty) {
      return rendered;
    }
    return Semantics(
      label: accessibility.semanticLabel,
      hint: accessibility.semanticHint,
      child: rendered,
    );
  }

  Widget _card(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    final tone = _toneColor(node.style.tone);
    final colors = _themeColors;
    return Container(
      margin: EdgeInsets.only(bottom: _spacing(node.style.spacingRole)),
      padding: EdgeInsets.all(_densityPadding(node.style.density)),
      decoration: BoxDecoration(
        color: node.style.variant == 'filled'
            ? tone.withValues(alpha: capabilities.darkTheme ? 0.18 : 0.08)
            : colors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: tone.withValues(alpha: 0.22)),
      ),
      child: _contentAndChildren(node, children),
    );
  }

  Widget _column(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    return Column(
      crossAxisAlignment: _crossAxis(node.style.alignment),
      mainAxisSize: MainAxisSize.min,
      children: [
        ..._headingWidgets(node),
        ..._spacedChildren(children.map(render).toList(growable: false)),
      ],
    );
  }

  Widget _row(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    if (capabilities.viewportClass ==
            AssistantPresentationViewportClass.compact ||
        capabilities.textScale > 1.3) {
      return _column(node, children);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        ..._headingWidgets(node),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: children
              .map(
                (child) => Expanded(
                  flex: child.style.responsiveSpan,
                  child: Padding(
                    padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                    child: render(child),
                  ),
                ),
              )
              .toList(growable: false),
        ),
      ],
    );
  }

  Widget _grid(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    final columns = switch (capabilities.viewportClass) {
      AssistantPresentationViewportClass.compact => 1,
      AssistantPresentationViewportClass.standard => 2,
      AssistantPresentationViewportClass.expanded => 3,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        GridView.count(
          crossAxisCount: columns,
          crossAxisSpacing: AppSpacing.interGroupSm,
          mainAxisSpacing: AppSpacing.interGroupSm,
          childAspectRatio: node.style.aspectRatio > 0
              ? node.style.aspectRatio
              : 1,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: children.map(render).toList(growable: false),
        ),
      ],
    );
  }

  Widget _list(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        ...children.indexed.map(
          (entry) => Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: AppSpacing.lg,
                  child: Text('${entry.$1 + 1}.', style: _bodyStyle(node)),
                ),
                Expanded(child: render(entry.$2)),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _carousel(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    final itemWidth =
        capabilities.viewportClass == AssistantPresentationViewportClass.compact
        ? AppSpacing.twoHundredTwenty
        : AppSpacing.threeHundredTwenty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: children
                .map(
                  (child) => SizedBox(
                    width: itemWidth,
                    child: Padding(
                      padding: EdgeInsets.only(right: AppSpacing.interGroupSm),
                      child: render(child),
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ),
      ],
    );
  }

  Widget _text(AssistantPresentationNodeWire node) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    mainAxisSize: MainAxisSize.min,
    children: _headingWidgets(node),
  );

  Widget _icon(AssistantPresentationNodeWire node) {
    final token = (node.data['iconToken'] as String?)?.trim() ?? '';
    return Icon(
      _iconData(token),
      color: _toneColor(node.style.tone),
      size: AppSpacing.iconMedium,
      semanticLabel: node.accessibility.semanticLabel.isEmpty
          ? null
          : node.accessibility.semanticLabel,
    );
  }

  Widget _media(AssistantPresentationNodeWire node) {
    final media = node.media!;
    final url = mediaUrlResolver!(media)!.trim();
    final ratio = node.style.aspectRatio > 0
        ? node.style.aspectRatio
        : media.width > 0 && media.height > 0
        ? media.width / media.height
        : 1.0;
    return Semantics(
      image: true,
      label: media.alt,
      child: AspectRatio(
        aspectRatio: ratio,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          child: AppCachedNetworkImage(
            imageUrl: url,
            fit: BoxFit.cover,
            cdnPreset: CdnImagePreset.inline,
            onLoadFailed: onMediaFailed,
            errorWidget: ColoredBox(
              color: _themeColors.backgroundTertiary,
              child: Center(
                child: Icon(
                  CupertinoIcons.photo,
                  color: _themeColors.foregroundSecondary,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _badge(AssistantPresentationNodeWire node) => Container(
    padding: EdgeInsets.symmetric(
      horizontal: AppSpacing.intraGroupLg,
      vertical: AppSpacing.intraGroupXs,
    ),
    decoration: BoxDecoration(
      color: _toneColor(node.style.tone).withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
    ),
    child: Text(
      node.body.isNotEmpty ? node.body : node.title,
      style: _bodyStyle(node).copyWith(fontSize: AppTypography.sm),
    ),
  );

  Widget _divider(AssistantPresentationNodeWire node) => Divider(
    height: AppSpacing.interGroupMd,
    thickness: AppSpacing.hairline,
    color: _toneColor(node.style.tone).withValues(alpha: 0.24),
  );

  Widget _stat(AssistantPresentationNodeWire node) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    mainAxisSize: MainAxisSize.min,
    children: [
      if (node.body.isNotEmpty)
        Text(
          node.body,
          style: _bodyStyle(node).copyWith(
            fontSize: AppTypography.xxl,
            fontWeight: AppTypography.medium,
          ),
        ),
      if (node.title.isNotEmpty)
        Text(
          node.title,
          style: _bodyStyle(
            node,
          ).copyWith(color: _themeColors.foregroundSecondary),
        ),
    ],
  );

  Widget _keyValue(AssistantPresentationNodeWire node) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (node.title.isNotEmpty)
        Expanded(
          child: Text(
            node.title,
            style: _bodyStyle(
              node,
            ).copyWith(color: _themeColors.foregroundSecondary),
          ),
        ),
      if (node.body.isNotEmpty)
        Expanded(
          child: Text(
            node.body,
            textAlign: TextAlign.end,
            style: _bodyStyle(node),
          ),
        ),
    ],
  );

  Widget _reference(AssistantPresentationNodeWire node) {
    final content = _contentAndChildren(node, const []);
    if (node.action == null) return content;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: () => onAction?.call(node.action!),
      child: DefaultTextStyle.merge(style: _bodyStyle(node), child: content),
    );
  }

  Widget _timeline(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        ...children.map(
          (child) => Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.interGroupSm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: EdgeInsets.only(top: AppSpacing.xs),
                  child: Icon(
                    CupertinoIcons.circle_filled,
                    size: AppSpacing.intraGroupSm,
                    color: _toneColor(child.style.tone),
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupLg),
                Expanded(child: render(child)),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _comparisonTable(AssistantPresentationNodeWire node) {
    final columns = _stringList(node.data['columns']);
    final rows = _mapList(node.data['rows']);
    if (columns.isEmpty || rows.isEmpty) {
      return _text(node);
    }
    final textStyle = _bodyStyle(node).copyWith(fontSize: AppTypography.sm);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Table(
            defaultColumnWidth: const IntrinsicColumnWidth(),
            border: TableBorder.all(
              color: _themeColors.foregroundTertiary.withValues(alpha: 0.22),
              width: AppSpacing.hairline,
            ),
            children: [
              TableRow(
                children: columns
                    .map(
                      (column) => Padding(
                        padding: EdgeInsets.all(AppSpacing.intraGroupSm),
                        child: Text(
                          column,
                          style: textStyle.copyWith(
                            fontWeight: AppTypography.medium,
                          ),
                        ),
                      ),
                    )
                    .toList(growable: false),
              ),
              ...rows.map(
                (row) => TableRow(
                  children: columns
                      .map(
                        (column) => Padding(
                          padding: EdgeInsets.all(AppSpacing.intraGroupSm),
                          child: Text(
                            row[column]?.toString() ?? '',
                            style: textStyle,
                          ),
                        ),
                      )
                      .toList(growable: false),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _callout(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) {
    final tone = _toneColor(node.style.tone);
    return Container(
      padding: EdgeInsets.all(_densityPadding(node.style.density)),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border(
          left: BorderSide(color: tone, width: AppSpacing.two),
        ),
      ),
      child: _contentAndChildren(node, children),
    );
  }

  Widget _actionGroup(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) => Wrap(
    spacing: AppSpacing.intraGroupSm,
    runSpacing: AppSpacing.intraGroupSm,
    children: [
      if (node.action != null) _actionButton(node),
      ...children.map(_actionButton),
    ],
  );

  Widget _choiceChips(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) => Wrap(
    spacing: AppSpacing.intraGroupSm,
    runSpacing: AppSpacing.intraGroupSm,
    children: [
      if (node.action != null) _choiceChip(node),
      ...children.map(_choiceChip),
    ],
  );

  Widget _actionTile(AssistantPresentationNodeWire node) => CupertinoButton(
    padding: EdgeInsets.symmetric(
      horizontal: AppSpacing.containerSm,
      vertical: AppSpacing.intraGroupSm,
    ),
    minimumSize: const Size.square(AppSpacing.minInteractiveSize),
    onPressed: node.action == null ? null : () => onAction?.call(node.action!),
    child: Row(
      children: [
        Icon(CupertinoIcons.calendar, color: _toneColor(node.style.tone)),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(child: _text(node)),
      ],
    ),
  );

  Widget _confirmation(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) => Container(
    padding: EdgeInsets.all(_densityPadding(node.style.density)),
    decoration: BoxDecoration(
      color: _themeColors.backgroundSecondary,
      borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      border: Border.all(
        color: _toneColor(node.style.tone).withValues(alpha: 0.22),
      ),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ..._headingWidgets(node),
        ..._spacedChildren(children.map(render).toList(growable: false)),
        if (node.action != null) ...[
          SizedBox(height: AppSpacing.interGroupSm),
          _actionButton(node),
        ],
      ],
    ),
  );

  Widget _actionButton(AssistantPresentationNodeWire node) {
    return CupertinoButton.filled(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: node.action == null
          ? null
          : () => onAction?.call(node.action!),
      child: Text(node.title.isNotEmpty ? node.title : node.body),
    );
  }

  Widget _choiceChip(AssistantPresentationNodeWire node) {
    return ActionChip(
      label: Text(node.title.isNotEmpty ? node.title : node.body),
      onPressed: node.action == null
          ? null
          : () => onAction?.call(node.action!),
    );
  }

  Widget _contentAndChildren(
    AssistantPresentationNodeWire node,
    List<AssistantPresentationNodeWire> children,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    mainAxisSize: MainAxisSize.min,
    children: [
      ..._headingWidgets(node),
      ..._spacedChildren(children.map(render).toList(growable: false)),
    ],
  );

  List<Widget> _headingWidgets(AssistantPresentationNodeWire node) => [
    if (node.title.isNotEmpty)
      Padding(
        padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
        child: SelectableText(
          node.title,
          style: _bodyStyle(node).copyWith(
            fontWeight: node.style.emphasis == 'strong'
                ? AppTypography.semiBold
                : AppTypography.medium,
          ),
        ),
      ),
    if (node.body.isNotEmpty)
      SelectableText(node.body, style: _bodyStyle(node)),
  ];

  List<Widget> _spacedChildren(List<Widget> children) => children.indexed
      .map(
        (entry) => Padding(
          padding: EdgeInsets.only(
            top: entry.$1 == 0 ? AppSpacing.zero : AppSpacing.intraGroupSm,
          ),
          child: entry.$2,
        ),
      )
      .toList(growable: false);

  TextStyle _bodyStyle(AssistantPresentationNodeWire node) => TextStyle(
    color: node.style.emphasis == 'subtle'
        ? _themeColors.foregroundSecondary
        : textColor,
    fontSize: AppTypography.base,
    height: AppTypography.lineHeightRelaxed,
  );

  AppColorsTheme get _themeColors =>
      AppColorsTheme(isDark: capabilities.darkTheme);

  Color _toneColor(AssistantPresentationTone tone) => switch (tone) {
    AssistantPresentationTone.neutral => _themeColors.foregroundSecondary,
    AssistantPresentationTone.informative => AppColors.info,
    AssistantPresentationTone.positive => AppColors.success,
    AssistantPresentationTone.caution => AppColors.warning,
    AssistantPresentationTone.critical => AppColors.error,
  };

  double _densityPadding(AssistantPresentationDensity density) =>
      switch (density) {
        AssistantPresentationDensity.compact => AppSpacing.containerXs,
        AssistantPresentationDensity.standard => AppSpacing.containerSm,
        AssistantPresentationDensity.immersive => AppSpacing.containerMd,
      };

  double _spacing(String role) => switch (role) {
    'none' => AppSpacing.zero,
    'related' => AppSpacing.intraGroupSm,
    'section' => AppSpacing.interGroupMd,
    'screen' => AppSpacing.interGroupLg,
    _ => AppSpacing.intraGroupSm,
  };

  CrossAxisAlignment _crossAxis(String alignment) => switch (alignment) {
    'center' => CrossAxisAlignment.center,
    'end' => CrossAxisAlignment.end,
    'space_between' || 'start' => CrossAxisAlignment.start,
    _ => CrossAxisAlignment.start,
  };
}

class _PresentationValidation {
  const _PresentationValidation({required this.reason, this.root});

  final String reason;
  final AssistantPresentationNodeWire? root;
}

_PresentationValidation _validateDocument(
  AssistantPresentationDocumentWire document, {
  required AssistantPresentationRenderCapabilities capabilities,
  required AssistantPresentationMediaUrlResolver? mediaUrlResolver,
  required bool hasActionHandler,
  required AssistantPresentationActionPredicate? canHandleAction,
}) {
  if (document.revision <= 0 ||
      document.nodes.isEmpty ||
      document.nodes.length > 128 ||
      document.rootNodeId.isEmpty ||
      !_digestPattern.hasMatch(document.templateDigest) ||
      !_digestPattern.hasMatch(document.dataDigest) ||
      !document.templateRef.endsWith('@${document.templateDigest}') ||
      DateTime.tryParse(document.committedAt) == null) {
    return const _PresentationValidation(reason: 'invalid_document');
  }
  final byId = <String, AssistantPresentationNodeWire>{};
  for (final node in document.nodes) {
    if (node.nodeId.isEmpty || byId.containsKey(node.nodeId)) {
      return const _PresentationValidation(reason: 'invalid_tree');
    }
    byId[node.nodeId] = node;
    if (!capabilities.supportedNodeKinds.contains(node.kind)) {
      return const _PresentationValidation(reason: 'unsupported_node');
    }
    if (node.order < 0 ||
        node.title.runes.length > 512 ||
        node.body.runes.length > 20000 ||
        node.binding.isNotEmpty ||
        !_validStyle(node.style)) {
      return const _PresentationValidation(reason: 'invalid_node');
    }
    if (node.media != null) {
      final media = node.media!;
      final url = mediaUrlResolver?.call(media)?.trim() ?? '';
      if (media.mediaAssetId.isEmpty ||
          media.alt.isEmpty ||
          media.provenanceRef.isEmpty ||
          url.isEmpty) {
        return const _PresentationValidation(reason: 'media_unavailable');
      }
    }
    if (node.action != null &&
        (!hasActionHandler ||
            !_validAction(node.action!) ||
            canHandleAction?.call(node.action!) == false)) {
      return const _PresentationValidation(reason: 'action_unavailable');
    }
  }
  final root = byId[document.rootNodeId];
  if (root == null || root.parentNodeId.isNotEmpty) {
    return const _PresentationValidation(reason: 'invalid_tree');
  }
  for (final node in document.nodes) {
    if (node.nodeId == document.rootNodeId) continue;
    if (!byId.containsKey(node.parentNodeId)) {
      return const _PresentationValidation(reason: 'invalid_tree');
    }
    final visited = <String>{node.nodeId};
    var cursor = node;
    var depth = 1;
    while (cursor.parentNodeId.isNotEmpty) {
      if (!visited.add(cursor.parentNodeId) || depth > 12) {
        return const _PresentationValidation(reason: 'invalid_tree');
      }
      cursor = byId[cursor.parentNodeId]!;
      depth++;
    }
  }
  return _PresentationValidation(reason: '', root: root);
}
