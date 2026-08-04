// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/post/capture_photography_tag_deriver.dart';
import 'package:quwoquan_app/core/geo/solar_position.dart';
import 'package:quwoquan_app/content/media/media_upload_session/domain/media_capture_metadata.dart';

const _deriver = CapturePhotographyTagDeriver();

/// 杭州西湖，用于光线条件断言。
const double _hangzhouLat = 30.2489;
const double _hangzhouLon = 120.1489;

DateTime _hangzhou(int month, int day, int hour, int minute) =>
    DateTime.parse(
      '2026-${month.toString().padLeft(2, '0')}-'
      '${day.toString().padLeft(2, '0')}T'
      '${hour.toString().padLeft(2, '0')}:'
      '${minute.toString().padLeft(2, '0')}:00+08:00',
    );

void main() {
  group('器材派生', () {
    test('全画幅微单 + 变焦镜头 + 标准焦段', () {
      final refs = _deriver.derive(
        const ExtractedMediaCaptureMetadata(
          cameraMake: 'SONY',
          cameraModel: 'ILCE-7M4',
          lensModel: 'FE 24-70mm F2.8 GM II',
          focalLengthMm: 50,
        ),
      );

      expect(refs, contains('$kPhotographyTagRoot/器材/机身类型/全画幅微单'));
      expect(refs, contains('$kPhotographyTagRoot/器材/镜头类型/变焦镜头'));
      expect(refs, contains('$kPhotographyTagRoot/拍摄参数/焦段/标准'));
    });

    test('手机厂商优先于机型串里的其他线索', () {
      final refs = _deriver.derive(
        const ExtractedMediaCaptureMetadata(cameraMake: 'Apple', cameraModel: 'iPhone 17 Pro'),
      );
      expect(refs, contains('$kPhotographyTagRoot/器材/机身类型/手机拍摄'));
    });

    test('无人机与运动相机不被误判成手机', () {
      expect(
        _deriver.derive(
          const ExtractedMediaCaptureMetadata(cameraMake: 'DJI', cameraModel: 'FC3582'),
        ),
        contains('$kPhotographyTagRoot/器材/机身类型/无人机航拍'),
      );
      expect(
        _deriver.derive(
          const ExtractedMediaCaptureMetadata(cameraMake: 'GoPro', cameraModel: 'HERO12 Black'),
        ),
        contains('$kPhotographyTagRoot/器材/机身类型/运动相机'),
      );
    });

    test('未知机型不猜机身类别', () {
      final refs = _deriver.derive(
        const ExtractedMediaCaptureMetadata(cameraMake: 'ACME', cameraModel: 'XYZ-1'),
      );
      expect(refs.where((r) => r.contains('机身类型')), isEmpty);
    });

    test('焦段区间边界按左闭右开划分，不重叠', () {
      String? focalOf(double mm) {
        final refs = _deriver.derive(ExtractedMediaCaptureMetadata(focalLengthMm: mm));
        final matched = refs.where((r) => r.contains('/焦段/'));
        expect(matched, hasLength(1));
        return matched.single.split('/').last;
      }

      expect(focalOf(14), '超广角');
      expect(focalOf(20), '广角');
      expect(focalOf(35), '标准');
      expect(focalOf(70), '中长焦');
      expect(focalOf(135), '长焦');
      expect(focalOf(300), '超长焦');
      expect(focalOf(600), '超长焦');
    });

    test('镜头类别可叠加：微距变焦同时命中两类', () {
      final refs = _deriver.derive(
        const ExtractedMediaCaptureMetadata(lensModel: 'AF-S VR Micro 70-180mm Macro'),
      );
      expect(refs, contains('$kPhotographyTagRoot/器材/镜头类型/微距镜头'));
      expect(refs, contains('$kPhotographyTagRoot/器材/镜头类型/变焦镜头'));
    });

    test('定焦与变焦互斥', () {
      final prime = _deriver.derive(
        const ExtractedMediaCaptureMetadata(lensModel: 'FE 35mm F1.4 GM'),
      );
      expect(prime, contains('$kPhotographyTagRoot/器材/镜头类型/定焦镜头'));
      expect(prime, isNot(contains('$kPhotographyTagRoot/器材/镜头类型/变焦镜头')));
    });
  });

  group('拍摄参数派生', () {
    test('快门三档按阈值判定，中间地带不打标', () {
      String? shutterOf(double seconds) {
        final refs = _deriver.derive(
          ExtractedMediaCaptureMetadata(shutterSpeedSeconds: seconds),
        );
        final matched = refs.where((r) => r.contains('/快门/'));
        return matched.isEmpty ? null : matched.single.split('/').last;
      }

      expect(shutterOf(30), '长曝光');
      expect(shutterOf(1), '长曝光');
      expect(shutterOf(1 / 4), '慢门');
      expect(shutterOf(1 / 15), '慢门');
      expect(shutterOf(1 / 2000), '高速快门');
      // 1/125 既不算慢门也不算高速快门：绝大多数照片落在这里，打标会失去区分度。
      expect(shutterOf(1 / 125), isNull);
    });

    test('光圈与感光度只在两端打标', () {
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(apertureFNumber: 1.4)),
        contains('$kPhotographyTagRoot/拍摄参数/光圈/大光圈虚化'),
      );
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(apertureFNumber: 16)),
        contains('$kPhotographyTagRoot/拍摄参数/光圈/小光圈全景深'),
      );
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(apertureFNumber: 5.6)),
        isEmpty,
      );
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(isoSensitivity: 6400)),
        contains('$kPhotographyTagRoot/拍摄参数/感光度/高感夜拍'),
      );
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(isoSensitivity: 100)),
        contains('$kPhotographyTagRoot/拍摄参数/感光度/低感画质'),
      );
      expect(
        _deriver.derive(const ExtractedMediaCaptureMetadata(isoSensitivity: 800)),
        isEmpty,
      );
    });
  });

  group('光线条件派生', () {
    String? windowAt(DateTime at) {
      final refs = _deriver.derive(
        ExtractedMediaCaptureMetadata(
          capturedAt: at,
          gpsLatitude: _hangzhouLat,
          gpsLongitude: _hangzhouLon,
        ),
      );
      final matched = refs.where((r) => r.contains('/光线条件/'));
      return matched.isEmpty ? null : matched.single.split('/').last;
    }

    test('夏至日的杭州：深夜、日出前后、正午分别落在不同窗口', () {
      expect(windowAt(_hangzhou(6, 21, 1, 0)), '夜间无日光');
      expect(windowAt(_hangzhou(6, 21, 12, 0)), '正午强光');
      expect(windowAt(_hangzhou(6, 21, 9, 0)), '白天漫射光');
    });

    test('日落前后依次经过金色时刻与蓝调时刻', () {
      // 杭州冬至日落约 17:00（+08:00），太阳高度角依次穿过 6° / -4° / -6° 三个边界。
      final sequence = <String?>[
        windowAt(_hangzhou(12, 21, 16, 0)),
        windowAt(_hangzhou(12, 21, 16, 45)),
        windowAt(_hangzhou(12, 21, 17, 25)),
        windowAt(_hangzhou(12, 21, 18, 0)),
      ];
      expect(sequence, <String?>['白天漫射光', '金色时刻', '蓝调时刻', '夜间无日光']);
    });

    test('缺经纬度或缺时间时不产出光线标签，不按钟点粗判', () {
      expect(
        _deriver.derive(
          ExtractedMediaCaptureMetadata(capturedAt: _hangzhou(6, 21, 12, 0)),
        ),
        isEmpty,
      );
      expect(
        _deriver.derive(
          const ExtractedMediaCaptureMetadata(
            gpsLatitude: _hangzhouLat,
            gpsLongitude: _hangzhouLon,
          ),
        ),
        isEmpty,
      );
    });

    test('北极圈夏季午夜仍是白昼，按太阳高度角而非钟点判定', () {
      // 特罗姆瑟（69.65N）夏至午夜太阳不落。
      final refs = _deriver.derive(
        ExtractedMediaCaptureMetadata(
          capturedAt: DateTime.parse('2026-06-21T00:00:00+02:00'),
          gpsLatitude: 69.6492,
          gpsLongitude: 18.9553,
        ),
      );
      expect(
        refs.single,
        anyOf(
          '$kPhotographyTagRoot/光线条件/白天漫射光',
          '$kPhotographyTagRoot/光线条件/金色时刻',
        ),
      );
    });
  });

  group('披露裁剪与推导的联动', () {
    const full = ExtractedMediaCaptureMetadata(
      cameraMake: 'SONY',
      cameraModel: 'ILCE-7M4',
      lensModel: 'FE 24-70mm F2.8 GM II',
      focalLengthMm: 50,
      apertureFNumber: 1.8,
      isoSensitivity: 6400,
    );

    test('只披露参数组时，器材子树整体消失', () {
      final refs = _deriver.derive(
        full.discloseOnly(const <CaptureMetadataDisclosureGroup>{
          CaptureMetadataDisclosureGroup.parameters,
        }),
      );

      expect(refs.where((r) => r.contains('/器材/')), isEmpty);
      expect(refs, contains('$kPhotographyTagRoot/拍摄参数/焦段/标准'));
      expect(refs, contains('$kPhotographyTagRoot/拍摄参数/光圈/大光圈虚化'));
      expect(refs, contains('$kPhotographyTagRoot/拍摄参数/感光度/高感夜拍'));
    });

    test('只披露器材组时，拍摄参数子树整体消失（焦段属参数组）', () {
      final refs = _deriver.derive(
        full.discloseOnly(const <CaptureMetadataDisclosureGroup>{
          CaptureMetadataDisclosureGroup.gear,
        }),
      );

      expect(refs, contains('$kPhotographyTagRoot/器材/机身类型/全画幅微单'));
      expect(refs.where((r) => r.contains('/拍摄参数/')), isEmpty);
    });

    test('全部关闭后无任何派生标签', () {
      expect(
        _deriver.derive(
          full.discloseOnly(const <CaptureMetadataDisclosureGroup>{}),
        ),
        isEmpty,
      );
      expect(_deriver.derive(ExtractedMediaCaptureMetadata.empty), isEmpty);
    });
  });

  group('solarElevationDegrees', () {
    test('赤道春分正午接近天顶', () {
      final elevation = solarElevationDegrees(
        capturedAt: DateTime.parse('2026-03-20T12:00:00Z'),
        latitude: 0,
        longitude: 0,
      );
      expect(elevation, closeTo(89.6, 1.5));
    });

    test('同一时刻南北半球高度角符号相反', () {
      final north = solarElevationDegrees(
        capturedAt: DateTime.parse('2026-06-21T12:00:00Z'),
        latitude: 80,
        longitude: 0,
      );
      final south = solarElevationDegrees(
        capturedAt: DateTime.parse('2026-06-21T12:00:00Z'),
        latitude: -80,
        longitude: 0,
      );
      expect(north, greaterThan(0));
      expect(south, lessThan(0));
    });
  });
}
