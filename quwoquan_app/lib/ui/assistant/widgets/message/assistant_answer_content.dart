// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `runArtifacts` / cardPayload 等开放 JSON 与 Markdown 解析。

import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class AssistantAnswerContent extends StatelessWidget {
  const AssistantAnswerContent({
    super.key,
    required this.transcriptRow,
    required this.content,
    required this.textColor,
    this.answerBlocks = const <AssistantAnswerDisplayBlock>[],
    this.onReferenceTap,
  });

  final AssistantTranscriptTimelineRow transcriptRow;
  final String content;
  final Color textColor;
  final List<AssistantAnswerDisplayBlock> answerBlocks;
  final void Function(AssistantCitation reference)? onReferenceTap;

  static final RegExp _citationLabelPattern = RegExp(r'^\[?(\d+)\]?$');
  static final RegExp _gfmTableBlockRe = RegExp(
    r'((?:^|\n)\|[^\n]+\|\s*\n\|[\s:|-]+\|\s*\n(?:\|[^\n]+\|\s*\n?)*)',
    multiLine: true,
  );

  @override
  Widget build(BuildContext context) {
    final references = _resolveReferenceItemsFromTranscriptRow(transcriptRow);
    final cleaned = content.trimRight();
    final visibleBlocks = answerBlocks
        .where(_hasVisibleAnswerBlock)
        .toList(growable: false);
    if (cleaned.isEmpty && visibleBlocks.isEmpty && references.isEmpty) {
      return const SizedBox.shrink();
    }
    final textStyle = TextStyle(
      fontSize: AppTypography.base,
      fontWeight: AppTypography.regular,
      color: textColor,
      height: AppTypography.lineHeightRelaxed,
    );
    final linkColor = textColor.withValues(alpha: 0.86);
    // `MarkdownStyleSheet.fromTheme` requires `textTheme.bodyMedium?.fontSize != null`;
    // on current Flutter/M3 builds that can still be null. Use the package's
    // Cupertino path (asserts `textTheme.textStyle.fontSize`) — aligned with iOS UI.
    final cupertino = CupertinoTheme.of(context);
    final CupertinoThemeData markdownCupertinoTheme =
        cupertino.textTheme.textStyle.fontSize != null
        ? cupertino
        : cupertino.copyWith(
            textTheme: cupertino.textTheme.copyWith(
              textStyle: cupertino.textTheme.textStyle.copyWith(
                fontSize: AppTypography.iosBody,
              ),
            ),
          );
    final mdStyle =
        MarkdownStyleSheet.fromCupertinoTheme(markdownCupertinoTheme).copyWith(
          p: textStyle,
          pPadding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
          h1: textStyle.copyWith(
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.medium,
            height: AppTypography.bodyLineHeight,
          ),
          h1Padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
          h2: textStyle.copyWith(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.medium,
          ),
          h2Padding: EdgeInsets.only(bottom: AppSpacing.xs),
          h3: textStyle.copyWith(
            fontSize: AppTypography.base,
            fontWeight: AppTypography.regular,
          ),
          h3Padding: EdgeInsets.only(bottom: AppSpacing.xs),
          strong: textStyle.copyWith(fontWeight: AppTypography.regular),
          em: textStyle.copyWith(fontStyle: FontStyle.italic),
          a: textStyle.copyWith(
            color: linkColor,
            fontWeight: AppTypography.regular,
            decoration: TextDecoration.underline,
            decorationColor: linkColor.withValues(alpha: 0.4),
          ),
          listBullet: textStyle,
          listIndent: AppSpacing.lg,
          listBulletPadding: EdgeInsets.only(
            right: AppSpacing.xs,
            top: AppSpacing.xs / 2,
          ),
          blockquote: textStyle.copyWith(
            color: textColor.withValues(alpha: 0.88),
          ),
          blockquotePadding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          blockquoteDecoration: BoxDecoration(
            color: linkColor.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            border: Border.all(color: linkColor.withValues(alpha: 0.12)),
          ),
          code: textStyle.copyWith(color: textColor, fontFamily: 'monospace'),
          codeblockPadding: EdgeInsets.all(AppSpacing.containerSm),
          codeblockDecoration: BoxDecoration(
            color: textColor.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          horizontalRuleDecoration: BoxDecoration(
            border: Border(
              top: BorderSide(color: textColor.withValues(alpha: 0.08)),
            ),
          ),
          tableColumnWidth: const IntrinsicColumnWidth(),
          tableCellsPadding: EdgeInsets.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.xs / 2,
          ),
          tableBorder: TableBorder.all(
            color: textColor.withValues(alpha: 0.08),
          ),
          tableHead: textStyle.copyWith(fontWeight: AppTypography.medium),
          tableBody: textStyle,
        );
    final children = visibleBlocks.isNotEmpty
        ? _buildTypedBlocks(
            context: context,
            blocks: visibleBlocks,
            markdownHostTheme: markdownCupertinoTheme,
            mdStyle: mdStyle,
            textStyle: textStyle,
            linkColor: linkColor,
            references: references,
          )
        : _buildMarkdownSegments(
            context: context,
            cleaned: cleaned,
            markdownHostTheme: markdownCupertinoTheme,
            mdStyle: mdStyle,
            textStyle: textStyle,
            linkColor: linkColor,
            references: references,
          );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    );
  }

  List<Widget> _buildTypedBlocks({
    required BuildContext context,
    required List<AssistantAnswerDisplayBlock> blocks,
    required CupertinoThemeData markdownHostTheme,
    required MarkdownStyleSheet mdStyle,
    required TextStyle textStyle,
    required Color linkColor,
    required List<_AssistantReferenceItem> references,
  }) {
    return blocks
        .map((block) {
          switch (block.kind) {
            case DisplayBlockKind.markdown:
              return _safeMarkdownBody(
                markdownText: block.body.trim(),
                markdownHostTheme: markdownHostTheme,
                styleSheet: mdStyle,
                textStyle: textStyle,
                references: references,
                linkColor: linkColor,
              );
            case DisplayBlockKind.bulletList:
            case DisplayBlockKind.numberedList:
            case DisplayBlockKind.referenceList:
              return _buildListBlock(
                block: block,
                textStyle: textStyle,
                textColor: textColor,
              );
            case DisplayBlockKind.callout:
              return _buildCalloutBlock(
                block: block,
                textStyle: textStyle,
                linkColor: linkColor,
              );
            case DisplayBlockKind.paragraph:
            case DisplayBlockKind.unknown:
              return _buildParagraphBlock(block: block, textStyle: textStyle);
          }
        })
        .toList(growable: false);
  }

  List<Widget> _buildMarkdownSegments({
    required BuildContext context,
    required String cleaned,
    required CupertinoThemeData markdownHostTheme,
    required MarkdownStyleSheet mdStyle,
    required TextStyle textStyle,
    required Color linkColor,
    required List<_AssistantReferenceItem> references,
  }) {
    final segments = _MarkdownSegment.parse(cleaned);
    return segments
        .map((segment) {
          if (!segment.isCard) {
            return _safeMarkdownBody(
              markdownText: segment.content,
              markdownHostTheme: markdownHostTheme,
              styleSheet: mdStyle,
              textStyle: textStyle,
              references: references,
              linkColor: linkColor,
            );
          }
          return Container(
            margin: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
            padding: EdgeInsets.all(AppSpacing.containerSm),
            decoration: BoxDecoration(
              color: AppColors.primaryColor.withValues(alpha: 0.06),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: AppColors.primaryColor.withValues(alpha: 0.16),
              ),
            ),
            child: _safeMarkdownBody(
              markdownText: segment.toCardMarkdown(),
              markdownHostTheme: markdownHostTheme,
              styleSheet: mdStyle,
              textStyle: textStyle,
              references: references,
              linkColor: linkColor,
            ),
          );
        })
        .toList(growable: false);
  }

  Widget _buildParagraphBlock({
    required AssistantAnswerDisplayBlock block,
    required TextStyle textStyle,
  }) {
    final title = block.title.trim();
    final body = block.body.trim();
    final children = <Widget>[
      if (title.isNotEmpty)
        Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.one),
          child: SelectableText(
            title,
            style: textStyle.copyWith(fontWeight: AppTypography.regular),
          ),
        ),
      if (body.isNotEmpty)
        Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
          child: SelectableText(body, style: textStyle),
        ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: children,
    );
  }

  Widget _buildListBlock({
    required AssistantAnswerDisplayBlock block,
    required TextStyle textStyle,
    required Color textColor,
  }) {
    final title = block.title.trim();
    final items = block.items
        .map(_displayItemText)
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    final useNumbers =
        block.kind == DisplayBlockKind.numberedList ||
        block.listStyle == DisplayListStyle.numbered;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.one),
              child: SelectableText(
                title,
                style: textStyle.copyWith(fontWeight: AppTypography.regular),
              ),
            ),
          if (block.body.trim().isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.one),
              child: SelectableText(block.body.trim(), style: textStyle),
            ),
          ...items.asMap().entries.map((entry) {
            final marker = useNumbers ? '${entry.key + 1}.' : '•';
            return Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.one),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: AppSpacing.lg,
                    child: Text(
                      marker,
                      style: textStyle.copyWith(color: textColor),
                    ),
                  ),
                  Expanded(
                    child: SelectableText(entry.value, style: textStyle),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildCalloutBlock({
    required AssistantAnswerDisplayBlock block,
    required TextStyle textStyle,
    required Color linkColor,
  }) {
    final title = block.title.trim();
    final body = block.body.trim();
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      decoration: BoxDecoration(
        color: linkColor.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(color: linkColor.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.one),
              child: SelectableText(
                title,
                style: textStyle.copyWith(fontWeight: AppTypography.regular),
              ),
            ),
          if (body.isNotEmpty) SelectableText(body, style: textStyle),
        ],
      ),
    );
  }

  Widget _safeMarkdownBody({
    required String markdownText,
    required CupertinoThemeData markdownHostTheme,
    required MarkdownStyleSheet styleSheet,
    required TextStyle textStyle,
    required List<_AssistantReferenceItem> references,
    required Color linkColor,
  }) {
    void onMarkdownLinkTap(String text, String? href, String title) {
      final url = (href ?? '').trim();
      if (url.isEmpty) return;
      final citation = _citationForTap(
        references: references,
        text: text,
        href: url,
        fallbackTitle: title,
      );
      onReferenceTap?.call(citation);
    }

    try {
      final tableMatches = _gfmTableBlockRe.allMatches(markdownText).toList();
      if (tableMatches.isEmpty) {
        return CupertinoTheme(
          data: markdownHostTheme,
          child: MarkdownBody(
            data: markdownText,
            selectable: true,
            // Library always merges with kFallbackStyle; default null uses
            // Material.fromTheme and asserts when bodyMedium.fontSize is null
            // (common under CupertinoPageScaffold + transparent Material).
            styleSheetTheme: MarkdownStyleSheetBaseTheme.cupertino,
            styleSheet: styleSheet,
            builders: <String, MarkdownElementBuilder>{
              'a': _AssistantLinkBuilder(
                references: references,
                linkColor: linkColor,
                onReferenceTap: onReferenceTap,
              ),
            },
            onTapLink: onMarkdownLinkTap,
          ),
        );
      }

      final children = <Widget>[];
      var cursor = 0;
      for (final match in tableMatches) {
        if (match.start > cursor) {
          final before = markdownText.substring(cursor, match.start).trim();
          if (before.isNotEmpty) {
            children.add(
              CupertinoTheme(
                data: markdownHostTheme,
                child: MarkdownBody(
                  data: before,
                  selectable: true,
                  styleSheetTheme: MarkdownStyleSheetBaseTheme.cupertino,
                  styleSheet: styleSheet,
                  builders: <String, MarkdownElementBuilder>{
                    'a': _AssistantLinkBuilder(
                      references: references,
                      linkColor: linkColor,
                      onReferenceTap: onReferenceTap,
                    ),
                  },
                  onTapLink: onMarkdownLinkTap,
                ),
              ),
            );
          }
        }
        final tableText = match.group(0)!.trim();
        children.add(
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: CupertinoTheme(
              data: markdownHostTheme,
              child: MarkdownBody(
                data: tableText,
                selectable: true,
                styleSheetTheme: MarkdownStyleSheetBaseTheme.cupertino,
                styleSheet: styleSheet,
                builders: <String, MarkdownElementBuilder>{
                  'a': _AssistantLinkBuilder(
                    references: references,
                    linkColor: linkColor,
                    onReferenceTap: onReferenceTap,
                  ),
                },
                onTapLink: onMarkdownLinkTap,
              ),
            ),
          ),
        );
        cursor = match.end;
      }
      if (cursor < markdownText.length) {
        final after = markdownText.substring(cursor).trim();
        if (after.isNotEmpty) {
          children.add(
            CupertinoTheme(
              data: markdownHostTheme,
              child: MarkdownBody(
                data: after,
                selectable: true,
                styleSheetTheme: MarkdownStyleSheetBaseTheme.cupertino,
                styleSheet: styleSheet,
                builders: <String, MarkdownElementBuilder>{
                  'a': _AssistantLinkBuilder(
                    references: references,
                    linkColor: linkColor,
                    onReferenceTap: onReferenceTap,
                  ),
                },
                onTapLink: onMarkdownLinkTap,
              ),
            ),
          );
        }
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: children,
      );
    } catch (_) {
      return SelectableText(markdownText, style: textStyle);
    }
  }

  List<_AssistantReferenceItem> _resolveReferenceItemsFromTranscriptRow(
    AssistantTranscriptTimelineRow row,
  ) {
    return switch (row) {
      AssistantAnswerTranscriptRow r => _resolveReferenceItemsFromAnswerParts(
        runArtifactsMap: r.runArtifacts,
        uiReferences: r.uiReferences,
      ),
      _ => const <_AssistantReferenceItem>[],
    };
  }

  static List<_AssistantReferenceItem> _resolveReferenceItemsFromAnswerParts({
    required Map<String, dynamic> runArtifactsMap,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final items = <_AssistantReferenceItem>[];
    final runArtifacts = _resolveRunArtifactsFromMap(runArtifactsMap);
    final bindings =
        runArtifacts?.answerEvidenceBindings ?? const <AnswerEvidenceBinding>[];
    if (bindings.isNotEmpty) {
      for (var index = 0; index < bindings.length; index++) {
        final binding = bindings[index];
        if (binding.url.trim().isEmpty) continue;
        items.add(
          _AssistantReferenceItem(
            index: index + 1,
            title: binding.title.trim().isNotEmpty
                ? binding.title.trim()
                : binding.url,
            url: binding.url.trim(),
            source: binding.source.trim(),
            snippet: binding.snippet.trim(),
            label: binding.label.trim(),
          ),
        );
      }
    }
    if (items.isNotEmpty) {
      return items;
    }
    for (var index = 0; index < uiReferences.length; index++) {
      final reference = uiReferences[index];
      final url = (reference['url'] as String?)?.trim() ?? '';
      if (url.isEmpty) continue;
      items.add(
        _AssistantReferenceItem(
          index: index + 1,
          title: (reference['title'] as String?)?.trim().isNotEmpty == true
              ? (reference['title'] as String).trim()
              : url,
          url: url,
          source: (reference['source'] as String?)?.trim() ?? '',
          snippet: (reference['snippet'] as String?)?.trim() ?? '',
          label: '[${index + 1}]',
        ),
      );
    }
    return items;
  }

  static RunArtifacts? _resolveRunArtifactsFromMap(Map<String, dynamic> raw) {
    if (raw.isEmpty) return null;
    try {
      return parseRunArtifacts(raw);
    } catch (_) {
      return null;
    }
  }

  static AssistantCitation _citationForTap({
    required List<_AssistantReferenceItem> references,
    required String text,
    required String href,
    required String fallbackTitle,
  }) {
    final matched = _matchReference(
      references: references,
      text: text,
      href: href,
    );
    if (matched != null) {
      return matched.toCitation();
    }
    final title = text.trim().isNotEmpty ? text.trim() : fallbackTitle;
    return AssistantCitation(url: href, title: title);
  }

  static _AssistantReferenceItem? _matchReference({
    required List<_AssistantReferenceItem> references,
    required String text,
    required String href,
  }) {
    final normalizedText = text.trim();
    final labelMatch = _citationLabelPattern.firstMatch(normalizedText);
    if (labelMatch != null) {
      final index = int.tryParse(labelMatch.group(1) ?? '');
      if (index != null) {
        for (final reference in references) {
          if (reference.index == index) {
            return reference;
          }
        }
      }
    }
    for (final reference in references) {
      if (reference.url == href) {
        return reference;
      }
    }
    return null;
  }
}

