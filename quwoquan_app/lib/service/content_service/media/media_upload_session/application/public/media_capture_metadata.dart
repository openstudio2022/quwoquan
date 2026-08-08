import 'dart:typed_data';

/// 拍摄元数据的披露分组。
///
/// 创作者可逐组关闭；关闭后该组派生的 tagRef 与交集事实必须同步撤回，不得残留。
/// 分组是端云同一套闭集：端侧按组裁剪后再上报，服务端按组撤回既有派生事实。
enum CaptureMetadataDisclosureGroup {
  /// 机身与镜头（`cameraMake` / `cameraModel` / `lensModel`）。
  gear('gear'),

  /// 曝光参数（`focalLengthMm` / `apertureFNumber` / `shutterSpeedSeconds` /
  /// `isoSensitivity`）。
  parameters('parameters'),

  /// 拍摄地点（`gpsLatitude` / `gpsLongitude`）。PII。
  place('place'),

  /// 拍摄时间（`capturedAt`）。PII。
  time('time');

  const CaptureMetadataDisclosureGroup(this.wire);

  /// 与服务端 `CaptureDisclosureGroup` 枚举同名的线上取值。
  final String wire;

  static CaptureMetadataDisclosureGroup? fromWire(String value) {
    for (final group in CaptureMetadataDisclosureGroup.values) {
      if (group.wire == value) return group;
    }
    return null;
  }
}

/// 默认披露集合：全字段默认提取并参与推荐/交集。
///
/// 该默认值是产品决策，配套要求见 [ExtractedMediaCaptureMetadata]：`place` 与 `time` 属 PII，
/// 不得进入日志与分享卡，且首次发布必须给出一次性告知。
const Set<CaptureMetadataDisclosureGroup> kDefaultCaptureDisclosure =
    <CaptureMetadataDisclosureGroup>{
      CaptureMetadataDisclosureGroup.gear,
      CaptureMetadataDisclosureGroup.parameters,
      CaptureMetadataDisclosureGroup.place,
      CaptureMetadataDisclosureGroup.time,
    };

/// 从原始素材解析出的拍摄事实。
///
/// 这是端侧唯一的拍摄元数据真相源：解析只发生一次（上传前），之后所有派生物
/// （器材/参数/光线 tagRef、机位实体绑定、季节窗口交集）都从本对象推导。
///
/// 隐私约束：
/// - [gpsLatitude] / [gpsLongitude] / [capturedAt] 是 PII，序列化后在服务端标记
///   `classification: PII` + `log_policy: mask`；端侧不得写入日志或分享卡文案。
/// - 未披露分组必须在离开端侧之前被裁剪，见 [discloseOnly]。
class ExtractedMediaCaptureMetadata {
  const ExtractedMediaCaptureMetadata({
    this.cameraMake,
    this.cameraModel,
    this.lensModel,
    this.focalLengthMm,
    this.apertureFNumber,
    this.shutterSpeedSeconds,
    this.isoSensitivity,
    this.capturedAt,
    this.gpsLatitude,
    this.gpsLongitude,
  });

  /// 机身厂商，如 `SONY`。
  final String? cameraMake;

  /// 机身型号，如 `ILCE-7M4`。
  final String? cameraModel;

  /// 镜头型号，如 `FE 24-70mm F2.8 GM II`。
  final String? lensModel;

  /// 实际焦距（毫米）。
  final double? focalLengthMm;

  /// 光圈 F 值，如 `2.8`。
  final double? apertureFNumber;

  /// 快门时间（秒）。`1/500` 记作 `0.002`。
  final double? shutterSpeedSeconds;

  /// 感光度 ISO。
  final int? isoSensitivity;

  /// 拍摄时间。PII。
  final DateTime? capturedAt;

  /// 拍摄地纬度。PII。
  final double? gpsLatitude;

  /// 拍摄地经度。PII。
  final double? gpsLongitude;

  /// 没有解析到任何字段的空元数据。
  static const ExtractedMediaCaptureMetadata empty =
      ExtractedMediaCaptureMetadata();

  bool get hasGear =>
      cameraMake != null || cameraModel != null || lensModel != null;

  bool get hasParameters =>
      focalLengthMm != null ||
      apertureFNumber != null ||
      shutterSpeedSeconds != null ||
      isoSensitivity != null;

  bool get hasPlace => gpsLatitude != null && gpsLongitude != null;

  bool get hasTime => capturedAt != null;

  bool get isEmpty => !hasGear && !hasParameters && !hasPlace && !hasTime;

  bool get isNotEmpty => !isEmpty;

