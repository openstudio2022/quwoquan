import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

void main() {
  group('CloudRuntimeConfig defaults', () {
    test('默认网关与媒体基座使用 secure env domains', () {
      expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
      expect(
        CloudRuntimeConfig.gatewayBaseUrl,
        'https://alpha-api.quwoquan-env.test:17000',
      );
      expect(
        CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        'https://alpha-avatar.quwoquan-env.test:17100',
      );
      expect(
        CloudRuntimeConfig.mediaImageCdnBaseUrl,
        'https://alpha-image.quwoquan-env.test:17100',
      );
      expect(
        CloudRuntimeConfig.mediaVideoCdnBaseUrl,
        'https://alpha-video.quwoquan-env.test:17100',
      );
      expect(
        CloudRuntimeConfig.mediaUploadBaseUrl,
        'https://alpha-upload.quwoquan-env.test:17100',
      );
    });
  });
}