class _AssistantLinkBuilder extends MarkdownElementBuilder {
  _AssistantLinkBuilder({
    required this.references,
    required this.linkColor,
    required this.onReferenceTap,
  });

  final List<_AssistantReferenceItem> references;
  final Color linkColor;
  final void Function(AssistantCitation reference)? onReferenceTap;

  @override
  Widget? visitElementAfterWithContext(
    BuildContext context,
    md.Element element,
    TextStyle? preferredStyle,
    TextStyle? parentStyle,
  ) {
    final href = (element.attributes['href'] ?? '').trim();
    final text = element.textContent.trim();
    if (href.isEmpty || text.isEmpty) {
      return null;
    }
    final matched = AssistantAnswerContent._matchReference(
      references: references,
      text: text,
      href: href,
    );
    if (matched != null &&
        AssistantAnswerContent._citationLabelPattern.hasMatch(text)) {
      return _AssistantCitationChip(
        reference: matched,
        onTap: onReferenceTap == null
            ? null
            : () => onReferenceTap!(matched.toCitation()),
      );
    }
    return GestureDetector(
      onTap: onReferenceTap == null
          ? null
          : () => onReferenceTap!(
              AssistantAnswerContent._citationForTap(
                references: references,
                text: text,
                href: href,
                fallbackTitle: text,
              ),
            ),
      child: Text(
        text,
        style: (preferredStyle ?? parentStyle ?? const TextStyle()).copyWith(
          color: linkColor,
          fontWeight: AppTypography.regular,
          decoration: TextDecoration.underline,
          decorationColor: linkColor.withValues(alpha: 0.4),
        ),
      ),
    );
  }
}

