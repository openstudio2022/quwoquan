import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/asset_url_resolver.dart';

void main() {
  group('AssetUrlResolver', () {
    test('resolves asset manifest objectKey through CDN base', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://img.example.com',
        gatewayBaseUrl: 'https://api.example.com',
      );

      final urls = resolver.resolveManifestUrls(const <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'cover',
            'objectKey':
                'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
          },
        ],
      });

      expect(
        urls['cover'],
        'https://img.example.com/media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
      );
    });

    test('prefers cdnUrl over objectKey when both are present', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://img.example.com',
      );

      final urls = resolver.resolveManifestUrls(const <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'detail',
            'cdnUrl': 'https://cdn.example.com/detail.png',
            'objectKey':
                'media/objects/sha256/bb/bb/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png',
          },
        ],
      });

      expect(urls['detail'], 'https://cdn.example.com/detail.png');
    });

    test('selects media variants by scene and gates original access', () {
      const resolver = AssetUrlResolver(
        imageCdnBaseUrl: 'https://img.example.com',
      );

      final variantsById = resolver.resolveManifestVariants(
        const <String, Object?>{
          'assets': <Object?>[
            <String, Object?>{
              'assetId': 'cover',
              'kind': 'image',
              'cdnUrl': 'https://cdn.example.com/fallback.jpg',
              'variants': <String, Object?>{
                'thumbnail': <String, Object?>{
                  'profile': 'thumbnail',
                  'cdnUrl': 'https://cdn.example.com/cover-thumb.webp',
                  'objectKey':
                      'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
                  'sourceSha256':
                      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'width': 320,
                },
                'display': <String, Object?>{
                  'profile': 'display',
                  'cdnUrl': 'https://cdn.example.com/cover-display.webp',
                  'objectKey':
                      'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
                  'sourceSha256':
                      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'width': 960,
                },
                'full': <String, Object?>{
                  'profile': 'full',
                  'cdnUrl': 'https://cdn.example.com/cover-full.webp',
                  'objectKey':
                      'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
                  'sourceSha256':
                      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'width': 2048,
                },
                'original': <String, Object?>{
                  'profile': 'original',
                  'objectKey':
                      'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
                  'sourceSha256':
                      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'requiresAccess': true,
                },
              },
            },
          ],
        },
      );

      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.thumbnail,
        ),
        'https://cdn.example.com/cover-thumb.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.display,
        ),
        'https://cdn.example.com/cover-display.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.full,
        ),
        'https://cdn.example.com/cover-full.webp',
      );
      expect(
        resolver.resolveVariantUrl(
          'cover',
          variantsById,
          profile: MediaAssetVariantProfile.original,
        ),
        'https://cdn.example.com/cover-full.webp',
      );

      final defaultUrls = resolver.resolveManifestUrls(
        const <String, Object?>{
          'assets': <Object?>[
            <String, Object?>{
              'assetId': 'cover',
              'variants': <String, Object?>{
                'display': <String, Object?>{
                  'cdnUrl': 'https://cdn.example.com/cover-display.webp',
                },
                'original': <String, Object?>{
                  'cdnUrl': 'https://cdn.example.com/original.jpg',
                  'requiresAccess': true,
                },
              },
            },
          ],
        },
      );

      expect(defaultUrls['cover'], 'https://cdn.example.com/cover-display.webp');
      expect(defaultUrls['cover'], isNot(contains('original.jpg')));
    });
  });
}
