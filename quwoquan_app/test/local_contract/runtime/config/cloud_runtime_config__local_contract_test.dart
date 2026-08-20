import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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
  };
}

ResolvedRuntimePackage _resolveRuntimePackage(
  Map<String, String> nativeRuntimePackage, {
  Map<String, String> compiledRuntimePackage = const <String, String>{},
  bool nativeRuntimePackageHydrated = true,
  bool enforceNativeLaunchBinding = true,
}) {
  return RuntimePackageResolver.resolve(
    compiledPackage: compiledRuntimePackage,
    nativeValues: nativeRuntimePackage,
    nativeRuntimePackageHydrated: nativeRuntimePackageHydrated,
    enforceNativeLaunchBinding: enforceNativeLaunchBinding,
  );
}

void main() {
  group('CloudRuntimeConfig environment package', () {
    test('裸 Flutter Debug 从 native manifest 恢复 canonical Alpha 包', () {
      final resolution = _resolveRuntimePackage(const <String, String>{
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
        'launchTarget': 'alpha-local',
        'effectiveLaunchManifestDigest': 'sha256:3333333333333333333333333333333333333333333333333333333333333333',
      });

      expect(resolution.source, RuntimePackageSource.native);
      expect(resolution.shouldLoadNativeRuntimePackage, isTrue);
      expect(resolution.appRuntimeEnv, 'alpha');
      expect(resolution.launchMode, 'direct_flutter_run');
      expect(resolution.runtimeDefineSummary['configurationState'], 'complete');
      expect(resolution.missingRequiredDefineKeys, isEmpty);
      expect(
        resolution.runtimeDefineSummary,
        isNot(contains('contentBindingState')),
      );
    });

    test('runtime package 未水合或无效时业务请求得到 typed unavailable', () {
      final pending = CloudRuntimeConfig.runtimeAvailabilityFailure();
      expect(pending, isNotNull);
      expect(pending!.kind, RuntimeFailureKind.unavailable);
      expect(
        pending.code,
        OpsEventRecordErrorCode.startupConfigurationInvalid.code,
      );
      expect(pending.recovery.action, 'retry');

      CloudRuntimeConfig.hydrateFromNativeRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('alpha'),
        'CLOUD_GATEWAY_BASE_URL': '',
      });
      final invalid = CloudRuntimeConfig.runtimeAvailabilityFailure();
      expect(invalid, isNotNull);
      expect(invalid!.kind, RuntimeFailureKind.unavailable);
      expect(
        invalid.context.attributes.any(
          (attribute) =>
              attribute.key == 'configurationState' &&
              attribute.value == 'invalid',
        ),
        isTrue,
      );

      CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
        _nativeRuntimePackageFor('alpha'),
      );
      expect(CloudRuntimeConfig.runtimeAvailabilityFailure(), isNull);
    });

    test('runtime package 重新带入内容激活身份时拒绝启动', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('alpha'),
        'CONTENT_BINDING_STATE': 'bound',
        'contentReleaseId': 'release-alpha',
        'contentManifestDigest': 'sha256:1111111111111111111111111111111111111111111111111111111111111111',
        'contentReadinessReceiptDigest': 'sha256:2222222222222222222222222222222222222222222222222222222222222222',
      });

      expect(
        resolution.missingRequiredDefineKeys,
        containsAll(<String>[
          'CONTENT_BINDING_STATE',
          'contentReleaseId',
          'contentManifestDigest',
          'contentReadinessReceiptDigest',
        ]),
      );
      expect(
        resolution.runtimeDefineSummary,
        isNot(contains('contentReleaseId')),
      );
    });

    test('裸 direct Flutter Debug 未绑定内容时进入 no_active_release 安全壳', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('alpha'),
        'QWQ_APP_LAUNCH_MODE': 'direct_flutter_run',
      });

      expect(resolution.missingRequiredDefineKeys, isEmpty);
    });

    test('canonical ui-only 未绑定内容仍可进入 Remote no_active_release 终态', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('alpha'),
        'QWQ_APP_LAUNCH_MODE': 'canonical_launcher',
      });

      expect(resolution.missingRequiredDefineKeys, isEmpty);
    });

    test('Prod runtime package 只要求 launch identity，不要求内容 identity', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('prod'),
        'APP_LAUNCH_POLICY': CloudRuntimeConfig.prodReleaseLaunchPolicy,
        'launchTarget': 'prod-hosted',
        'effectiveLaunchManifestDigest': 'sha256:3333333333333333333333333333333333333333333333333333333333333333',
      });

      expect(resolution.missingRequiredDefineKeys, isEmpty);
      expect(resolution.runtimeDefineSummary['configurationState'], 'complete');
    });

    test('Prod launch policy 缺少 launch identity 时仍 fail-closed', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('prod'),
        'APP_LAUNCH_POLICY': CloudRuntimeConfig.prodReleaseLaunchPolicy,
      });

      expect(
        resolution.missingRequiredDefineKeys,
        containsAll(<String>['launchTarget', 'effectiveLaunchManifestDigest']),
      );
    });

    test('不具备 native launch binding 的平台不伪造 release 绑定要求', () {
      final resolution = _resolveRuntimePackage(<String, String>{
        ..._nativeRuntimePackageFor('alpha'),
        'QWQ_APP_LAUNCH_MODE': 'direct_flutter_run',
      }, enforceNativeLaunchBinding: false);

      expect(resolution.missingRequiredDefineKeys, isEmpty);
    });

    test('Alpha、Beta、Gamma native 包不会混合 endpoint 或启动上下文', () {
      for (final environment in <String>['alpha', 'beta', 'gamma']) {
        final resolution = _resolveRuntimePackage(
          _nativeRuntimePackageFor(environment),
        );

        expect(resolution.appRuntimeEnv, environment);
        expect(
          resolution.gatewayBaseUrl,
          'https://api.$environment.example.test',
        );
        expect(
          resolution.mediaUploadBaseUrl,
          'https://upload.$environment.example.test',
        );
        expect(resolution.launchMode, 'stackctl_$environment');
        expect(resolution.missingRequiredDefineKeys, isEmpty);
      }
    });

    test('guarded compile-time 包优先且 native 漂移不会被测试后门隐藏', () {
      final compiled = _nativeRuntimePackageFor('alpha');
      final resolution = _resolveRuntimePackage(
        _nativeRuntimePackageFor('beta'),
        compiledRuntimePackage: compiled,
      );

      expect(resolution.source, RuntimePackageSource.compileTime);
      expect(resolution.appRuntimeEnv, 'alpha');
      expect(
        resolution.missingRequiredDefineKeys,
        contains('NATIVE_RUNTIME_PACKAGE.APP_RUNTIME_ENV'),
      );
    });

    test('部分 compile-time 包保持 fail-closed，不从完整 native 包补键', () {
      final resolution = _resolveRuntimePackage(
        _nativeRuntimePackageFor('alpha'),
        compiledRuntimePackage: const <String, String>{
          'APP_RUNTIME_ENV': 'alpha',
        },
      );

      expect(resolution.source, RuntimePackageSource.compileTime);
      expect(resolution.gatewayBaseUrl, isEmpty);
      expect(
        resolution.missingRequiredDefineKeys,
        contains('CLOUD_GATEWAY_BASE_URL'),
      );
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
      final summary = _resolveRuntimePackage(_nativeRuntimePackageFor('alpha'))
          .runtimeDefineSummary;

      expect(
        summary.keys,
        containsAll(<String>[
          'runtimeEnv',
          'launchMode',
          'configurationState',
          'missingKeys',
        ]),
      );
      expect(summary.values, everyElement(isA<String>()));
    });
  });
}