class _AssistantCitationChip extends StatelessWidget {
  const _AssistantCitationChip({required this.reference, this.onTap});

  final _AssistantReferenceItem reference;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final textColor = AppColors.iosSecondaryLabel(
      context,
    ).withValues(alpha: 0.56);
    return Transform.translate(
      offset: const Offset(0, -3),
      child: GestureDetector(
        key: ValueKey<String>('assistant_reference_chip_${reference.index}'),
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.one),
          child: Text(
            '[${reference.index}]',
            style: TextStyle(
              fontSize: AppTypography.xsPlus,
              color: textColor,
              fontWeight: AppTypography.regular,
              height: AppSpacing.textLineHeightDense,
            ),
          ),
        ),
      ),
    );
  }
}

class _AssistantReferenceItem {
  const _AssistantReferenceItem({
    required this.index,
    required this.title,
    required this.url,
    required this.source,
    required this.snippet,
    required this.label,
  });

  final int index;
  final String title;
  final String url;
  final String source;
  final String snippet;
  final String label;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'index': index,
      'title': title,
      'url': url,
      'source': source,
      'snippet': snippet,
      'label': label,
    };
  }

  AssistantCitation toCitation() {
    return AssistantCitation(
      url: url,
      title: title,
      source: source,
      snippet: snippet,
    );
  }
}

