import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

Map<String, String> _nativeRuntimePackageFor(String environment) {
  return <String, String>{
    'APP_RUNTIME_ENV': environment,
    'CLOUD_GATEWAY_BASE_URL': 'https://api.$environment.example.test',
    'REALTIME_CONNECTION_URL': 'wss://api.$environment.example.test',
    'PUBLIC_WEB_BASE_URL': 'https://www.$environment.example.test',
    'APP_DOWNLOAD_BASE_URL': 'https://cdn.$environment.example.test/download',
    'APP_LEGAL_BASE_URL': 'https://www.$environment.example.test/legal',
    'MEDIA_AVATAR_CDN_BASE_URL':
        'https://cdn.$environment.example.test/media/avatar',
    'MEDIA_IMAGE_CDN_BASE_URL':
        'https://cdn.$environment.example.test/media/image',
    'MEDIA_VIDEO_CDN_BASE_URL':
        'https://cdn.$environment.example.test/media/video',
    'MEDIA_UPLOAD_BASE_URL': 'https://upload.$environment.example.test',
    'RTC_MEDIA_CONNECTION_URL': 'wss://rtc.$environment.example.test',
    'QWQ_APP_LAUNCH_MODE': 'stackctl_$environment',
    'APP_LAUNCH_POLICY': 'test_live',
    'CONTENT_BINDING_STATE': 'unbound',
  };
}

