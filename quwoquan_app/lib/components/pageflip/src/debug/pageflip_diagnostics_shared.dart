import 'package:flutter/material.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

const ArticleTemplatePreset kPageflipDiagnosticsTemplate =
    ArticleTemplatePreset.tech;
const ArticleFontPreset kPageflipDiagnosticsFontPreset = ArticleFontPreset.mono;
const EdgeInsets kPageflipDiagnosticsViewportPadding = EdgeInsets.fromLTRB(
  16,
  16,
  16,
  24,
);

List<ArticlePageData> buildPageflipDiagnosticPages() {
  return <ArticlePageData>[
    _buildDiagnosticPage(
      pageIndex: 0,
      title: 'SEAM TRACE / 01',
      summary:
          'Top-heavy layout with hero image, intro paragraphs, and a dense lower block.',
      imageUrl: 'diagnostic://pageflip/01',
      imageLayout: 'wrapRight',
      caption: 'Figure 01A: current-page anchor.',
      sectionLabel: 'Header / Hero / Footer',
      detailParagraphs: const <String>[
        'This page places landmarks near the top, center, and bottom so a forward flip can be judged by more than a single text row.',
        'When the current page curls, the image and the lower paragraph should stay attached to the same sheet.',
      ],
      bullets: const <String>[
        'top title block stays on current page',
        'hero image remains attached to page 01',
        'bottom paragraph does not leak early',
      ],
    ),
    _buildDiagnosticPage(
      pageIndex: 1,
      title: 'SEAM TRACE / 02',
      summary:
          'Wrapped image layout to expose fold-line behavior in the middle and lower-right areas.',
      imageUrl: 'diagnostic://pageflip/02',
      imageLayout: 'wrapRight',
      caption: 'Figure 02A: wrapped block stays synchronized.',
      sectionLabel: 'Wrap / Fold / Corner',
      detailParagraphs: const <String>[
        'The wrapped image should occupy a clear right-side block while the paragraph continues beside it.',
        'If any region rebounds to the wrong page, the image and neighboring text will diverge immediately.',
      ],
      bullets: const <String>[
        'wrap text and image move together',
        'lower-right reveal belongs to page 03',
        'fold band should not duplicate page 02',
      ],
    ),
    _buildDiagnosticPage(
      pageIndex: 2,
      title: 'SEAM TRACE / 03',
      summary:
          'Center-dense page with section rhythm, full-width image, and a long bottom paragraph.',
      imageUrl: 'diagnostic://pageflip/03',
      imageLayout: 'wrapLeft',
      caption: 'Figure 03A: center-weighted backface check.',
      sectionLabel: 'Center / Caption / Baseline',
      detailParagraphs: const <String>[
        'This page keeps most of its density around the middle so the backface can be judged against recognizable breaks.',
        'If the backface is stretched or projected onto the wrong plane, the caption and following text should look detached.',
      ],
      bullets: const <String>[
        'section title remains crisp on backface',
        'caption sits under the same image block',
        'lower text emerges only after the fold passes',
      ],
    ),
    _buildDiagnosticPage(
      pageIndex: 3,
      title: 'SEAM TRACE / 04',
      summary:
          'Image-forward page with alternating paragraph lengths for front/back identity checks.',
      imageUrl: 'diagnostic://pageflip/04',
      imageLayout: 'wrapRight',
      caption: 'Figure 04A: front/back identity check.',
      sectionLabel: 'Image / Backface / Reveal',
      detailParagraphs: const <String>[
        'The image and short paragraphs give strong shape differences across the page.',
        'This page is useful for spotting whether the revealed next page starts from the correct side of the fold.',
      ],
      bullets: const <String>[
        'front image remains page 04 while curling',
        'revealed page 05 stays on the far side of the fold',
        'no duplicated lower-right patch',
      ],
    ),
    _buildDiagnosticPage(
      pageIndex: 4,
      title: 'SEAM TRACE / 05',
      summary:
          'Closing page with note-like blocks, checklist rows, and a strong bottom marker.',
      imageUrl: 'diagnostic://pageflip/05',
      imageLayout: 'wrapLeft',
      caption: 'Figure 05A: final-page marker.',
      sectionLabel: 'List / Note / Marker',
      detailParagraphs: const <String>[
        'The last page keeps a compact note structure so stale texture is easier to distinguish from real next-page content.',
        'The bottom marker helps confirm whether page identity near the lower edge remains stable.',
      ],
      bullets: const <String>[
        'note block belongs only to page 05',
        'bottom marker remains fixed to the same page',
        'previous page content should not reappear',
      ],
    ),
  ];
}

