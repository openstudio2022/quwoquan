import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_capture_metadata.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';

void main() {
  group('PublishSettings 拍摄元数据披露', () {
    test('默认四组全开', () {
      const settings = PublishSettings();

      expect(
        settings.captureDisclosure,
        CaptureMetadataDisclosureGroup.values.toSet(),
      );
    });

    test('披露集合可经 toMap/fromMap 往返', () {
      const settings = PublishSettings(
        captureDisclosure: <CaptureMetadataDisclosureGroup>{
          CaptureMetadataDisclosureGroup.gear,
          CaptureMetadataDisclosureGroup.parameters,
        },
      );

      final restored = PublishSettings.fromMap(settings.toMap());

      expect(restored.captureDisclosure, settings.captureDisclosure);
    });

    test('显式关闭全部分组不会被回退成默认值', () {
      const settings = PublishSettings(
        captureDisclosure: <CaptureMetadataDisclosureGroup>{},
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

      expect(restored.captureDisclosure, <CaptureMetadataDisclosureGroup>{
        CaptureMetadataDisclosureGroup.gear,
      });
    });

    test('copyWith 可单独改披露集合且不影响其它字段', () {
      const settings = PublishSettings(locationName: '西湖');

      final updated = settings.copyWith(
        captureDisclosure: <CaptureMetadataDisclosureGroup>{
          CaptureMetadataDisclosureGroup.time,
        },
      );

      expect(updated.captureDisclosure, <CaptureMetadataDisclosureGroup>{
        CaptureMetadataDisclosureGroup.time,
      });
      expect(updated.locationName, '西湖');
    });

    test('关闭拍摄地点后 metadata 裁剪结果不含坐标', () {
      const settings = PublishSettings(
        captureDisclosure: <CaptureMetadataDisclosureGroup>{
          CaptureMetadataDisclosureGroup.gear,
        },
      );
      const captured = ExtractedMediaCaptureMetadata(
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

  group('capture payload boundary', () {
    const captured = ExtractedMediaCaptureMetadata(
      cameraMake: 'SONY',
      cameraModel: 'ILCE-7M4',
      focalLengthMm: 200,
      isoSensitivity: 6400,
    );

    test('端侧不把器材与参数派生成公开 tagRefs', () {
      const settings = PublishSettings(captureMetadata: captured);

      final payload = settings.toPayloadFields();
      expect(payload, isNot(contains('tagRefs')));
      expect(
        payload['captureDisclosure'],
        containsAll(<String>['gear', 'parameters']),
      );
    });

    test('关闭某组后请求只保留仍披露的闭集', () {
      final settings = const PublishSettings(captureMetadata: captured)
          .copyWith(
            captureDisclosure: <CaptureMetadataDisclosureGroup>{
              CaptureMetadataDisclosureGroup.gear,
            },
          );

      expect(settings.toPayloadFields()['captureDisclosure'], <String>['gear']);
    });

    test('拍摄元数据不落草稿：toMap 不含 PII，恢复后为空', () {
      const settings = PublishSettings(
        captureMetadata: ExtractedMediaCaptureMetadata(
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
        ExtractedMediaCaptureMetadata.empty,
      );
    });
  });
}