  /// 本次解析实际命中的分组，用于决定发布面板显示哪些开关。
  Set<CaptureMetadataDisclosureGroup> get availableGroups =>
      <CaptureMetadataDisclosureGroup>{
        if (hasGear) CaptureMetadataDisclosureGroup.gear,
        if (hasParameters) CaptureMetadataDisclosureGroup.parameters,
        if (hasPlace) CaptureMetadataDisclosureGroup.place,
        if (hasTime) CaptureMetadataDisclosureGroup.time,
      };

  /// 只保留 [disclosed] 中的分组，其余分组整体置空。
  ///
  /// 这是「关闭某组后已派生事实必须同步撤回」的端侧一半：上报前裁剪，使服务端
  /// 收到的 payload 本身不含被关闭分组。服务端据此撤回既有 tagRef 与交集事实。
  ExtractedMediaCaptureMetadata discloseOnly(
    Set<CaptureMetadataDisclosureGroup> disclosed,
  ) {
    final gear = disclosed.contains(CaptureMetadataDisclosureGroup.gear);
    final parameters = disclosed.contains(
      CaptureMetadataDisclosureGroup.parameters,
    );
    final place = disclosed.contains(CaptureMetadataDisclosureGroup.place);
    final time = disclosed.contains(CaptureMetadataDisclosureGroup.time);
    return ExtractedMediaCaptureMetadata(
      cameraMake: gear ? cameraMake : null,
      cameraModel: gear ? cameraModel : null,
      lensModel: gear ? lensModel : null,
      focalLengthMm: parameters ? focalLengthMm : null,
      apertureFNumber: parameters ? apertureFNumber : null,
      shutterSpeedSeconds: parameters ? shutterSpeedSeconds : null,
      isoSensitivity: parameters ? isoSensitivity : null,
      capturedAt: time ? capturedAt : null,
      gpsLatitude: place ? gpsLatitude : null,
      gpsLongitude: place ? gpsLongitude : null,
    );
  }

  /// 线上表示。空字段整体省略，使被裁剪分组在 wire 上不可区分于「相机未记录」。
  Map<String, Object?> toWire() => <String, Object?>{
    if (cameraMake != null) 'cameraMake': cameraMake,
    if (cameraModel != null) 'cameraModel': cameraModel,
    if (lensModel != null) 'lensModel': lensModel,
    if (focalLengthMm != null) 'focalLengthMm': focalLengthMm,
    if (apertureFNumber != null) 'apertureFNumber': apertureFNumber,
    if (shutterSpeedSeconds != null) 'shutterSpeedSeconds': shutterSpeedSeconds,
    if (isoSensitivity != null) 'isoSensitivity': isoSensitivity,
    if (capturedAt != null) 'capturedAt': capturedAt!.toUtc().toIso8601String(),
    if (gpsLatitude != null) 'gpsLatitude': gpsLatitude,
    if (gpsLongitude != null) 'gpsLongitude': gpsLongitude,
  };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ExtractedMediaCaptureMetadata &&
          other.cameraMake == cameraMake &&
          other.cameraModel == cameraModel &&
          other.lensModel == lensModel &&
          other.focalLengthMm == focalLengthMm &&
          other.apertureFNumber == apertureFNumber &&
          other.shutterSpeedSeconds == shutterSpeedSeconds &&
          other.isoSensitivity == isoSensitivity &&
          other.capturedAt == capturedAt &&
          other.gpsLatitude == gpsLatitude &&
          other.gpsLongitude == gpsLongitude;

  @override
  int get hashCode => Object.hash(
    cameraMake,
    cameraModel,
    lensModel,
    focalLengthMm,
    apertureFNumber,
    shutterSpeedSeconds,
    isoSensitivity,
    capturedAt,
    gpsLatitude,
    gpsLongitude,
  );

  /// 诊断字符串。刻意不包含 GPS 与拍摄时间，避免 PII 随 `toString` 进入日志。
  @override
  String toString() =>
      'ExtractedMediaCaptureMetadata(cameraModel: $cameraModel, lensModel: $lensModel, '
      'focalLengthMm: $focalLengthMm, apertureFNumber: $apertureFNumber, '
      'shutterSpeedSeconds: $shutterSpeedSeconds, iso: $isoSensitivity, '
      'hasPlace: $hasPlace, hasTime: $hasTime)';
}

/// Public, deterministic capture-metadata extraction seam.
///
/// EXIF parsing libraries and platform details remain in the object's adapter.
abstract interface class MediaCaptureMetadataExtractor {
  ExtractedMediaCaptureMetadata extractMediaCaptureMetadata(Uint8List bytes);
}
