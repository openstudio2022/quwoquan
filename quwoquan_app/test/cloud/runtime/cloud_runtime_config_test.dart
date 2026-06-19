import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

void main() {
  group('CloudRuntimeConfig defaults', () {
    test('本地默认网关与媒体基座使用 http loopback', () {
      expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
      expect(CloudRuntimeConfig.gatewayBaseUrl, 'http://127.0.0.1:17000');
      expect(
        CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        'http://127.0.0.1:17100',
      );
      expect(
        CloudRuntimeConfig.mediaImageCdnBaseUrl,
        'http://127.0.0.1:17100',
      );
      expect(
        CloudRuntimeConfig.mediaVideoCdnBaseUrl,
        'http://127.0.0.1:17100',
      );
      expect(CloudRuntimeConfig.mediaUploadBaseUrl, 'http://127.0.0.1:17100');
    });
  });
}