bool _hasVisibleAnswerBlock(AssistantAnswerDisplayBlock block) {
  return block.title.trim().isNotEmpty ||
      block.body.trim().isNotEmpty ||
      block.items.any(
        (item) => item.title.trim().isNotEmpty || item.body.trim().isNotEmpty,
      );
}

String _displayItemText(AssistantDisplayItem item) {
  final title = item.title.trim();
  final body = item.body.trim();
  if (title.isNotEmpty && body.isNotEmpty) {
    return '$title：$body';
  }
  return title.isNotEmpty ? title : body;
}

class _MarkdownSegment {
  const _MarkdownSegment._({
    required this.content,
    required this.isCard,
    this.cardType = '',
    this.cardPayload = const <String, dynamic>{},
  });

  final String content;
  final bool isCard;
  final String cardType;
  final Map<String, dynamic> cardPayload;

  static const Set<String> _supportedCardTypes = <String>{
    'compare',
    'trend',
    'diagram',
  };

  factory _MarkdownSegment.text(String content) =>
      _MarkdownSegment._(content: content, isCard: false);

  factory _MarkdownSegment.hidden() =>
      const _MarkdownSegment._(content: '', isCard: false);

  factory _MarkdownSegment.card({
    required String cardType,
    required String payload,
  }) {
    final type = cardType.trim().toLowerCase();
    if (!_supportedCardTypes.contains(type)) {
      return _MarkdownSegment.hidden();
    }
    final decoded = _tryDecode(payload);
    if (decoded == null || decoded.isEmpty) {
      return _MarkdownSegment.hidden();
    }
    return _MarkdownSegment._(
      content: payload,
      isCard: true,
      cardType: type,
      cardPayload: decoded,
    );
  }