void main() {
  group('CloudRuntimeConfig environment package', () {
    setUp(CloudRuntimeConfig.clearNativeRuntimePackageForTest);
    tearDown(CloudRuntimeConfig.clearNativeRuntimePackageForTest);

    test('裸 Flutter Debug 从 native manifest 恢复 canonical Alpha 包', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(const <
        String,
        String
      >{
        'APP_RUNTIME_ENV': 'alpha',
        'CLOUD_GATEWAY_BASE_URL': 'https://api.example.test',
        'REALTIME_CONNECTION_URL': 'wss://api.example.test',
        'PUBLIC_WEB_BASE_URL': 'https://example.test',
        'APP_DOWNLOAD_BASE_URL': 'https://cdn.example.test/download',
        'APP_LEGAL_BASE_URL': 'https://example.test/legal',
        'MEDIA_AVATAR_CDN_BASE_URL': 'https://cdn.example.test/media/avatar',
        'MEDIA_IMAGE_CDN_BASE_URL': 'https://cdn.example.test/media/image',
        'MEDIA_VIDEO_CDN_BASE_URL': 'https://cdn.example.test/media/video',
        'MEDIA_UPLOAD_BASE_URL': 'https://upload.example.test',
        'RTC_MEDIA_CONNECTION_URL': 'wss://rtc.example.test',
        'QWQ_APP_LAUNCH_MODE': 'direct_flutter_run',
        'APP_LAUNCH_POLICY': 'test_live',
        'CONTENT_BINDING_STATE': 'unbound',
        'launchTarget': 'alpha-local',
        'effectiveLaunchManifestDigest':
            'sha256:3333333333333333333333333333333333333333333333333333333333333333',
      });

      expect(CloudRuntimeConfig.shouldLoadNativeRuntimePackage, isTrue);
      expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
      expect(CloudRuntimeConfig.launchMode, 'direct_flutter_run');
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['configurationState'],
        'complete',
      );
      expect(CloudRuntimeConfig.missingRequiredDefineKeys, isEmpty);
      expect(CloudRuntimeConfig.hasCompleteContentBinding, isFalse);
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['contentBindingState'],
        'unbound',
      );
      expect(CloudRuntimeConfig.validateRequiredEndpoints, returnsNormally);
    });

    test('内容发布绑定缺失或 digest 非 canonical 时保持 invalid', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(<
        String,
        String
      >{
        ..._nativeRuntimePackageFor('prod'),
        'APP_LAUNCH_POLICY': CloudRuntimeConfig.prodReleaseLaunchPolicy,
        'CONTENT_BINDING_STATE': 'bound',
        'contentReleaseId': 'release-alpha',
        'contentManifestDigest': 'invalid',
        'contentReadinessReceiptDigest':
            'sha256:2222222222222222222222222222222222222222222222222222222222222222',
      });

      expect(CloudRuntimeConfig.hasCompleteContentBinding, isFalse);
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['contentBindingState'],
        'invalid',
      );
    });

    test('裸 direct Flutter Debug 未绑定内容时进入 no_active_release 安全壳', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'QWQ_APP_LAUNCH_MODE': 'direct_flutter_run',
        },
      );

      expect(CloudRuntimeConfig.requiresReleaseBoundContent, isFalse);
      expect(CloudRuntimeConfig.missingRequiredDefineKeys, isEmpty);
      expect(CloudRuntimeConfig.validateRequiredEndpoints, returnsNormally);
    });

    test('canonical ui-only 未绑定内容仍可进入 Remote no_active_release 终态', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'QWQ_APP_LAUNCH_MODE': 'canonical_launcher',
        },
      );

      expect(CloudRuntimeConfig.requiresReleaseBoundContent, isFalse);
      expect(CloudRuntimeConfig.validateRequiredEndpoints, returnsNormally);
    });

    test('test_live 接受完整 run-bound 内容并拒绝伪绑定或部分绑定', () {
      const manifestDigest =
          'sha256:1111111111111111111111111111111111111111111111111111111111111111';
      const readinessDigest =
          'sha256:2222222222222222222222222222222222222222222222222222222222222222';
      const launchDigest =
          'sha256:3333333333333333333333333333333333333333333333333333333333333333';

      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'CONTENT_BINDING_STATE': 'bound',
          'contentReleaseId': 'release-alpha-run',
          'contentManifestDigest': manifestDigest,
          'contentReadinessReceiptDigest': readinessDigest,
          'launchTarget': 'alpha-local',
          'effectiveLaunchManifestDigest': launchDigest,
        },
      );

      expect(CloudRuntimeConfig.hasCompleteContentBinding, isTrue);
      expect(CloudRuntimeConfig.requiresReleaseBoundContent, isTrue);
      expect(CloudRuntimeConfig.missingRequiredDefineKeys, isEmpty);
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['contentBindingState'],
        'bound',
      );

      CloudRuntimeConfig.clearNativeRuntimePackageForTest();
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'CONTENT_BINDING_STATE': 'bound',
          'contentReleaseId': 'release-alpha-run',
          'contentManifestDigest': manifestDigest,
          'launchTarget': 'alpha-local',
          'effectiveLaunchManifestDigest': launchDigest,
        },
      );
      expect(
        CloudRuntimeConfig.missingRequiredDefineKeys,
        contains('contentReadinessReceiptDigest'),
      );
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['contentBindingState'],
        'invalid',
      );

      CloudRuntimeConfig.clearNativeRuntimePackageForTest();
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'contentReleaseId': 'release-alpha-run',
          'contentManifestDigest': manifestDigest,
          'contentReadinessReceiptDigest': readinessDigest,
        },
      );
      expect(
        CloudRuntimeConfig.missingRequiredDefineKeys,
        contains('CONTENT_BINDING_STATE'),
      );
      expect(
        CloudRuntimeConfig.runtimeDefineSummary['contentBindingState'],
        'invalid',
      );
    });

    test('Prod launch policy 缺少 release-bound 内容时仍 fail-closed', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('prod'),
          'APP_LAUNCH_POLICY': CloudRuntimeConfig.prodReleaseLaunchPolicy,
          'CONTENT_BINDING_STATE': 'bound',
        },
      );

      expect(
        CloudRuntimeConfig.validateRequiredEndpoints,
        throwsA(
          isA<CloudRuntimeConfigurationException>().having(
            (error) => error.invalidKeys,
            'invalidKeys',
            containsAll(<String>[
              'contentReleaseId',
              'contentManifestDigest',
              'contentReadinessReceiptDigest',
              'launchTarget',
              'effectiveLaunchManifestDigest',
            ]),
          ),
        ),
      );
    });

    test('不具备 native launch binding 的平台不伪造 release 绑定要求', () {
      CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
        <String, String>{
          ..._nativeRuntimePackageFor('alpha'),
          'QWQ_APP_LAUNCH_MODE': 'direct_flutter_run',
        },
        enforceNativeLaunchBinding: false,
      );

      expect(CloudRuntimeConfig.requiresReleaseBoundContent, isFalse);
      expect(CloudRuntimeConfig.missingRequiredDefineKeys, isEmpty);
      expect(CloudRuntimeConfig.validateRequiredEndpoints, returnsNormally);
    });

    test('Alpha、Beta、Gamma native 包不会混合 endpoint 或启动上下文', () {
      for (final environment in <String>['alpha', 'beta', 'gamma']) {
        CloudRuntimeConfig.clearNativeRuntimePackageForTest();
        CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
          _nativeRuntimePackageFor(environment),
        );

        expect(CloudRuntimeConfig.appRuntimeEnv, environment);
        expect(
          CloudRuntimeConfig.gatewayBaseUrl,
          'https://api.$environment.example.test',
        );
        expect(
          CloudRuntimeConfig.mediaUploadBaseUrl,
          'https://upload.$environment.example.test',
        );
        expect(CloudRuntimeConfig.launchMode, 'stackctl_$environment');
        expect(CloudRuntimeConfig.missingRequiredDefineKeys, isEmpty);
      }
    });

    test('完整业务 endpoint 包通过且只要求 canonical telemetry endpoint', () {
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
