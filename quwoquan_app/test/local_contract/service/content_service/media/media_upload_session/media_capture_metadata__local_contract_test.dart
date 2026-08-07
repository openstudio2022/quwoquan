import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/exif_media_capture_metadata_extractor.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';

const _extractor = ExifMediaCaptureMetadataExtractor();

/// `Rational` 未从 `package:image` 公开导出，只能借 [img.IfdValueRational] 中转
/// 构造出三元组（度/分/秒）。
img.IfdValueRational _dmsValue(List<double> dms) {
  final value = img.IfdValueRational((dms[0] * 10000).round(), 10000);
  for (final component in dms.skip(1)) {
    value.value.add(
      img.IfdValueRational((component * 10000).round(), 10000).toRational(),
    );
  }
  return value;
}

/// 生成一张带 EXIF 的真实 JPEG，用于证明解析走的是真实 APP1/TIFF 结构，
/// 而不是对内部字段的直接赋值。
Uint8List _jpegWithExif({
  String? make,
  String? model,
  String? lens,
  double? focalLength,
  double? fNumber,
  double? exposureTime,
  int? iso,
  String? dateTimeOriginal,
  List<double>? latitudeDms,
  String? latitudeRef,
  List<double>? longitudeDms,
  String? longitudeRef,
}) {
  final image = img.Image(width: 8, height: 8);
  final exif = image.exif;
  if (make != null) exif.imageIfd['Make'] = make;
  if (model != null) exif.imageIfd['Model'] = model;
  if (lens != null) exif.exifIfd['LensModel'] = lens;
  if (focalLength != null) {
    exif.exifIfd['FocalLength'] = img.IfdValueRational(
      (focalLength * 100).round(),
      100,
    );
  }
  if (fNumber != null) {
    exif.exifIfd['FNumber'] = img.IfdValueRational(
      (fNumber * 100).round(),
      100,
    );
  }
  if (exposureTime != null) {
    exif.exifIfd['ExposureTime'] = img.IfdValueRational(
      1,
      (1 / exposureTime).round(),
    );
  }
  if (iso != null) exif.exifIfd['ISOSpeed'] = img.IfdValueLong(iso);
  if (dateTimeOriginal != null) {
    exif.exifIfd['DateTimeOriginal'] = dateTimeOriginal;
  }
  if (latitudeDms != null) {
    exif.gpsIfd['GPSLatitude'] = _dmsValue(latitudeDms);
  }
  // GPS ref 必须显式包成 IfdValueAscii：`IfdDirectory.operator[]=` 对裸字符串会去
  // 查 image tag 表（0x1 在那里是 InteropIndex），导致 GPS ref 被静默丢弃。
  if (latitudeRef != null) {
    exif.gpsIfd['GPSLatitudeRef'] = img.IfdValueAscii(latitudeRef);
  }
  if (longitudeDms != null) {
    exif.gpsIfd['GPSLongitude'] = _dmsValue(longitudeDms);
  }
  if (longitudeRef != null) {
    exif.gpsIfd['GPSLongitudeRef'] = img.IfdValueAscii(longitudeRef);
  }
  return img.encodeJpg(image);
}