ArticlePageData _buildDiagnosticPage({
  required int pageIndex,
  required String title,
  required String summary,
  required String imageUrl,
  required String imageLayout,
  required String caption,
  required String sectionLabel,
  required List<String> detailParagraphs,
  required List<String> bullets,
}) {
  return ArticlePageData(
    id: 'diag_$pageIndex',
    title: title,
    body: summary,
    contentBlocks: <ArticleDocumentBlock>[
      ArticleDocumentBlock(
        id: 'diag_${pageIndex}_section',
        type: ArticleDocumentBlockType.sectionTitle,
        text: 'PAGE ${pageIndex + 1} / 5  |  $sectionLabel',
      ),
      ArticleDocumentBlock(
        id: 'diag_${pageIndex}_paragraph_0',
        type: ArticleDocumentBlockType.paragraph,
        text: detailParagraphs[0],
      ),
      ArticleDocumentBlock(
        id: 'diag_${pageIndex}_image',
        type: ArticleDocumentBlockType.image,
        imageUrl: imageUrl,
        imageLayout: imageLayout,
        caption: caption,
      ),
      ArticleDocumentBlock(
        id: 'diag_${pageIndex}_paragraph_1',
        type: ArticleDocumentBlockType.paragraph,
        text: detailParagraphs[1],
      ),
      ...bullets.asMap().entries.map(
        (entry) => ArticleDocumentBlock(
          id: 'diag_${pageIndex}_bullet_${entry.key}',
          type: ArticleDocumentBlockType.bulletItem,
          text: entry.value,
        ),
      ),
    ],
  );
}

class PageflipDiagnosticsParityPage extends StatelessWidget {
  const PageflipDiagnosticsParityPage({
    super.key,
    required this.pages,
    required this.pageIndex,
    required this.metrics,
    this.coverUrl = '',
    this.showFooterPageLabel = false,
  });

  final List<ArticlePageData> pages;
  final int pageIndex;
  final ArticleCanvasMetrics metrics;
  final String coverUrl;
  final bool showFooterPageLabel;

  @override
  Widget build(BuildContext context) {
    final page = pages[pageIndex];
    return ArticlePageShell(
      key: ValueKey<String>('pageflip_widget_diagnostic_page_$pageIndex'),
      template: kPageflipDiagnosticsTemplate,
      fontPreset: kPageflipDiagnosticsFontPreset,
      pageIndex: pageIndex,
      totalPages: pages.length,
      aspectRatio: metrics.aspectRatio,
      outerPadding: metrics.outerPadding,
      contentPadding: metrics.contentPadding,
      headerReservedHeight: metrics.headerReservedHeight,
      footerReservedHeight: metrics.footerReservedHeight,
      variant: ArticlePageShellVariant.readerSheet,
      showIndicator: false,
      footerLabel: showFooterPageLabel
          ? '${pageIndex + 1}/${pages.length}'
          : null,
      child: pageIndex == 0 && coverUrl.trim().isNotEmpty
          ? ArticleFrontispieceView(
              page: page,
              template: kPageflipDiagnosticsTemplate,
              fontPreset: kPageflipDiagnosticsFontPreset,
              coverUrl: coverUrl.trim(),
            )
          : ArticlePageReadOnlyView(
              page: page,
              template: kPageflipDiagnosticsTemplate,
              fontPreset: kPageflipDiagnosticsFontPreset,
              metrics: metrics,
            ),
    );
  }
}
