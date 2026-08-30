// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016.t4
//
// 文章内嵌图片几何元数据消费（REQ-017）：
// 占位比例只由 manifest 像素宽高派生并 clamp 到版式区间 [3:4, 2:1]，
// 元数据缺席时分页与渲染同取 4:3 后备；缺席图片（URL 未解析）仍预留
// 同尺寸占位框，页数不因状态转换改变；wrap 图缺席降级为全宽正文，
// 文字不得随图丢失。运行时解码尺寸不得进入分页输入。
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_asset.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_flow_layout_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_pagination_engine.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';

const MediaAssetManifestResolver _assetManifestResolver =
    MediaAssetManifestResolver(
      resolveReference: _resolveMediaReference,
      imageCdnBaseUrl: 'https://image.example.test',
    );

String _resolveMediaReference(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) => resolveContentMediaUrl(
  raw,
  gatewayBaseUrl: gatewayBaseUrl,
  imageCdnBaseUrl: imageCdnBaseUrl,
  videoCdnBaseUrl: videoCdnBaseUrl,
);

const double _stageWidth = 390;

final TextStyle _titleStyle = const TextStyle(fontSize: 24, height: 1.4);
final TextStyle _bodyStyle = const TextStyle(fontSize: 17, height: 1.6);

ArticleCanvasMetrics get _metrics => ArticleCanvasMetrics.snapshot();

ArticleDocumentAsset _asset({
  String imageUrl = 'https://image.example.test/a1.webp',
  String imageLayout = 'fullWidth',
  int? width,
  int? height,
}) {
  return ArticleDocumentAsset(
    id: 'a1',
    offset: 0,
    imageUrl: imageUrl,
    imageLayout: imageLayout,
    width: width,
    height: height,
  );
}

/// 单 figure 文档：title + figure（可缺席、可带元数据）+ 一段正文。
ArticleDocumentData _figureDocument({
  String imageUrl = 'https://image.example.test/a1.webp',
  String imageLayout = 'fullWidth',
  int? width,
  int? height,
}) {
  return ArticleDocumentData(
    nodes: <ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'doc_title',
        type: ArticleDocumentNodeType.documentTitle,
        text: '图片几何元数据验证',
      ),
      ArticleDocumentNode(
        id: 'fig_a1',
        type: ArticleDocumentNodeType.figure,
        assetId: 'a1',
        imageUrl: imageUrl,
        imageLayout: imageLayout,
        imageWidth: width,
        imageHeight: height,
      ),
      const ArticleDocumentNode(
        id: 'p_0',
        type: ArticleDocumentNodeType.paragraph,
        text: '湖面在清晨的薄雾里缓慢展开，木船沿着岸线滑行，桨声把水面划出细长的纹路。',
      ),
    ],
  );
}

double _figureRunHeight(ArticleDocumentData document) {
  final runs = ArticleFlowLayoutEngine.computeRuns(
    document: document,
    metrics: _metrics,
    stageWidth: _stageWidth,
    titleStyle: _titleStyle,
    bodyStyle: _bodyStyle,
  );
  return runs
      .where(
        (run) => run.fragment.kind == ArticleLayoutFragmentKind.fullWidthImage,
      )
      .single
      .measuredHeight;
}

ArticleDocumentData _wrapPaginationDocument({
  required int width,
  required int height,
}) {
  return ArticleDocumentData(
    titleStyle: ArticleDocumentTitleStyle.none,
    nodes: <ArticleDocumentNode>[
      ArticleDocumentNode(
        id: 'fig_wrap',
        type: ArticleDocumentNodeType.figure,
        assetId: 'wrap',
        imageUrl: 'https://image.example.test/wrap.webp',
        imageLayout: 'wrapLeft',
        imageWidth: width,
        imageHeight: height,
      ),
      ArticleDocumentNode(
        id: 'p_wrap',
        type: ArticleDocumentNodeType.paragraph,
        text: List<String>.generate(
          36,
          (index) => '第$index段湖岸观察文字用于验证结构分页持续消费图片元数据比例。',
        ).join(),
      ),
    ],
  );
}

