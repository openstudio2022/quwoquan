// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: record-media-processing-result-local
// readiness_case: update-media-asset-access-policy-local
// readiness_case: get-owned-media-asset-local
// readiness_case: get-media-asset-reference-local
// readiness_case: get-media-asset-delivery-reference-local
// readiness_case: get-media-asset-local
// readiness_case: discard-media-asset-local
// readiness_case: select-auto-video-cover-local
// readiness_case: select-manual-video-cover-local
package application_test

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

const readinessMediaDigest = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"

func TestMediaAssetCommandsAndReadersExecuteTheObjectFacades(t *testing.T) {
	now := time.Date(2030, time.August, 9, 10, 11, 12, 0, time.UTC)
	store := mediacontract.NewMediaStore()
	service := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		readinessMediaGateway{},
		mediaapp.WithClock(func() time.Time { return now }),
	)
	const ownerID = "persona-media-readiness"

	imageID := seedReadinessMediaAsset(
		t,
		store,
		now,
		"media-readiness-image",
		ownerID,
		mediamodel.MediaTypeImage,
		"image/jpeg",
		mediamodel.AccessPolicyOwnerOnly,
		true,
	)
	processedImage, err := service.RecordMediaProcessingResult(
		mediaReadinessContext("process-image"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID:    imageID,
			Processing: mediamodel.ProcessingStatusReady,
			Descriptor: mediamodel.MediaProcessingDescriptor{
				Image: mediamodel.ImageProcessingDescriptor{
					ProcessorProfile:         "content_image_normalization",
					ImageWidth:               1200,
					ImageHeight:              900,
					ImageDeliveryMimeType:    "image/jpeg",
					ImageNormalizedObjectKey: "media/processed/image/" + imageID + "/v2/source.jpg",
					ImagePublicSliceKey:      "media/image/s/asset/" + imageID + "/v2/source.jpg",
					ImageDominantColor:       "#1A2B3C",
					ImageLQIP:                "data:image/jpeg;base64,/9j/2Q==",
					ImageContentProfile:      "photographic",
					DerivativePolicyVersion:  1,
				},
			},
		},
	)
	if err != nil || processedImage.ProcessingStatus != mediamodel.ProcessingStatusReady {
		t.Fatalf("record ready image descriptor: result=%+v err=%v", processedImage, err)
	}

	updated, err := service.UpdateMediaAssetAccessPolicy(
		mediaReadinessContext("publish-image"),
		mediaapp.UpdateMediaAssetAccessPolicyCommand{
			AssetID: imageID, OwnerID: ownerID,
			AccessPolicy: mediamodel.AccessPolicyPublic,
		},
	)
	if err != nil || updated.AccessPolicy != mediamodel.AccessPolicyPublic {
		t.Fatalf("update image access policy: result=%+v err=%v", updated, err)
	}

	owned, err := service.GetMediaAsset(
		context.Background(),
		mediaapp.GetMediaAssetQuery{AssetID: imageID, OwnerID: ownerID},
	)
	if err != nil || owned.AssetID != imageID || owned.DeliveryURL == "" {
		t.Fatalf("get owner MediaAsset: slice=%+v err=%v", owned, err)
	}
	reference, err := service.GetOwnedReadyMediaAssetReference(
		context.Background(),
		mediaapp.GetMediaAssetQuery{AssetID: imageID, OwnerID: ownerID},
	)
	if err != nil || reference.AssetID != imageID || reference.OwnerPersonaID != ownerID {
		t.Fatalf("get MediaAsset reference: slice=%+v err=%v", reference, err)
	}
	fileID := seedReadinessMediaAsset(
		t,
		store,
		now,
		"media-readiness-file",
		ownerID,
		mediamodel.MediaTypeFile,
		"application/pdf",
		mediamodel.AccessPolicyPublic,
		false,
	)
	delivery, err := service.GetOwnedReadyMediaAssetDeliveryReference(
		context.Background(),
		mediaapp.GetMediaAssetQuery{AssetID: fileID, OwnerID: ownerID},
	)
	if err != nil || delivery.AssetID != fileID || delivery.DeliveryURL == "" || delivery.PublicSliceKey == "" {
		t.Fatalf("get MediaAsset delivery reference: slice=%+v err=%v", delivery, err)
	}
	public, err := service.GetPublicMediaAsset(
		context.Background(),
		mediaapp.GetPublicMediaAssetQuery{AssetID: imageID},
	)
	if err != nil || public.AssetID != imageID || public.AccessPolicy != mediamodel.AccessPolicyPublic {
		t.Fatalf("get public MediaAsset: slice=%+v err=%v", public, err)
	}
	discarded, err := service.DiscardMediaAsset(
		mediaReadinessContext("discard-image"),
		mediaapp.DiscardMediaAssetCommand{AssetID: imageID, OwnerID: ownerID},
	)
	if err != nil || discarded.MediaID != imageID || discarded.Status != mediaapp.MediaAssetDiscardStatusDeleted {
		t.Fatalf("discard MediaAsset: result=%+v err=%v", discarded, err)
	}

	videoID := seedReadinessMediaAsset(
		t,
		store,
		now,
		"media-readiness-video",
		ownerID,
		mediamodel.MediaTypeVideo,
		"video/mp4",
		mediamodel.AccessPolicyOwnerOnly,
		true,
	)
	videoPrefix := "media/video/s/asset/" + videoID + "/v2"
	if _, err := service.RecordMediaProcessingResult(
		mediaReadinessContext("process-video"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID: videoID, Processing: mediamodel.ProcessingStatusReady,
			Descriptor: mediamodel.MediaProcessingDescriptor{
				Video: mediamodel.VideoProcessingDescriptor{
					ProcessorProfile:   "media_canary_progressive_mp4",
					VerifiedDurationMs: 125000, VideoWidth: 1080, VideoHeight: 1920,
					VideoCodec: "h264", VideoContainer: "mp4", VideoAudioCodec: "aac",
					VideoKeyframeIntervalMs: 2000, VideoFastStart: true,
					VideoPublicSliceKey:          videoPrefix + "/source.mp4",
					CoverPublicSliceKey:          videoPrefix + "/cover.jpg",
					PreviewTrackVersion:          1,
					PreviewTrackManifestSliceKey: videoPrefix + "/preview/manifest.json",
				},
			},
		},
	); err != nil {
		t.Fatalf("record ready video descriptor: %v", err)
	}
	auto, err := service.SelectAutoMediaCover(
		mediaReadinessContext("auto-cover"),
		mediaapp.SelectAutoMediaCoverCommand{AssetID: videoID, OwnerID: ownerID},
	)
	if err != nil || auto.CoverStrategy != string(mediamodel.CoverStrategyFirstFrame) {
		t.Fatalf("select auto video cover: result=%+v err=%v", auto, err)
	}
	manual, err := service.SelectManualMediaCover(
		mediaReadinessContext("manual-cover"),
		mediaapp.SelectManualMediaCoverCommand{
			AssetID: videoID, OwnerID: ownerID, CoverFrameTimeMs: 1250,
		},
	)
	if err != nil || manual.CoverStrategy != string(mediamodel.CoverStrategyManual) ||
		manual.CoverFrameTimeMs != 1250 || !strings.Contains(manual.CoverURL, "x-video-frame-ms=1250") {
		t.Fatalf("select manual video cover: result=%+v err=%v", manual, err)
	}
}