  static List<_MarkdownSegment> parse(String raw) {
    if (!raw.contains('```card:')) {
      return <_MarkdownSegment>[
        _MarkdownSegment.text(raw.replaceAll('🔗[', '[')),
      ];
    }
    final sanitizedRaw = _stripDanglingCardFence(raw.replaceAll('🔗[', '['));
    final regex = RegExp(r'```card:([a-zA-Z0-9_-]+)\n([\s\S]*?)```');
    final segments = <_MarkdownSegment>[];
    var index = 0;
    for (final match in regex.allMatches(sanitizedRaw)) {
      if (match.start > index) {
        segments.add(
          _MarkdownSegment.text(sanitizedRaw.substring(index, match.start)),
        );
      }
      final type = (match.group(1) ?? '').trim();
      final payload = (match.group(2) ?? '').trim();
      segments.add(_MarkdownSegment.card(cardType: type, payload: payload));
      index = match.end;
    }
    if (index < sanitizedRaw.length) {
      segments.add(_MarkdownSegment.text(sanitizedRaw.substring(index)));
    }
    return segments.where((seg) => seg.content.trim().isNotEmpty).toList();
  }

  static String _stripDanglingCardFence(String raw) {
    final start = raw.indexOf('```card:');
    if (start < 0) return raw;
    final end = raw.indexOf('```', start + 8);
    if (end >= 0) return raw;
    return raw.substring(0, start).trimRight();
  }

