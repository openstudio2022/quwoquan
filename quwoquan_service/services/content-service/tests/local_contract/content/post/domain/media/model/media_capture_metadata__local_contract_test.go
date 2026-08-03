// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/capture-metadata-disclosure/spec.md#gwt-001
package model_test

import (
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

func TestMediaAssetCaptureMetadataValidatesAndSurvivesSnapshot(t *testing.T) {
	now := time.Date(2026, 7, 31, 8, 0, 0, 0, time.UTC)
	focal, aperture, shutter := 35.0, 2.8, 1.0/500.0
	iso := 100
	latitude, longitude := 30.25, 102.75
	capturedAt := now.Add(-72 * time.Hour)
	asset, err := CreateMediaAsset(CreateMediaAssetParams{
		ID: "media-capture", OwnerID: "persona-capture", SourceSessionID: "session-capture",
		ObjectKey: "private/media-capture/source.jpg",
		SHA256:    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType: MediaTypeImage, MimeType: "image/jpeg", FileSize: 1024,
		AccessPolicy: AccessPolicyOwnerOnly, ProcessingRequired: true, Now: now,
		CaptureMetadata: CaptureMetadata{
			CameraMake: " SONY ", CameraModel: " ILCE-7M4 ",
			LensModel: " FE 35mm F1.4 GM ", FocalLengthMM: &focal,
			ApertureFNumber: &aperture, ShutterSpeedSeconds: &shutter,
			ISOSensitivity: &iso, CapturedAt: &capturedAt,
			GPSLatitude: &latitude, GPSLongitude: &longitude,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	snapshot := asset.Snapshot()
	if snapshot.CaptureMetadata.CameraMake != "SONY" ||
		snapshot.CaptureMetadata.CapturedAt == nil ||
		snapshot.CaptureMetadata.GPSLatitude == nil {
		t.Fatalf("capture metadata was not normalized and preserved: %+v", snapshot.CaptureMetadata)
	}
	if _, err := RestoreMediaAsset(snapshot); err != nil {
		t.Fatalf("restore capture metadata: %v", err)
	}
}

func TestMediaAssetCaptureMetadataRejectsPIIAndMediaBoundaryViolations(t *testing.T) {
	now := time.Date(2026, 7, 31, 8, 0, 0, 0, time.UTC)
	latitude := 31.0
	future := now.Add(48 * time.Hour)
	base := CreateMediaAssetParams{
		ID: "media-capture-invalid", OwnerID: "persona-capture",
		SourceSessionID: "session-capture-invalid",
		ObjectKey:       "private/media-capture-invalid/source.jpg",
		SHA256:          "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		MediaType:       MediaTypeImage, MimeType: "image/jpeg", FileSize: 1024,
		AccessPolicy: AccessPolicyOwnerOnly, ProcessingRequired: true, Now: now,
	}
	base.CaptureMetadata = CaptureMetadata{GPSLatitude: &latitude}
	if _, err := CreateMediaAsset(base); err == nil {
		t.Fatal("partial GPS pair must be rejected")
	}
	base.CaptureMetadata = CaptureMetadata{CapturedAt: &future}
	if _, err := CreateMediaAsset(base); err == nil {
		t.Fatal("future capture time must be rejected")
	}
	base.MediaType = MediaTypeVideo
	base.MimeType = "video/mp4"
	base.CaptureMetadata = CaptureMetadata{CameraModel: "ILCE-7M4"}
	if _, err := CreateMediaAsset(base); err == nil {
		t.Fatal("video capture metadata must be rejected")
	}
}
