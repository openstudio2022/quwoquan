import 'dart:typed_data';

import 'package:image/image.dart' as img;
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';

/// 从原始图片字节解析拍摄元数据。
///
/// 只读取 JPEG 的 APP1/Exif 段，不解码像素：扫描 marker 找到 TIFF 块后交给
/// `package:image` 的 EXIF 解析器。纯 Dart 实现，无 `dart:io`，Web / 鸿蒙同样可用。
///
/// 任何解析失败都返回 [ExtractedMediaCaptureMetadata.empty] 而非抛出：拍摄元数据是增强信号，
/// 缺失不得阻断发布。
final class ExifMediaCaptureMetadataExtractor
    implements MediaCaptureMetadataExtractor {
  const ExifMediaCaptureMetadataExtractor();

  @override
  ExtractedMediaCaptureMetadata extractMediaCaptureMetadata(Uint8List bytes) {
    final tiff = _locateExifTiffBlock(bytes);
    if (tiff == null) {
      return ExtractedMediaCaptureMetadata.empty;
    }
    final exif = img.ExifData();
    try {
      // `ExifData.read` 无论成功与否都返回 false，其返回值不可用于判定；
      // 解析结果是否为空才是唯一可靠信号。非 TIFF 输入会原样留下空 directory。
      exif.read(img.InputBuffer(tiff, bigEndian: true));
    } catch (_) {
      // 截断或损坏的 EXIF 段：按「相机未记录」处理。
      return ExtractedMediaCaptureMetadata.empty;
    }
    try {
      return _metadataFromExif(exif);
    } catch (_) {
      return ExtractedMediaCaptureMetadata.empty;
    }
  }
}

/// JPEG SOI。
const int _markerSoi = 0xD8;

/// JPEG SOS：其后是熵编码扫描数据，不会再有 APP1，扫描到此即可停止。
const int _markerSos = 0xDA;

/// JPEG EOI。
const int _markerEoi = 0xD9;

/// APP1，EXIF 所在段。
const int _markerApp1 = 0xE1;

/// `Exif\x00\x00`。
const List<int> _exifSignature = <int>[0x45, 0x78, 0x69, 0x66, 0x00, 0x00];

/// 定位 JPEG 中的 EXIF TIFF 块。返回的视图从 TIFF header（`II` / `MM`）开始。
Uint8List? _locateExifTiffBlock(Uint8List bytes) {
  if (bytes.length < 4 || bytes[0] != 0xFF || bytes[1] != _markerSoi) {
    return null;
  }
  var offset = 2;
  while (offset + 4 <= bytes.length) {
    if (bytes[offset] != 0xFF) {
      // 段边界丢失，无法继续可靠扫描。
      return null;
    }
    // 允许 0xFF 填充字节。
    var markerOffset = offset;
    while (markerOffset < bytes.length && bytes[markerOffset] == 0xFF) {
      markerOffset++;
    }
    if (markerOffset >= bytes.length) {
      return null;
    }
    final marker = bytes[markerOffset];
    if (marker == _markerSos || marker == _markerEoi) {
      return null;
    }
    final lengthOffset = markerOffset + 1;
    if (lengthOffset + 2 > bytes.length) {
      return null;
    }
    final segmentLength = (bytes[lengthOffset] << 8) | bytes[lengthOffset + 1];
    if (segmentLength < 2) {
      return null;
    }
    final payloadStart = lengthOffset + 2;
    final payloadEnd = lengthOffset + segmentLength;
    if (payloadEnd > bytes.length) {
      return null;
    }
    if (marker == _markerApp1 &&
        _hasExifSignature(bytes, payloadStart, payloadEnd)) {
      final tiffStart = payloadStart + _exifSignature.length;
      if (tiffStart >= payloadEnd) {
        return null;
      }
      return Uint8List.sublistView(bytes, tiffStart, payloadEnd);
    }
    offset = payloadEnd;
  }
  return null;
}

bool _hasExifSignature(Uint8List bytes, int start, int end) {
  if (end - start < _exifSignature.length) {
    return false;
  }
  for (var i = 0; i < _exifSignature.length; i++) {
    if (bytes[start + i] != _exifSignature[i]) {
      return false;
    }
  }
  return true;
}

