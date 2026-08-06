import 'package:quwoquan_app/service/content_service/content/post/domain/solar_position.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';

/// 摄影标签在标签树中的根路径。
const String kPhotographyTagRoot = 'Topic/摄影';

/// 把 [ExtractedMediaCaptureMetadata] 派生成 `Topic/摄影/**` tagRef。
///
/// 这是 EXIF 通道的消费端：taxonomy 侧
/// `bootstrap_tags_topic_photography.py` 在每个标签的 description 里写明了绑定字段与
/// 阈值，本文件的阈值必须与之逐条一致。阈值是产品口径而非实现细节，两处漂移会让同一
/// 张照片在不同版本被打上不同标签。
///
/// 派生结果只覆盖 EXIF 能证明的事实。中间地带刻意不打标：如果每张照片都能拿到某个
/// 参数标签，这一维度在召回里就没有区分度了。
///
/// 隐私：输入必须是已经过 [ExtractedMediaCaptureMetadata.discloseOnly] 裁剪的对象。创作者关闭
/// 某组后该组字段为 null，本推导自然不产出对应标签，这就是「关闭后已派生 tagRef 同步
/// 撤回」的端侧一半。标签树的子树与披露分组一一对应，所以撤回是「整棵子树消失」而不是
/// 逐条比对：`器材/**` ↔ gear，`拍摄参数/**` ↔ parameters，`光线条件/**` ↔ time+place。
final class CapturePhotographyTagDeriver {
  const CapturePhotographyTagDeriver();

  /// 按标签树路径顺序返回去重后的 tagRef。
  List<String> derive(ExtractedMediaCaptureMetadata metadata) {
    final refs = <String>{
      ..._gearRefs(metadata),
      ..._parameterRefs(metadata),
      ..._lightRefs(metadata),
    };
    final sorted = refs.toList()..sort();
    return sorted;
  }

  Iterable<String> _gearRefs(ExtractedMediaCaptureMetadata m) {
    final refs = <String>[];
    final body = _bodyType(m);
    if (body != null) refs.add('$kPhotographyTagRoot/器材/机身类型/$body');

    for (final lens in _lensTypes(m.lensModel)) {
      refs.add('$kPhotographyTagRoot/器材/镜头类型/$lens');
    }
    return refs;
  }

  Iterable<String> _parameterRefs(ExtractedMediaCaptureMetadata m) {
    final refs = <String>[];

    final focal = _focalRange(m.focalLengthMm);
    if (focal != null) refs.add('$kPhotographyTagRoot/拍摄参数/焦段/$focal');

    final shutter = m.shutterSpeedSeconds;
    if (shutter != null) {
      if (shutter >= 1.0) {
        refs.add('$kPhotographyTagRoot/拍摄参数/快门/长曝光');
      } else if (shutter >= 1 / 15) {
        refs.add('$kPhotographyTagRoot/拍摄参数/快门/慢门');
      } else if (shutter <= 1 / 1000) {
        refs.add('$kPhotographyTagRoot/拍摄参数/快门/高速快门');
      }
    }

    final aperture = m.apertureFNumber;
    if (aperture != null) {
      if (aperture <= 2.0) {
        refs.add('$kPhotographyTagRoot/拍摄参数/光圈/大光圈虚化');
      } else if (aperture >= 11.0) {
        refs.add('$kPhotographyTagRoot/拍摄参数/光圈/小光圈全景深');
      }
    }

    final iso = m.isoSensitivity;
    if (iso != null) {
      if (iso >= 3200) {
        refs.add('$kPhotographyTagRoot/拍摄参数/感光度/高感夜拍');
      } else if (iso <= 200) {
        refs.add('$kPhotographyTagRoot/拍摄参数/感光度/低感画质');
      }
    }
    return refs;
  }

  /// 光线条件需要拍摄时间与坐标同时存在：太阳高度角是二者的函数。
  ///
  /// 创作者关掉 `place` 或 `time` 任一组就整组不产出——只有本地时间无法区分「北欧夏季
  /// 的午夜白昼」与「赤道的午夜黑夜」，按钟点粗判会打出错误标签。
  Iterable<String> _lightRefs(ExtractedMediaCaptureMetadata m) {
    final capturedAt = m.capturedAt;
    final latitude = m.gpsLatitude;
    final longitude = m.gpsLongitude;
    if (capturedAt == null || latitude == null || longitude == null) {
      return const <String>[];
    }
    final elevation = solarElevationDegrees(
      capturedAt: capturedAt,
      latitude: latitude,
      longitude: longitude,
    );
    final String window;
    if (elevation < -6) {
      window = '夜间无日光';
    } else if (elevation < -4) {
      window = '蓝调时刻';
    } else if (elevation < 6) {
      window = '金色时刻';
    } else if (elevation <= 60) {
      window = '白天漫射光';
    } else {
      window = '正午强光';
    }
    return <String>['$kPhotographyTagRoot/光线条件/$window'];
  }