void main() {
  group('extractMediaCaptureMetadata', () {
    test('从真实 JPEG APP1 段解析器材、参数、时间与坐标', () {
      final bytes = _jpegWithExif(
        make: 'SONY',
        model: 'ILCE-7M4',
        lens: 'FE 24-70mm F2.8 GM II',
        focalLength: 35,
        fNumber: 2.8,
        exposureTime: 1 / 500,
        iso: 400,
        dateTimeOriginal: '2026:07:28 06:14:32',
        latitudeDms: <double>[30, 14, 30],
        latitudeRef: 'N',
        longitudeDms: <double>[120, 8, 45],
        longitudeRef: 'E',
      );

      final metadata = _extractor.extractMediaCaptureMetadata(bytes);

      expect(metadata.cameraMake, 'SONY');
      expect(metadata.cameraModel, 'ILCE-7M4');
      expect(metadata.lensModel, 'FE 24-70mm F2.8 GM II');
      expect(metadata.focalLengthMm, closeTo(35, 0.01));
      expect(metadata.apertureFNumber, closeTo(2.8, 0.01));
      expect(metadata.shutterSpeedSeconds, closeTo(1 / 500, 0.0001));
      expect(metadata.isoSensitivity, 400);
      expect(metadata.capturedAt, DateTime(2026, 7, 28, 6, 14, 32).toUtc());
      expect(metadata.gpsLatitude, closeTo(30 + 14 / 60 + 30 / 3600, 0.0001));
      expect(metadata.gpsLongitude, closeTo(120 + 8 / 60 + 45 / 3600, 0.0001));
    });

    test('南纬西经取负号', () {
      final bytes = _jpegWithExif(
        latitudeDms: <double>[33, 51, 30],
        latitudeRef: 'S',
        longitudeDms: <double>[151, 12, 40],
        longitudeRef: 'W',
      );

      final metadata = _extractor.extractMediaCaptureMetadata(bytes);

      expect(
        metadata.gpsLatitude,
        closeTo(-(33 + 51 / 60 + 30 / 3600), 0.0001),
      );
      expect(
        metadata.gpsLongitude,
        closeTo(-(151 + 12 / 60 + 40 / 3600), 0.0001),
      );
    });

    test('无 EXIF 的 JPEG 返回空元数据而不是抛错', () {
      final bytes = img.encodeJpg(img.Image(width: 4, height: 4));

      expect(_extractor.extractMediaCaptureMetadata(bytes).isEmpty, isTrue);
    });

    test('非图片字节与截断字节返回空元数据', () {
      expect(
        _extractor.extractMediaCaptureMetadata(
          Uint8List.fromList(<int>[1, 2, 3, 4]),
        ),
        ExtractedMediaCaptureMetadata.empty,
      );
      final truncated = Uint8List.sublistView(
        _jpegWithExif(make: 'SONY'),
        0,
        8,
      );
      expect(_extractor.extractMediaCaptureMetadata(truncated).isEmpty, isTrue);
    });

    test('相机时钟未初始化的年份被拒绝', () {
      final bytes = _jpegWithExif(dateTimeOriginal: '1800:01:01 00:00:00');

      expect(_extractor.extractMediaCaptureMetadata(bytes).capturedAt, isNull);
    });

    test('缺少方向参考的坐标不落库', () {
      final bytes = _jpegWithExif(latitudeDms: <double>[30, 14, 30]);

      expect(_extractor.extractMediaCaptureMetadata(bytes).gpsLatitude, isNull);
    });
  });

  group('ExtractedMediaCaptureMetadata.discloseOnly', () {
    const full = ExtractedMediaCaptureMetadata(
      cameraMake: 'SONY',
      cameraModel: 'ILCE-7M4',
      lensModel: 'FE 24-70mm F2.8 GM II',
      focalLengthMm: 35,
      apertureFNumber: 2.8,
      shutterSpeedSeconds: 0.002,
      isoSensitivity: 400,
      gpsLatitude: 30.24,
      gpsLongitude: 120.14,
    );

    test('默认披露集合包含四组', () {
      expect(
        kDefaultCaptureDisclosure,
        CaptureMetadataDisclosureGroup.values.toSet(),
      );
    });

    test('关闭拍摄地点后坐标整组消失且不出现在 wire 上', () {
      final disclosed = full.discloseOnly(<CaptureMetadataDisclosureGroup>{
        CaptureMetadataDisclosureGroup.gear,
        CaptureMetadataDisclosureGroup.parameters,
      });

      expect(disclosed.gpsLatitude, isNull);
      expect(disclosed.gpsLongitude, isNull);
      expect(disclosed.hasPlace, isFalse);
      expect(disclosed.toWire().containsKey('gpsLatitude'), isFalse);
      expect(disclosed.toWire().containsKey('gpsLongitude'), isFalse);
      // 未关闭的分组必须原样保留。
      expect(disclosed.cameraModel, 'ILCE-7M4');
      expect(disclosed.isoSensitivity, 400);
    });

    test('关闭全部分组后 payload 为空，等价于相机未记录', () {
      final disclosed = full.discloseOnly(
        const <CaptureMetadataDisclosureGroup>{},
      );

      expect(disclosed, ExtractedMediaCaptureMetadata.empty);
      expect(disclosed.toWire(), isEmpty);
    });

    test('availableGroups 只包含真正解析到的分组', () {
      const gearOnly = ExtractedMediaCaptureMetadata(cameraModel: 'X-T5');

      expect(gearOnly.availableGroups, <CaptureMetadataDisclosureGroup>{
        CaptureMetadataDisclosureGroup.gear,
      });
    });

    test('toString 不泄露坐标与拍摄时间', () {
      final metadata = ExtractedMediaCaptureMetadata(
        gpsLatitude: 30.2401,
        gpsLongitude: 120.1402,
        capturedAt: DateTime.utc(2026, 7, 28, 6, 14, 32),
      );

      final text = metadata.toString();

      expect(text, isNot(contains('30.24')));
      expect(text, isNot(contains('120.14')));
      expect(text, isNot(contains('2026')));
    });
  });

  group('CaptureMetadataDisclosureGroup wire', () {
    test('wire 取值与解析互为逆运算', () {
      for (final group in CaptureMetadataDisclosureGroup.values) {
        expect(CaptureMetadataDisclosureGroup.fromWire(group.wire), group);
      }
      expect(CaptureMetadataDisclosureGroup.fromWire('unknown'), isNull);
    });
  });
}
