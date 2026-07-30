import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_capture_metadata.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';

void main() {
  group('PublishSettings 拍摄元数据披露', () {
    test('默认四组全开', () {
      const settings = PublishSettings();

      expect(
        settings.captureDisclosure,
        MediaCaptureDisclosureGroup.values.toSet(),
      );
    });

    test('披露集合可经 toMap/fromMap 往返', () {
      const settings = PublishSettings(
        captureDisclosure: <MediaCaptureDisclosureGroup>{
          MediaCaptureDisclosureGroup.gear,
          MediaCaptureDisclosureGroup.parameters,
        },
      );

      final restored = PublishSettings.fromMap(settings.toMap());

      expect(restored.captureDisclosure, settings.captureDisclosure);
    });

    test('显式关闭全部分组不会被回退成默认值', () {
      const settings = PublishSettings(
        captureDisclosure: <MediaCaptureDisclosureGroup>{},
      );

      final restored = PublishSettings.fromMap(settings.toMap());

      expect(restored.captureDisclosure, isEmpty);
    });

    test('早于本能力的草稿缺少该键时按默认全开恢复', () {
      final legacy = PublishSettings.fromMap(<String, dynamic>{
        'visibility': 'public',
      });

      expect(legacy.captureDisclosure, kDefaultCaptureDisclosure);
    });

    test('未知分组值被丢弃而不是让整份草稿失败', () {
      final restored = PublishSettings.fromMap(<String, dynamic>{
        'captureDisclosure': <String>['gear', 'not_a_group'],
      });

      expect(restored.captureDisclosure, <MediaCaptureDisclosureGroup>{
        MediaCaptureDisclosureGroup.gear,
      });
    });

    test('copyWith 可单独改披露集合且不影响其它字段', () {
      const settings = PublishSettings(locationName: '西湖');

      final updated = settings.copyWith(
        captureDisclosure: <MediaCaptureDisclosureGroup>{
          MediaCaptureDisclosureGroup.time,
        },
      );

      expect(updated.captureDisclosure, <MediaCaptureDisclosureGroup>{
        MediaCaptureDisclosureGroup.time,
      });
      expect(updated.locationName, '西湖');
    });

    test('关闭拍摄地点后 metadata 裁剪结果不含坐标', () {
      const settings = PublishSettings(
        captureDisclosure: <MediaCaptureDisclosureGroup>{
          MediaCaptureDisclosureGroup.gear,
        },
      );
      const captured = MediaCaptureMetadata(
        cameraModel: 'ILCE-7M4',
        gpsLatitude: 30.24,
        gpsLongitude: 120.14,
        isoSensitivity: 400,
      );

      final disclosed = captured.discloseOnly(settings.captureDisclosure);

      expect(disclosed.cameraModel, 'ILCE-7M4');
      expect(disclosed.hasPlace, isFalse);
      expect(disclosed.isoSensitivity, isNull);
    });
  });

  group('captureDerivedTagRefs', () {
    const captured = MediaCaptureMetadata(
      cameraMake: 'SONY',
      cameraModel: 'ILCE-7M4',
      focalLengthMm: 200,
      isoSensitivity: 6400,
    );

    test('默认全开时派生器材与参数标签', () {
      const settings = PublishSettings(captureMetadata: captured);

      expect(
        settings.captureDerivedTagRefs,
        containsAll(<String>[
          'Topic/摄影/器材/机身类型/全画幅微单',
          'Topic/摄影/拍摄参数/焦段/长焦',
          'Topic/摄影/拍摄参数/感光度/高感夜拍',
        ]),
      );
    });

    test('关闭某组后该组派生标签立刻消失，不需要额外撤回动作', () {
      final settings = const PublishSettings(
        captureMetadata: captured,
      ).copyWith(
        captureDisclosure: <MediaCaptureDisclosureGroup>{
          MediaCaptureDisclosureGroup.gear,
        },
      );

      expect(
        settings.captureDerivedTagRefs,
        <String>['Topic/摄影/器材/机身类型/全画幅微单'],
      );
    });

    test('拍摄元数据不落草稿：toMap 不含 PII，恢复后为空', () {
      const settings = PublishSettings(
        captureMetadata: MediaCaptureMetadata(
          gpsLatitude: 30.24,
          gpsLongitude: 120.14,
          cameraModel: 'ILCE-7M4',
        ),
      );

      final serialized = settings.toMap();
      expect(serialized.keys, isNot(contains('captureMetadata')));
      expect(serialized.toString(), isNot(contains('30.24')));
      expect(
        PublishSettings.fromMap(serialized).captureMetadata,
        MediaCaptureMetadata.empty,
      );
    });
  });
}
