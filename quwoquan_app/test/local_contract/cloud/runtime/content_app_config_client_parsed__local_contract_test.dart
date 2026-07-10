import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';

void main() {
  group('ContentAppConfigWire.clientParsed', () {
    test('camelCase 旧别名不再被解析', () {
      final wire = ContentAppConfigWire.fromResponseObject(
        <String, dynamic>{
          'content': <String, dynamic>{
            'featureFlags': <String, dynamic>{
              'enable_create_action_entry': false,
            },
            'grayRelease': <String, dynamic>{
              'experimentBucket': 'rollout_20',
              'currentStage': '20%',
              'canaryMatrix': <Map<String, dynamic>>[
                <String, dynamic>{'stage': '20%', 'rolloutPercent': 20},
              ],
            },
            'clientStateSync': <String, dynamic>{
              'flushDelaySec': 15,
            },
          },
        },
      );

      final parsed = wire.clientParsed;

      expect(parsed.featureFlagOverrides, isEmpty);
      expect(parsed.grayRelease.experimentBucket, isEmpty);
      expect(parsed.grayRelease.currentStage, isEmpty);
      expect(parsed.grayRelease.canaryMatrix, isEmpty);
      expect(parsed.clientStateSyncMap, isEmpty);
    });
  });
}
