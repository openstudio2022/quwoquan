// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';

/// 文章素材清单的交付声明必须一路透传到内嵌图消费点（DEC-033）。
///
/// 缺了任一环，research 相位的文章内嵌图就会按公开 URL 直连：私有资产没有
/// 公开地址，结果是整片打不开，而这在本地契约里不会红。
void main() {
  Map<String, Object?> manifestWith({
    required String accessMode,
    String publicSliceKey = '',
  }) {
    return <String, Object?>{
      'assets': <Object?>[
        <String, Object?>{
          'assetId': 'asset-inline-1',
          'kind': 'image',
          'accessMode': accessMode,
          if (publicSliceKey.isNotEmpty) 'publicSliceKey': publicSliceKey,
          'width': 1200,
          'height': 800,
        },
      ],
    };
  }

  test('manifest 的 accessMode 进入解析结果', () {
    final variants = ArticleMarkdownCodec.resolveArticleAssetManifestVariants(
      manifestWith(accessMode: 'signed_grant'),
    );
    expect(variants['asset-inline-1']?.accessMode, 'signed_grant');
  });

  test('私有资产没有公开 URL 也必须保留，不得按无 URL 丢弃', () {
    final variants = ArticleMarkdownCodec.resolveArticleAssetManifestVariants(
      manifestWith(accessMode: 'signed_grant'),
    );
    expect(
      variants.containsKey('asset-inline-1'),
      isTrue,
      reason: '私有行被丢弃会让 research 相位的内嵌图整片消失',
    );
  });

  test('契约缺席保持空串，不猜成 public', () {
    final variants = ArticleMarkdownCodec.resolveArticleAssetManifestVariants(
      <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'asset-legacy-1',
            'kind': 'image',
            'publicSliceKey': 'media/image/s/legacy/v1/a.jpg',
          },
        ],
      },
    );
    expect(variants['asset-legacy-1']?.accessMode, '');
  });

  test('accessMode 一路透传到 ArticleDocumentAsset', () {
    const node = ArticleDocumentNode(
      id: 'block-1',
      type: ArticleDocumentNodeType.figure,
      assetId: 'asset-inline-1',
      accessMode: 'signed_grant',
      imageUrl: '',
    );
    final document = ArticleDocumentData(nodes: <ArticleDocumentNode>[node]);
    expect(document.assets, isNotEmpty);
    expect(document.assets.single.accessMode, 'signed_grant');
    // 资产身份必须在场：私有资产靠它换短签，缺了就只剩判否。
    expect(document.assets.single.id, 'asset-inline-1');
  });

  test('MediaAssetVariants 默认 accessMode 为缺席态', () {
    const variants = MediaAssetVariants(
      assetId: 'a',
      kind: 'image',
      variants: <String, MediaAssetVariant>{},
    );
    expect(variants.accessMode, '');
  });
}
