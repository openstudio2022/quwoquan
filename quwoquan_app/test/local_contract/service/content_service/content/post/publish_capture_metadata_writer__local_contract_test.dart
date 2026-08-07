import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/publish_capture_metadata_writer.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';

void main() {
  test('已选素材的拍摄事实写入发布设置且只保留可披露分组', () {
    final extracted = ExtractedMediaCaptureMetadata(
      cameraModel: 'ILCE-7M4',
      gpsLatitude: 30.24,
      gpsLongitude: 120.14,
      capturedAt: DateTime.utc(2026, 8, 7, 6, 14),
    );
    const settings = PublishSettings(
      captureDisclosure: <CaptureMetadataDisclosureGroup>{
        CaptureMetadataDisclosureGroup.gear,
        CaptureMetadataDisclosureGroup.place,
      },
    );

    final updated = writeSelectedMediaCaptureMetadata(settings, extracted);

    expect(updated.captureMetadata, extracted);
    expect(updated.captureDisclosure, <CaptureMetadataDisclosureGroup>{
      CaptureMetadataDisclosureGroup.gear,
      CaptureMetadataDisclosureGroup.place,
    });
    expect(
      updated.disclosedCaptureMetadata,
      const ExtractedMediaCaptureMetadata(
        cameraModel: 'ILCE-7M4',
        gpsLatitude: 30.24,
        gpsLongitude: 120.14,
      ),
    );
  });
}