ExtractedMediaCaptureMetadata _metadataFromExif(img.ExifData exif) {
  final image = exif.imageIfd;
  final photo = exif.exifIfd;
  final gps = exif.gpsIfd;
  return ExtractedMediaCaptureMetadata(
    cameraMake: _ascii(image['Make']),
    cameraModel: _ascii(image['Model']),
    lensModel: _ascii(photo['LensModel']),
    focalLengthMm: _positiveDouble(photo['FocalLength']),
    apertureFNumber: _positiveDouble(photo['FNumber']),
    shutterSpeedSeconds: _positiveDouble(photo['ExposureTime']),
    isoSensitivity: _positiveInt(photo['ISOSpeed']),
    capturedAt: _exifDateTime(_ascii(photo['DateTimeOriginal'])),
    gpsLatitude: _tryReadCoordinate(
      gps['GPSLatitude'],
      _ascii(gps['GPSLatitudeRef']),
    ),
    gpsLongitude: _tryReadCoordinate(
      gps['GPSLongitude'],
      _ascii(gps['GPSLongitudeRef']),
    ),
  );
}

String? _ascii(img.IfdValue? value) {
  if (value == null) return null;
  // EXIF ascii 以 NUL 结尾，部分机身还会补空格。
  final text = value.toString().replaceAll('\u0000', '').trim();
  return text.isEmpty ? null : text;
}

double? _positiveDouble(img.IfdValue? value) {
  if (value == null) return null;
  final resolved = value.toDouble();
  if (!resolved.isFinite || resolved <= 0) return null;
  return resolved;
}

int? _positiveInt(img.IfdValue? value) {
  if (value == null) return null;
  final resolved = value.toInt();
  return resolved > 0 ? resolved : null;
}

/// EXIF `DateTimeOriginal` 是 `YYYY:MM:DD HH:MM:SS` 本地时间，无时区。
///
/// 按本地时间解析并转成 UTC；相机未设置时区是常态，这里不臆造偏移。
DateTime? _exifDateTime(String? raw) {
  if (raw == null || raw.length < 19) return null;
  final year = int.tryParse(raw.substring(0, 4));
  final month = int.tryParse(raw.substring(5, 7));
  final day = int.tryParse(raw.substring(8, 10));
  final hour = int.tryParse(raw.substring(11, 13));
  final minute = int.tryParse(raw.substring(14, 16));
  final second = int.tryParse(raw.substring(17, 19));
  if (year == null ||
      month == null ||
      day == null ||
      hour == null ||
      minute == null ||
      second == null) {
    return null;
  }
  if (year < 1826 || month < 1 || month > 12 || day < 1 || day > 31) {
    // 1826 年是已知最早的照片；更早的值只可能来自未初始化的相机时钟。
    return null;
  }
  if (hour > 23 || minute > 59 || second > 60) {
    return null;
  }
  return DateTime(year, month, day, hour, minute, second).toUtc();
}

/// GPS 坐标是 `[度, 分, 秒]` 三个 rational，方向由 `N/S` `E/W` 决定符号。
double? _tryReadCoordinate(img.IfdValue? value, String? reference) {
  if (value == null || reference == null) return null;
  final double degrees;
  final double minutes;
  final double seconds;
  try {
    degrees = value.toDouble(0);
    minutes = value.toDouble(1);
    seconds = value.toDouble(2);
  } catch (_) {
    return null;
  }
  if (!degrees.isFinite || !minutes.isFinite || !seconds.isFinite) {
    return null;
  }
  final magnitude = degrees + minutes / 60 + seconds / 3600;
  if (!magnitude.isFinite) return null;
  final direction = reference.toUpperCase();
  final signed = switch (direction) {
    'N' || 'E' => magnitude,
    'S' || 'W' => -magnitude,
    _ => null,
  };
  if (signed == null) return null;
  final limit = (direction == 'N' || direction == 'S') ? 90.0 : 180.0;
  if (signed.abs() > limit) return null;
  return signed;
}