ArticleWrapLayoutData _resolveWrapLayoutForPagination(
  ArticleDocumentData document, {
  required bool useMetadataAspectRatio,
  String? body,
}) {
  final asset = document.assets.single;
  final contentWidth = _metrics.contentSizeForStageWidth(_stageWidth).width;
  return resolveArticleWrapLayout(
    ArticleWrapLayoutInput(
      body: body ?? document.body,
      rowContentWidth: contentWidth,
      bodyStyle: _bodyStyle,
      captionText: asset.caption,
      captionStyle: _bodyStyle,
      captionPlaceholderWhenEmpty: false,
      imageLayout: asset.imageLayout,
      figureAspectRatio: useMetadataAspectRatio
          ? resolveArticleFigureAspectRatio(metrics: _metrics, asset: asset)
          : _metrics.fullWidthImageAspectRatio,
      metrics: _metrics,
    ),
  ).layout;
}

double _wrapAssetReservationHeight(ArticleDocumentData document) {
  final wrap = _resolveWrapLayoutForPagination(
    document,
    useMetadataAspectRatio: true,
    body: '',
  );
  final lineHeight = (_bodyStyle.fontSize ?? 17) * (_bodyStyle.height ?? 1.0);
  final occupiedHeight = wrap.figureHeight > wrap.besideHeight
      ? wrap.figureHeight
      : wrap.besideHeight;
  return occupiedHeight + wrap.trailingSpacing + lineHeight;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('占位比例唯一决定函数（REQ-017）', () {
    test('区间内元数据比例原样生效（16:9 横图）', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(width: 1600, height: 900),
      );
      expect(aspect, moreOrLessEquals(16 / 9, epsilon: 1e-9));
    });

    test('竖图元数据超下限 clamp 到 3:4', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(width: 900, height: 1600),
      );
      expect(aspect, moreOrLessEquals(3 / 4, epsilon: 1e-9));
    });

    test('超宽横图元数据超上限 clamp 到 2:1', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(width: 4000, height: 1000),
      );
      expect(aspect, moreOrLessEquals(2.0, epsilon: 1e-9));
    });

    test('元数据缺席时 fullWidth 取 4:3 后备（分页与渲染同源函数）', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(),
      );
      expect(aspect, moreOrLessEquals(4 / 3, epsilon: 1e-9));
    });

    test('单维缺席（只有宽）整体按缺席处理走后备比例', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(width: 1600),
      );
      expect(aspect, moreOrLessEquals(4 / 3, epsilon: 1e-9));
    });

    test('journalCard 元数据缺席走 metrics 声明的 journal 后备比例', () {
      final aspect = resolveArticleFigureAspectRatio(
        metrics: _metrics,
        asset: _asset(imageLayout: 'journalCard'),
      );
      expect(aspect, _metrics.journalImageAspectRatio);
    });
  });

  group('codec 元数据透传（GWT-016）', () {
    test('manifest 像素宽高透传到 figure node 与 assets 投影', () {
      final document = ArticleMarkdownCodec.parseDocument(
        '''
---
title: 元数据透传
---

![竖图](asset://a1)
''',
        assetManifest: const <String, dynamic>{
          'assets': <Object?>[
            <String, Object?>{
              'assetId': 'a1',
              'publicSliceKey': 'media/image/s/post/p1/v1/a1-display.webp',
              'width': 900,
              'height': 1600,
            },
          ],
        },
        assetManifestResolver: _assetManifestResolver,
      );

      final figure = document.nodes.where((node) => node.isFigure).single;
      expect(figure.imageUrl, contains('a1-display.webp'));
      expect(figure.imageWidth, 900);
      expect(figure.imageHeight, 1600);
      final asset = document.assets.single;
      expect(asset.width, 900);
      expect(asset.height, 1600);
      expect(asset.metadataAspectRatio, moreOrLessEquals(900 / 1600));
    });

    test('交付 URL 缺席但声明宽高的资产行保留元数据（缺席态按元数据预留）', () {
      final document = ArticleMarkdownCodec.parseDocument(
        '''
---
title: 缺席保元数据
---

![缺席图](asset://a1)
''',
        assetManifest: const <String, dynamic>{
          'assets': <Object?>[
            <String, Object?>{'assetId': 'a1', 'width': 1600, 'height': 900},
          ],
        },
        assetManifestResolver: _assetManifestResolver,
      );

      final figure = document.nodes.where((node) => node.isFigure).single;
      expect(figure.imageUrl, isEmpty, reason: '缺席不得伪装 URL');
      expect(figure.imageWidth, 1600);
      expect(figure.imageHeight, 900);
    });
  });

  group('分页预留几何（GWT-016）', () {
    test('竖图与横图按元数据获得不同预留高度，差值等于比例差', () {
      final portrait = _figureRunHeight(
        _figureDocument(width: 900, height: 1600),
      );
      final landscape = _figureRunHeight(
        _figureDocument(width: 4000, height: 1000),
      );
      final contentWidth = _metrics.contentSizeForStageWidth(_stageWidth).width;

      expect(portrait, greaterThan(landscape));
      // 同结构文档 spacing 相同：高度差 = contentWidth/clamp(0.5625→3/4)
      // - contentWidth/clamp(4.0→2.0)。
      expect(
        portrait - landscape,
        moreOrLessEquals(
          contentWidth / (3 / 4) - contentWidth / 2.0,
          epsilon: 0.5,
        ),
      );
    });

    test('无元数据时预留高度与显式 4:3 元数据完全相等（后备同源）', () {
      final fallback = _figureRunHeight(_figureDocument());
      final explicit = _figureRunHeight(
        _figureDocument(width: 1200, height: 900),
      );
      expect(fallback, moreOrLessEquals(explicit, epsilon: 1e-6));
    });

    test('wrap 结构分页按元数据比例决定正文截断，不回退固定 4:3', () {
      final document = _wrapPaginationDocument(width: 900, height: 1600);
      final reservationHeight = _wrapAssetReservationHeight(document);
      final metadataLayout = _resolveWrapLayoutForPagination(
        document,
        useMetadataAspectRatio: true,
      );
      final fallbackLayout = _resolveWrapLayoutForPagination(
        document,
        useMetadataAspectRatio: false,
      );
      expect(
        metadataLayout.splitOffset,
        greaterThan(fallbackLayout.splitOffset),
        reason: '竖图元数据应扩大图旁行数，确保用例能区分固定 4:3 后备',
      );

      final firstPage = ArticlePaginationEngine.paginate(
        document: document,
        metrics: _metrics,
        stageWidth: _stageWidth,
        titleStyle: _titleStyle,
        bodyStyle: _bodyStyle,
        contentHeightOverride:
            reservationHeight +
            metadataLayout.trailingSpacing +
            (_bodyStyle.fontSize ?? 17) * (_bodyStyle.height ?? 1.0) * 2,
      ).first;

      expect(firstPage.binding?.bodyRange?.start, 0);
      expect(
        firstPage.binding?.bodyRange?.end,
        metadataLayout.splitOffset,
        reason: '结构分页的 _fitBodyTextForPage 必须消费 manifest 元数据比例',
      );
      expect(
        firstPage.binding?.bodyRange?.end,
        isNot(fallbackLayout.splitOffset),
        reason: '禁止静默回退 metrics.fullWidthImageAspectRatio（4:3）',
      );
    });

    test('缺席图片预留与在场相等，且文章总页数不变（状态转换不重排）', () {
      final present = _figureDocument();
      final absent = _figureDocument(imageUrl: '');

      expect(
        _figureRunHeight(absent),
        moreOrLessEquals(_figureRunHeight(present), epsilon: 1e-6),
        reason: '缺席图片必须预留与在场同尺寸的占位框（GWT-016）',
      );

      final sliceHeight = _metrics.contentSizeForStageWidth(_stageWidth).height;
      final presentPages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
        document: present,
        metrics: _metrics,
        stageWidth: _stageWidth,
        titleStyle: _titleStyle,
        bodyStyle: _bodyStyle,
        viewportSliceHeight: sliceHeight,
      ).length;
      final absentPages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
        document: absent,
        metrics: _metrics,
        stageWidth: _stageWidth,
        titleStyle: _titleStyle,
        bodyStyle: _bodyStyle,
        viewportSliceHeight: sliceHeight,
      ).length;
      expect(absentPages, presentPages, reason: '缺席不得改变文章总页数（GWT-016）');
    });

    test('fragmentless 兼容页保留 manifest 资产身份与宽高', () {
      final document = _figureDocument(imageUrl: '', width: 1600, height: 900);
      final sourcePage = ArticlePageData(
        id: 'fragmentless_page',
        body: document.body,
        contentBlocks: document.contentBlocks,
      );

      final imageRun =
          ArticleFlowLayoutEngine.computeRunsFromPages(
            <ArticlePageData>[sourcePage],
            document: document,
            metrics: _metrics,
            stageWidth: _stageWidth,
            titleStyle: _titleStyle,
            bodyStyle: _bodyStyle,
          ).singleWhere(
            (run) =>
                run.fragment.kind == ArticleLayoutFragmentKind.fullWidthImage,
          );
      final asset = imageRun.fragment.asset!;

      expect(asset.id, 'a1');
      expect(asset.imageUrl, isEmpty);
      expect(asset.width, 1600);
      expect(asset.height, 900);
      expect(asset.metadataAspectRatio, moreOrLessEquals(16 / 9));
      expect(
        imageRun.measuredHeight,
        moreOrLessEquals(
          _metrics.contentSizeForStageWidth(_stageWidth).width / (16 / 9),
          epsilon: 0.5,
        ),
      );
    });

    test('wrap 图缺席降级为全宽正文测量，文字不得随图丢失', () {
      final document = ArticleDocumentData(
        nodes: <ArticleDocumentNode>[
          const ArticleDocumentNode(
            id: 'doc_title',
            type: ArticleDocumentNodeType.documentTitle,
            text: 'wrap 缺席降级验证',
          ),
          const ArticleDocumentNode(
            id: 'fig_w1',
            type: ArticleDocumentNodeType.figure,
            assetId: 'w1',
            imageUrl: '',
            imageLayout: 'wrapLeft',
          ),
          const ArticleDocumentNode(
            id: 'p_0',
            type: ArticleDocumentNodeType.paragraph,
            text: '桨声把水面划出细长的纹路，远处的山脊被光线勾出轮廓，村落的屋顶次第亮起来。',
          ),
        ],
      );
      final runs = ArticleFlowLayoutEngine.computeRuns(
        document: document,
        metrics: _metrics,
        stageWidth: _stageWidth,
        titleStyle: _titleStyle,
        bodyStyle: _bodyStyle,
      );
      final wrapRuns = runs.where(
        (run) => run.fragment.kind == ArticleLayoutFragmentKind.wrapContent,
      );
      expect(wrapRuns, isNotEmpty, reason: '缺席 wrap 图不得在分页源头被剔除');
      final wrapRun = wrapRuns.first;
      expect(
        wrapRun.measuredHeight,
        greaterThan(0),
        reason: 'wrap 缺席必须按降级正文测量，文字高度不得测成 0 而丢字',
      );
      expect(
        articleWrapAbsentFallbackText(wrapRun.fragment),
        contains('桨声'),
        reason: '降级正文必须保留原 wrap 文字',
      );
    });
  });
}