  String toCardMarkdown() {
    if (!isCard || cardPayload.isEmpty) return content;
    final title = (cardPayload['title'] as String?)?.trim();
    final lines = <String>[
      '### ${title?.isNotEmpty == true ? title! : _fallbackTitle()}',
    ];
    if (cardType == 'diagram') {
      final mermaid = (cardPayload['mermaid'] as String?)?.trim() ?? '';
      if (mermaid.isNotEmpty) {
        lines
          ..add('```mermaid')
          ..add(mermaid)
          ..add('```');
      }
    }
    cardPayload.forEach((key, value) {
      if (key == 'title' || key == 'mermaid') return;
      lines.add('- **$key**: ${_valueText(value)}');
    });
    return lines.join('\n');
  }

  String _fallbackTitle() {
    switch (cardType) {
      case 'compare':
        return '对比卡片';
      case 'trend':
        return '趋势卡片';
      case 'diagram':
        return '结构图';
      default:
        return cardType;
    }
  }

  static Map<String, dynamic>? _tryDecode(String payload) {
    try {
      final decoded = jsonDecode(payload);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return decoded.cast<String, dynamic>();
      return null;
    } catch (_) {
      return null;
    }
  }

  static String _valueText(Object? value) {
    if (value == null) return '';
    if (value is num || value is bool || value is String) {
      return value.toString();
    }
    return jsonEncode(value);
  }
}
