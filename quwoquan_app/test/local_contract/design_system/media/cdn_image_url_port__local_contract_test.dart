import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/media/cdn_image_url_port.dart';
import 'package:quwoquan_app/runtime/di/content_image_delivery_dependencies.dart';

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md

final MediaEndpointConfig _testMediaEndpointConfig = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/avatar',
  imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
  videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/video',
  attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
);

final class _RecordingCdnImageUrlPort implements CdnImageUrlPort {
  final List<String> calls = <String>[];
  int? avatarSize;

  @override
  String thumbnail(String url) {
    calls.add('thumbnail');
    return url;
  }

  @override
  String cover(String url) {
    calls.add('cover');
    return url;
  }

  @override
  String display(String url) {
    calls.add('display');
    return url;
  }

  @override
  String avatar(String url, {required int size}) {
    calls.add('avatar');
    avatarSize = size;
    return url;
  }

  @override
  String full(String url) {
    calls.add('full');
    return url;
  }
}

Future<_RecordingCdnImageUrlPort> _pumpWithRecordingPort(
  WidgetTester tester, {
  required CdnImagePreset preset,
  double? width,
}) async {
  final port = _RecordingCdnImageUrlPort();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
        cdnImageUrlPortProvider.overrideWithValue(port),
      ],
      child: CupertinoApp(
        home: CupertinoPageScaffold(
          child: Center(
            child: AppCachedNetworkImage(
              imageUrl: 'media/image/s/archived-image/post/p1/v1/cover.png',
              cdnPreset: preset,
              width: width,
            ),
          ),
        ),
      ),
    ),
  );
  return port;
}

void main() {
  group('AppCachedNetworkImage 经端口取 CDN 变体 URL', () {
    testWidgets('每个 preset 只调用端口上对应的变体方法', (tester) async {
      const expectedCall = <CdnImagePreset, String?>{
        CdnImagePreset.thumbnail: 'thumbnail',
        CdnImagePreset.cover: 'cover',
        CdnImagePreset.inline: 'display',
        CdnImagePreset.avatar: 'avatar',
        CdnImagePreset.full: 'full',
        CdnImagePreset.none: null,
      };
      for (final entry in expectedCall.entries) {
        final port = await _pumpWithRecordingPort(tester, preset: entry.key);
        final expected = entry.value;
        expect(
          port.calls,
          expected == null ? isEmpty : everyElement(expected),
          reason: '${entry.key} 应只经端口的 $expected 变体解析',
        );
        if (expected != null) {
          expect(port.calls, isNotEmpty);
        }
      }
    });

    testWidgets('avatar preset 把宽度作为目标像素尺寸透传给端口', (tester) async {
      final port = await _pumpWithRecordingPort(
        tester,
        preset: CdnImagePreset.avatar,
        width: 72,
      );

      expect(port.avatarSize, 72);
    });

    testWidgets('端口返回的 URL 直接成为请求 URL', (tester) async {
      await _pumpWithRecordingPort(tester, preset: CdnImagePreset.cover);

      final image = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(image.imageUrl, contains('/media/image/'));
      expect(image.imageUrl, isNot(contains('x-oss-process')));
    });
  });

  group('组合根装配', () {
    test('production 默认端口来自 content 域 CDN 策略', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final port = container.read(cdnImageUrlPortProvider);

      expect(port, isA<CdnImageUrlPort>());
      // 非 CDN host 不做处理，是 content 侧 CDN 策略的可观测下界。
      expect(
        port.cover('https://example.com/a.png'),
        'https://example.com/a.png',
      );
    });
  });
}