  String? _focalRange(double? focalLengthMm) {
    final focal = focalLengthMm;
    if (focal == null || focal <= 0) return null;
    if (focal < 20) return '超广角';
    if (focal < 35) return '广角';
    if (focal < 70) return '标准';
    if (focal < 135) return '中长焦';
    if (focal < 300) return '长焦';
    return '超长焦';
  }

  /// 机身类别按厂商与型号特征判定，不建具体型号标签。
  ///
  /// 具体型号是实体而非标签：型号每年新增，做成标签会让标签树被机型无限撑大。
  /// `sameGearUsed` 交集直接比对 `cameraModel` 字符串，不需要经过标签。
  String? _bodyType(ExtractedMediaCaptureMetadata m) {
    final make = (m.cameraMake ?? '').toUpperCase();
    final model = (m.cameraModel ?? '').toUpperCase();
    if (make.isEmpty && model.isEmpty) return null;
    final combined = '$make $model';

    if (_containsAny(combined, const <String>[
      'DJI',
      'AUTEL',
      'MAVIC',
      'PHANTOM',
      'AIR 2S',
    ])) {
      return '无人机航拍';
    }
    if (_containsAny(combined, const <String>[
      'GOPRO',
      'HERO',
      'INSTA360',
      'OSMO ACTION',
      'ACTION 4',
    ])) {
      return '运动相机';
    }
    if (_containsAny(combined, const <String>[
      'APPLE',
      'IPHONE',
      'XIAOMI',
      'REDMI',
      'HUAWEI',
      'HONOR',
      'OPPO',
      'VIVO',
      'ONEPLUS',
      'SAMSUNG',
      'GOOGLE',
      'PIXEL',
      'MEIZU',
      'REALME',
    ])) {
      return '手机拍摄';
    }
    if (_containsAny(combined, const <String>[
      'GFX',
      'HASSELBLAD',
      'X1D',
      'PHASE ONE',
      'IQ4',
      '645Z',
    ])) {
      return '中画幅';
    }
    if (_containsAny(combined, const <String>[
      'EOS 5D',
      'EOS 6D',
      'EOS 1D',
      'EOS 90D',
      'EOS 80D',
      'D850',
      'D780',
      'D750',
      'D7500',
      'D5600',
      'K-1',
      'K-3',
      'SLT-',
    ])) {
      return '单反相机';
    }
    if (_containsAny(combined, const <String>[
      'EPSON',
      'PLUSTEK',
      'COOLSCAN',
      'NORITSU',
      'FRONTIER SP',
    ])) {
      return '胶片扫描';
    }
    if (_containsAny(combined, const <String>[
      'ILCE-6',
      'ILCE-5',
      'ZV-E10',
      'X-T',
      'X-S',
      'X-E',
      'X-PRO',
      'X100',
      'EOS R7',
      'EOS R10',
      'EOS R50',
      'EOS M',
      'Z 50',
      'Z 30',
      'Z FC',
      'E-M',
      'OM-',
      'DC-G',
      'DC-GH',
    ])) {
      return '半画幅微单';
    }
    if (_containsAny(combined, const <String>[
      'ILCE-7',
      'ILCE-1',
      'ILCE-9',
      'EOS R',
      'Z 6',
      'Z 7',
      'Z 8',
      'Z 9',
      'DC-S',
      'SIGMA FP',
      'L-MOUNT',
    ])) {
      return '全画幅微单';
    }
    return null;
  }

  /// 镜头类别可以叠加：微距变焦既是变焦也是微距。
  List<String> _lensTypes(String? lensModel) {
    final lens = (lensModel ?? '').trim();
    if (lens.isEmpty) return const <String>[];
    final upper = lens.toUpperCase();
    final types = <String>[];

    if (_containsAny(upper, const <String>['MACRO', '微距', 'MP-E'])) {
      types.add('微距镜头');
    }
    if (_containsAny(upper, const <String>['FISHEYE', '鱼眼'])) {
      types.add('鱼眼镜头');
    }
    if (_containsAny(upper, const <String>['TS-E', 'PC-E', 'TILT', '移轴'])) {
      types.add('移轴镜头');
    }
    // 变焦镜头的型号里带焦距区间（`24-70mm`），定焦只有单一焦距（`35mm`）。
    if (RegExp(r'\d+(\.\d+)?\s*-\s*\d+(\.\d+)?\s*MM').hasMatch(upper)) {
      types.add('变焦镜头');
    } else if (RegExp(r'\d+(\.\d+)?\s*MM').hasMatch(upper)) {
      types.add('定焦镜头');
    }
    return types;
  }

  bool _containsAny(String haystack, List<String> needles) {
    for (final needle in needles) {
      if (haystack.contains(needle)) return true;
    }
    return false;
  }
}
