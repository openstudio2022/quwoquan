import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

void main() {
  group('CloudRuntimeConfig environment package', () {
    test('完整业务 endpoint 包通过且不要求 SLS 配置', () {
      expect(
        () => CloudRuntimeConfig.validateRuntimePackage(
          runtimeEnv: 'gamma',
          gatewayBaseUrl: 'https://api.example.test',
          mediaAvatarCdnBaseUrl: 'https://avatar.example.test',
          mediaImageCdnBaseUrl: 'https://image.example.test',
          mediaVideoCdnBaseUrl: 'https://video.example.test',
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
          mediaAvatarCdnBaseUrl: 'https://avatar.example.test',
          mediaImageCdnBaseUrl: 'https://image.example.test',
          mediaVideoCdnBaseUrl: 'https://video.example.test',
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
          mediaAvatarCdnBaseUrl: 'https://avatar.example.test?size=small',
          mediaImageCdnBaseUrl: 'https://image.example.test',
          mediaVideoCdnBaseUrl: 'https://video.example.test',
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
          mediaAvatarCdnBaseUrl: 'https://avatar.example.test',
          mediaImageCdnBaseUrl: 'https://image.example.test',
          mediaVideoCdnBaseUrl: 'https://video.example.test',
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
