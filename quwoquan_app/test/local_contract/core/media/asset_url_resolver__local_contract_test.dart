import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/asset_url_resolver.dart';

void main() {
  group('AssetUrlResolver', () {
    test('resolves canonical publicSliceKey through CDN base', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://img.example.com',
        gatewayBaseUrl: 'https://api.example.com',
      );

      final urls = resolver.resolveManifestUrls(const <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'cover',
            'publicSliceKey': 'media/image/s/article/post-1/v1/cover.jpg',
          },
        ],
      });

      expect(
        urls['cover'],
        'https://img.example.com/media/image/s/article/post-1/v1/cover.jpg',
      );
    });

    test('prefers cdnUrl over publicSliceKey when both are present', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://cdn.example.com',
      );

      final urls = resolver.resolveManifestUrls(const <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'detail',
            'cdnUrl':
                'https://cdn.example.com/media/image/s/article/post-1/v1/detail.png',
            'publicSliceKey':
                'media/image/s/article/post-1/v1/detail-fallback.png',
          },
        ],
      });

      expect(
        urls['detail'],
        'https://cdn.example.com/media/image/s/article/post-1/v1/detail.png',
      );
    });

    test('selects media variants by scene and gates original access', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://cdn.example.com',
      );

      final variantsById = resolver.resolveManifestVariants(const <
        String,
        Object?
      >{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'cover',
            'kind': 'image',
            'cdnUrl':
                'https://cdn.example.com/media/image/s/article/post-1/v1/fallback.jpg',
            'variants': <String, Object?>{
              'thumbnail': <String, Object?>{
                'profile': 'thumbnail',
                'cdnUrl':
                    'https://cdn.example.com/media/image/s/article/post-1/v1/cover-thumb.webp',
                'publicSliceKey':
                    'media/image/s/article/post-1/v1/cover-thumb.webp',
                'sourceSha256':
                    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'width': 320,
              },
              'display': <String, Object?>{
                'profile': 'display',
                'cdnUrl':
                    'https://cdn.example.com/media/image/s/article/post-1/v1/cover-display.webp',
                'publicSliceKey':
                    'media/image/s/article/post-1/v1/cover-display.webp',
                'sourceSha256':
                    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'width': 960,
              },
              'full': <String, Object?>{
                'profile': 'full',
                'cdnUrl':
                    'https://cdn.example.com/media/image/s/article/post-1/v1/cover-full.webp',
                'publicSliceKey':
                    'media/image/s/article/post-1/v1/cover-full.webp',
                'sourceSha256':
                    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'width': 2048,
              },
              'original': <String, Object?>{
                'profile': 'original',
                'sourceSha256':
                    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'requiresAccess': true,
              },
            },
          },
        ],
      });

      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.thumbnail,
        ),
        'https://cdn.example.com/media/image/s/article/post-1/v1/cover-thumb.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.display,
        ),
        'https://cdn.example.com/media/image/s/article/post-1/v1/cover-display.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.full,
        ),
        'https://cdn.example.com/media/image/s/article/post-1/v1/cover-full.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.original,
        ),
        'https://cdn.example.com/media/image/s/article/post-1/v1/cover-full.webp',
      );

      final defaultUrls = resolver.resolveManifestUrls(const <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'cover',
            'variants': <String, Object?>{
              'display': <String, Object?>{
                'cdnUrl':
                    'https://cdn.example.com/media/image/s/article/post-1/v1/cover-display.webp',
              },
              'original': <String, Object?>{
                'cdnUrl':
                    'https://cdn.example.com/media/image/s/article/post-1/v1/original.jpg',
                'requiresAccess': true,
              },
            },
          },
        ],
      });

      expect(
        defaultUrls['cover'],
        'https://cdn.example.com/media/image/s/article/post-1/v1/cover-display.webp',
      );
      expect(defaultUrls['cover'], isNot(contains('original.jpg')));
    });
  });
}