func seedReadinessMediaAsset(
	t *testing.T,
	store *mediacontract.MediaStore,
	now time.Time,
	assetID string,
	ownerID string,
	mediaType mediamodel.MediaType,
	mimeType string,
	accessPolicy mediamodel.AccessPolicy,
	processingRequired bool,
) string {
	t.Helper()
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: assetID, OwnerID: ownerID, SourceSessionID: "session-" + assetID,
		ObjectKey: "media/objects/" + assetID, SHA256: readinessMediaDigest,
		MediaType: mediaType, MimeType: mimeType, FileSize: 256,
		AccessPolicy: accessPolicy, ProcessingRequired: processingRequired, Now: now,
	})
	if err != nil {
		t.Fatalf("create MediaAsset %s: %v", assetID, err)
	}
	if _, err := store.CommitMediaAsset(context.Background(), mediaports.MediaAssetCommit{
		Aggregate: asset, ExpectedVersion: 0,
		IdempotencyKey: "seed-" + assetID,
		CommandName:    "CompleteMediaUpload", CommandDigest: "digest-" + assetID,
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []mediaports.OutboxEvent{{
			EventID: "event-" + assetID, EventType: "content.media_asset.created",
			AggregateType: "MediaAsset", AggregateID: assetID,
			AggregateVersion: 1, Payload: []byte(`{}`), OccurredAt: now,
		}},
	}); err != nil {
		t.Fatalf("commit MediaAsset %s: %v", assetID, err)
	}
	return assetID
}

func mediaReadinessContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}

type readinessMediaGateway struct{}

func (readinessMediaGateway) PublishPublicSlice(context.Context, string, string) error {
	return nil
}

func (readinessMediaGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}

func (readinessMediaGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.UTC().Unix()), nil
}
