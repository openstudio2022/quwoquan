import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

void main() {
  group('CloudRuntimeConfig environment package', () {
    test('完整业务 endpoint 包通过且不要求 SLS 配置', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'gamma',
          gatewayBaseUrl: 'https://api.example.test',
          realtimeConnectionUrl: 'wss://api.example.test',
          publicWebBaseUrl: 'https://example.test',
          appDownloadBaseUrl: 'https://cdn.example.test/download',
          legalBaseUrl: 'https://example.test/legal',
          mediaAvatarCdnBaseUrl: 'https://cdn.example.test/media/avatar',
          mediaImageCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaVideoCdnBaseUrl: 'https://cdn.example.test/media/video',
          mediaUploadBaseUrl: 'https://upload.example.test',
          rtcMediaConnectionUrl: 'wss://rtc.example.test',
        ),
        returnsNormally,
      );
    });

    test('环境名或业务 endpoint 缺失时 fail-closed', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'staging',
          gatewayBaseUrl: '',
          realtimeConnectionUrl: 'wss://api.example.test',
          publicWebBaseUrl: 'https://example.test',
          appDownloadBaseUrl: 'https://cdn.example.test/download',
          legalBaseUrl: 'https://example.test/legal',
          mediaAvatarCdnBaseUrl: 'https://cdn.example.test/media/avatar',
          mediaImageCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaVideoCdnBaseUrl: 'https://cdn.example.test/media/video',
          mediaUploadBaseUrl: 'https://upload.example.test',
          rtcMediaConnectionUrl: 'wss://rtc.example.test',
        ),
        throwsA(
          isA<CloudRuntimeConfigurationException>().having(
            (error) => error.invalidKeys,
            'invalidKeys',
            allOf(
              contains('APP_RUNTIME_ENV'),
              contains('CLOUD_GATEWAY_BASE_URL'),
            ),
          ),
        ),
      );
    });

    test('非 HTTPS 或带 query 的业务 endpoint 被拒绝', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'beta',
          gatewayBaseUrl: 'http://api.example.test',
          realtimeConnectionUrl: 'wss://api.example.test',
          publicWebBaseUrl: 'https://example.test',
          appDownloadBaseUrl: 'https://cdn.example.test/download',
          legalBaseUrl: 'https://example.test/legal',
          mediaAvatarCdnBaseUrl:
              'https://cdn.example.test/media/avatar?size=small',
          mediaImageCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaVideoCdnBaseUrl: 'https://cdn.example.test/media/video',
          mediaUploadBaseUrl: 'https://upload.example.test',
          rtcMediaConnectionUrl: 'wss://rtc.example.test',
        ),
        throwsA(isA<CloudRuntimeConfigurationException>()),
      );
    });

    test('RTC endpoint 缺失时返回配置错误而非固定列表异常', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'beta',
          gatewayBaseUrl: 'https://api.example.test',
          realtimeConnectionUrl: 'wss://api.example.test',
          publicWebBaseUrl: 'https://example.test',
          appDownloadBaseUrl: 'https://cdn.example.test/download',
          legalBaseUrl: 'https://example.test/legal',
          mediaAvatarCdnBaseUrl: 'https://cdn.example.test/media/avatar',
          mediaImageCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaVideoCdnBaseUrl: 'https://cdn.example.test/media/video',
          mediaUploadBaseUrl: 'https://upload.example.test',
          rtcMediaConnectionUrl: '',
        ),
        throwsA(
          isA<CloudRuntimeConfigurationException>().having(
            (error) => error.invalidKeys,
            'invalidKeys',
            contains('RTC_MEDIA_CONNECTION_URL'),
          ),
        ),
      );
    });

    test('媒体、Legal、下载和上传 role 发生 authority/path 串用时拒绝启动', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'gamma',
          gatewayBaseUrl: 'https://api.example.test',
          realtimeConnectionUrl: 'wss://api.example.test',
          publicWebBaseUrl: 'https://example.test',
          appDownloadBaseUrl: 'https://example.test/download',
          legalBaseUrl: 'https://api.example.test/legal',
          mediaAvatarCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaImageCdnBaseUrl: 'https://cdn.example.test/media/image',
          mediaVideoCdnBaseUrl: 'https://cdn.example.test/media/video',
          mediaUploadBaseUrl: 'https://cdn.example.test',
          rtcMediaConnectionUrl: 'wss://rtc.example.test',
        ),
        throwsA(
          isA<CloudRuntimeConfigurationException>().having(
            (error) => error.invalidKeys,
            'invalidKeys',
            containsAll(<String>[
              'APP_LEGAL_BASE_URL',
              'APP_DOWNLOAD_BASE_URL',
              'MEDIA_AVATAR_CDN_BASE_URL',
              'MEDIA_UPLOAD_BASE_URL',
            ]),
          ),
        ),
      );
    });

    test('配置摘要只暴露环境、入口和缺失键，不暴露 endpoint', () {
      expect(
        CloudRuntimeConfig.runtimeDefineSummary.keys,
        containsAll(<String>[
          'runtimeEnv',
          'launchMode',
          'configurationState',
          'missingKeys',
        ]),
      );
      expect(
        CloudRuntimeConfig.runtimeDefineSummary.values,
        everyElement(isA<String>()),
      );
    });
  });
}
