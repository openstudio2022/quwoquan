import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart';

/// Applies facts parsed from the selected lead image to the publication only.
///
/// This stays out of draft serialization: [PublishSettings] owns the ephemeral
/// facts until the publish request applies its disclosure boundary.
PublishSettings writeSelectedMediaCaptureMetadata(
  PublishSettings settings,
  ExtractedMediaCaptureMetadata captureMetadata,
) {
  return settings.copyWith(
    captureMetadata: captureMetadata,
    captureDisclosure: settings.captureDisclosure.intersection(
      captureMetadata.availableGroups,
    ),
  );
}
