package media_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_original_access_fact"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
)

const digestAtomic = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

func TestDiscardMediaAssetCommitsDeletedFactAndReplaysReceipt(t *testing.T) {
	now := time.Date(2030, time.February, 2, 5, 6, 7, 0, time.UTC)
	service, store, _ := newMediaService(now)
	assetID := seedMediaAsset(
		t,
		store,
		now,
		"asset-discard",
		"persona-discard-owner",
		"image",
		"image/jpeg",
		digestAtomic,
		mediamodel.AccessPolicyOwnerOnly,
	)
	command := mediaapp.DiscardMediaAssetCommand{
		AssetID: assetID,
		OwnerID: "persona-discard-owner",
	}
	first, err := service.DiscardMediaAsset(
		mediaContext("asset-discard"),
		command,
	)
	if err != nil {
		t.Fatalf("discard media asset: %v", err)
	}
	if first.MediaID != assetID ||
		first.Status != mediamodel.ProcessingStatusDeleted ||
		first.Replayed {
		t.Fatalf("unexpected discard result: %+v", first)
	}
	events := store.OutboxEvents()
	if got := events[len(events)-1].EventType; got != "content.media_asset.discarded" {
		t.Fatalf("unexpected discard event: %q", got)
	}

	replayed, err := service.DiscardMediaAsset(
		mediaContext("asset-discard"),
		command,
	)
	if err != nil {
		t.Fatalf("replay media discard: %v", err)
	}
	if !replayed.Replayed ||
		replayed.MediaID != first.MediaID ||
		replayed.Status != first.Status {
		t.Fatalf("discard receipt did not replay: first=%+v replay=%+v", first, replayed)
	}
}

func TestMediaAssetAccessPolicyNoopPersistsReceipt(t *testing.T) {
	now := time.Date(2030, time.February, 3, 5, 6, 7, 0, time.UTC)
	service, store, _ := newMediaService(now)
	assetID := seedMediaAsset(
		t,
		store,
		now,
		"asset-policy-noop",
		"persona-policy-owner",
		"image",
		"image/jpeg",
		digestAtomic,
		mediamodel.AccessPolicyOwnerOnly,
	)
	outboxBeforeNoop := len(store.OutboxEvents())
	noopCommand := mediaapp.UpdateMediaAssetAccessPolicyCommand{
		AssetID:      assetID,
		OwnerID:      "persona-policy-owner",
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
	}
	noop, err := service.UpdateMediaAssetAccessPolicy(
		mediaContext("asset-policy-noop"),
		noopCommand,
	)
	if err != nil {
		t.Fatalf("record access-policy no-op: %v", err)
	}
	if noop.Replayed || noop.Version != 1 ||
		noop.AccessPolicy != mediamodel.AccessPolicyOwnerOnly {
		t.Fatalf("unexpected first no-op result: %+v", noop)
	}
	if got := len(store.OutboxEvents()); got != outboxBeforeNoop {
		t.Fatalf("no-op appended outbox fact: before=%d after=%d", outboxBeforeNoop, got)
	}

	changed, err := service.UpdateMediaAssetAccessPolicy(
		mediaContext("asset-policy-public"),
		mediaapp.UpdateMediaAssetAccessPolicyCommand{
			AssetID:      assetID,
			OwnerID:      "persona-policy-owner",
			AccessPolicy: mediamodel.AccessPolicyPublic,
		},
	)
	if err != nil {
		t.Fatalf("change access policy: %v", err)
	}
	if changed.Version != 2 || changed.AccessPolicy != mediamodel.AccessPolicyPublic {
		t.Fatalf("unexpected changed access policy: %+v", changed)
	}

	replayed, err := service.UpdateMediaAssetAccessPolicy(
		mediaContext("asset-policy-noop"),
		noopCommand,
	)
	if err != nil {
		t.Fatalf("replay access-policy no-op: %v", err)
	}
	if !replayed.Replayed ||
		replayed.Version != noop.Version ||
		replayed.AccessPolicy != noop.AccessPolicy {
		t.Fatalf("no-op receipt did not replay original result: first=%+v replay=%+v", noop, replayed)
	}
}

func TestManualVideoCoverClassifiesTransientAndRejectedCoverAssets(t *testing.T) {
	now := time.Date(2030, time.February, 3, 6, 7, 8, 0, time.UTC)
	service, store, _ := newMediaService(now)
	const ownerID = "persona-cover-owner"
	videoID := seedMediaAsset(
		t,
		store,
		now,
		"asset-cover-video",
		ownerID,
		"video",
		"video/mp4",
		digestAtomic,
		mediamodel.AccessPolicyOwnerOnly,
	)
	coverID := seedMediaAsset(
		t,
		store,
		now,
		"asset-cover-image",
		ownerID,
		"image",
		"image/jpeg",
		digestAtomic,
		mediamodel.AccessPolicyOwnerOnly,
	)
	command := mediaapp.SelectManualMediaCoverCommand{
		AssetID:      videoID,
		OwnerID:      ownerID,
		CoverAssetID: coverID,
	}

	_, err := service.SelectManualMediaCover(
		mediaContext("manual-cover-processing"),
		command,
	)
	if err == nil || !strings.Contains(err.Error(), mediaerrors.ErrMediaNotReady.Error()) {
		t.Fatalf("processing cover error=%v, want %s", err, mediaerrors.ErrMediaNotReady)
	}

	if _, err := service.RecordMediaProcessingResult(
		mediaContext("reject-manual-cover"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID:       coverID,
			Processing:    mediamodel.ProcessingStatusRejected,
			FailureReason: "fixture rejected",
		},
	); err != nil {
		t.Fatalf("reject cover asset: %v", err)
	}
	_, err = service.SelectManualMediaCover(
		mediaContext("manual-cover-rejected"),
		command,
	)
	if err == nil ||
		!strings.Contains(err.Error(), mediaerrors.ErrMediaProcessingRejected.Error()) {
		t.Fatalf(
			"rejected cover error=%v, want %s",
			err,
			mediaerrors.ErrMediaProcessingRejected,
		)
	}
}

func TestReadyVideoRequiresAndPersistsTrustedProcessingDescriptor(t *testing.T) {
	now := time.Date(2030, time.February, 4, 4, 5, 6, 0, time.UTC)
	service, store, _ := newMediaService(now)
	assetID := seedMediaAsset(
		t,
		store,
		now,
		"asset-video",
		"persona-owner",
		"video",
		"video/mp4",
		digestAtomic,
		mediamodel.AccessPolicyOwnerOnly,
	)
	if _, err := service.RecordMediaProcessingResult(
		mediaContext("ready-video-without-descriptor"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID: assetID, Processing: mediamodel.ProcessingStatusReady,
		},
	); err == nil {
		t.Fatal("ready video without a VOD descriptor must be rejected")
	}

	videoPrefix := fmt.Sprintf(
		"media/video/s/asset/%s/v2",
		assetID,
	)
	command := mediaapp.RecordMediaProcessingResultCommand{
		AssetID:    assetID,
		Processing: mediamodel.ProcessingStatusReady,
		Descriptor: mediamodel.MediaProcessingDescriptor{
			Video: mediamodel.VideoProcessingDescriptor{
				ProcessorProfile:             "media_canary_progressive_mp4",
				VerifiedDurationMs:           125000,
				VideoWidth:                   1080,
				VideoHeight:                  1920,
				VideoCodec:                   "h264",
				VideoContainer:               "mp4",
				VideoAudioCodec:              "aac",
				VideoKeyframeIntervalMs:      2000,
				VideoFastStart:               true,
				VideoPublicSliceKey:          videoPrefix + "/source.mp4",
				CoverPublicSliceKey:          videoPrefix + "/cover.jpg",
				PreviewTrackVersion:          1,
				PreviewTrackManifestSliceKey: videoPrefix + "/preview/manifest.json",
			},
		},
	}
	ctx := mediaContext("ready-video-with-descriptor")
	result, err := service.RecordMediaProcessingResult(ctx, command)
	if err != nil {
		t.Fatalf("record trusted processing result: %v", err)
	}
	if result.ProcessingStatus != mediamodel.ProcessingStatusReady ||
		result.VerifiedDurationMs != 125000 ||
		result.VideoWidth != 1080 ||
		result.VideoAudioCodec != "aac" ||
		!result.VideoFastStart ||
		result.PreviewTrackVersion != 1 {
		t.Fatalf("trusted descriptor was not returned: %+v", result)
	}
	replayed, err := service.RecordMediaProcessingResult(ctx, command)
	if err != nil || !replayed.Replayed || replayed.VerifiedDurationMs != 125000 {
		t.Fatalf("processing result replay must be exact: result=%+v err=%v", replayed, err)
	}
}

func TestReadyVideoRejectsOverOneHourAndUnsafeSeekDescriptors(t *testing.T) {
	now := time.Date(2030, time.February, 5, 4, 5, 6, 0, time.UTC)
	base := mediamodel.MediaAssetSnapshot{
		ID:               "asset-video-boundary",
		Version:          1,
		OwnerID:          "persona-owner",
		SourceSessionID:  "session-video-boundary",
		ObjectKey:        "uploads/video-boundary",
		SHA256:           digestAtomic,
		MediaType:        mediamodel.MediaTypeVideo,
		MimeType:         "video/mp4",
		FileSize:         2048,
		AccessPolicy:     mediamodel.AccessPolicyOwnerOnly,
		ProcessingStatus: mediamodel.ProcessingStatusProcessing,
		CoverStrategy:    mediamodel.CoverStrategyFirstFrame,
		CreatedAt:        now,
		UpdatedAt:        now,
	}
	descriptor := mediamodel.VideoProcessingDescriptor{
		ProcessorProfile:        "media_canary_progressive_mp4",
		VerifiedDurationMs:      mediamodel.MaxVideoDurationMs + 5000,
		VideoWidth:              1080,
		VideoHeight:             1920,
		VideoCodec:              "h264",
		VideoContainer:          "mp4",
		VideoAudioCodec:         "aac",
		VideoKeyframeIntervalMs: 2000,
		VideoFastStart:          true,
		VideoPublicSliceKey:     "media/video/s/asset/asset-video-boundary/v1/source.mp4",
		CoverPublicSliceKey:     "media/video/s/asset/asset-video-boundary/v1/cover.webp",
	}
	asset, err := mediamodel.RestoreMediaAsset(base)
	if err != nil {
		t.Fatalf("restore processing asset: %v", err)
	}
	if err := asset.RecordProcessingResult(
		mediamodel.ProcessingStatusReady,
		"",
		mediamodel.MediaProcessingDescriptor{Video: descriptor},
		now.Add(time.Second),
	); err == nil {
		t.Fatal("3605-second descriptor must be rejected by the one-hour product boundary")
	}

	descriptor.VerifiedDurationMs = 125000
	descriptor.VideoKeyframeIntervalMs = mediamodel.MaxVideoKeyframeIntervalMs + 1
	asset, err = mediamodel.RestoreMediaAsset(base)
	if err != nil {
		t.Fatalf("restore processing asset for keyframe check: %v", err)
	}
	if err := asset.RecordProcessingResult(
		mediamodel.ProcessingStatusReady,
		"",
		mediamodel.MediaProcessingDescriptor{Video: descriptor},
		now.Add(time.Second),
	); err == nil {
		t.Fatal("descriptor with a keyframe interval over two seconds must be rejected")
	}

	descriptor.VideoKeyframeIntervalMs = 2000
	descriptor.VideoFastStart = false
	asset, err = mediamodel.RestoreMediaAsset(base)
	if err != nil {
		t.Fatalf("restore processing asset for fast-start check: %v", err)
	}
	if err := asset.RecordProcessingResult(
		mediamodel.ProcessingStatusReady,
		"",
		mediamodel.MediaProcessingDescriptor{Video: descriptor},
		now.Add(time.Second),
	); err == nil {
		t.Fatal("non-fast-start MP4 must not become ready")
	}
}

func TestOriginalMediaAccessAppendsOneFactAndKeepsAbsoluteExpiryOnReplay(t *testing.T) {
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	service, store, _ := newMediaService(now)
	assetID := seedMediaAsset(
		t, store, now, "asset-original-access", "persona-owner",
		"image", "image/jpeg", digestAtomic, mediamodel.AccessPolicyOwnerOnly,
	)
	if _, err := service.RecordMediaProcessingResult(
		mediaContext("ready-original-access-image"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID:    assetID,
			Processing: mediamodel.ProcessingStatusReady,
			Descriptor: imageProcessingDescriptor(assetID, 2),
		},
	); err != nil {
		t.Fatalf("ready image before original access: %v", err)
	}
	command := mediaapp.RequestOriginalMediaAccessCommand{
		AssetID: assetID, ViewerID: "persona-owner", Purpose: "save",
	}
	ctx := mediaContext("grant-original-access")
	first, err := service.RequestOriginalMediaAccess(ctx, command)
	if err != nil {
		t.Fatalf("request original access: %v", err)
	}
	replayed, err := service.RequestOriginalMediaAccess(ctx, command)
	if err != nil {
		t.Fatalf("replay original access: %v", err)
	}
	if first.AuditID != replayed.AuditID || first.OriginalURL != replayed.OriginalURL || !first.ExpiresAt.Equal(replayed.ExpiresAt) {
		t.Fatalf("idempotent replay extended or changed grant: first=%+v replay=%+v", first, replayed)
	}
	if !first.ExpiresAt.Equal(now.Add(5*time.Minute)) || !strings.Contains(first.OriginalURL, fmt.Sprintf("expires=%d", first.ExpiresAt.Unix())) {
		t.Fatalf("signed URL and response must share the absolute expiry: %+v", first)
	}
	facts := store.OriginalAccessFacts()
	if len(facts) != 1 ||
		facts[0].AuditID != first.AuditID ||
		facts[0].Purpose != "save" ||
		facts[0].Outcome != "granted" ||
		facts[0].Reason != "authorized" {
		t.Fatalf("expected exactly one durable original access fact, got %+v", facts)
	}
}

func TestOriginalMediaAccessRateLimitsByViewerAssetAndPurpose(t *testing.T) {
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	service, store, _ := newMediaService(now)
	assetID := seedMediaAsset(
		t, store, now, "asset-original-access-limit", "persona-owner",
		"image", "image/jpeg", digestAtomic, mediamodel.AccessPolicyOwnerOnly,
	)
	if _, err := service.RecordMediaProcessingResult(
		mediaContext("ready-original-access-limit"),
		mediaapp.RecordMediaProcessingResultCommand{
			AssetID: assetID, Processing: mediamodel.ProcessingStatusReady,
			Descriptor: imageProcessingDescriptor(assetID, 2),
		},
	); err != nil {
		t.Fatalf("ready image: %v", err)
	}
	for attempt := 0; attempt < 6; attempt++ {
		if _, err := service.RequestOriginalMediaAccess(
			mediaContext(fmt.Sprintf("original-access-limit-%d", attempt)),
			mediaapp.RequestOriginalMediaAccessCommand{
				AssetID: assetID, ViewerID: "persona-owner", Purpose: "view",
			},
		); err != nil {
			t.Fatalf("grant %d: %v", attempt, err)
		}
	}
	_, err := service.RequestOriginalMediaAccess(
		mediaContext("original-access-limit-rejected"),
		mediaapp.RequestOriginalMediaAccessCommand{
			AssetID: assetID, ViewerID: "persona-owner", Purpose: "view",
		},
	)
	var appError *rterr.AppError
	if !errors.As(err, &appError) ||
		appError.Code.String() != contentgenerated.AppErrorFromOriginalAccessRateLimited("").Code.String() {
		t.Fatalf("expected viewer/media/purpose rate limit, got %v", err)
	}
	facts := store.OriginalAccessFacts()
	rateLimitedAudits := 0
	for _, fact := range facts {
		if fact.Outcome == "rate_limited" && fact.Reason == "rate_limit_exhausted" {
			rateLimitedAudits++
		}
	}
	if rateLimitedAudits != 1 {
		t.Fatalf("rate-limited request must append one audit fact, got %+v", facts)
	}
}

func newMediaService(
	now time.Time,
) (*mediaapp.MediaService, *mediacontract.MediaStore, *time.Time) {
	store := mediacontract.NewMediaStore()
	current := new(time.Time)
	*current = now
	identifier := 0
	service := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		mediaObjectGateway{},
		mediaapp.WithOriginalAccessPostVisibilityReader(
			alwaysVisibleMediaReader{},
		),
		mediaapp.WithClock(func() time.Time { return *current }),
		mediaapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			identifier++
			return prefix + "-" + string(rune('0'+identifier)), nil
		}),
	)
	return service, store, current
}

type alwaysVisibleMediaReader struct{}

func (alwaysVisibleMediaReader) CanViewerAccessPublishedMedia(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

type mediaObjectGateway struct{}

func (mediaObjectGateway) PublishPublicSlice(
	_ context.Context,
	_ string,
	_ string,
) error {
	return nil
}

func (mediaObjectGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}

func (mediaObjectGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.UTC().Unix()), nil
}

func seedMediaAsset(
	t *testing.T,
	store *mediacontract.MediaStore,
	now time.Time,
	assetID string,
	ownerID string,
	mediaType mediamodel.MediaType,
	mimeType string,
	digest string,
	accessPolicy mediamodel.AccessPolicy,
) string {
	t.Helper()
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: assetID, OwnerID: ownerID, SourceSessionID: "session-" + assetID,
		ObjectKey: "media/objects/" + strings.TrimPrefix(digest, "sha256:"),
		SHA256:    digest, MediaType: mediaType, MimeType: mimeType,
		FileSize: 256, AccessPolicy: accessPolicy, ProcessingRequired: true, Now: now,
	})
	if err != nil {
		t.Fatalf("build media asset %s: %v", assetID, err)
	}
	_, err = store.CommitMediaAsset(context.Background(), mediaports.MediaAssetCommit{
		Aggregate: asset, ExpectedVersion: 0, IdempotencyKey: "seed-" + assetID,
		CommandName: "CompleteMediaUpload", CommandDigest: "digest-" + assetID,
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []mediaports.OutboxEvent{{
			EventID: "event-" + assetID, EventType: "content.media_asset.created",
			AggregateType: "MediaAsset", AggregateID: assetID, AggregateVersion: 1,
			Payload: []byte(`{}`), OccurredAt: now,
		}},
	})
	if err != nil {
		t.Fatalf("seed media asset %s: %v", assetID, err)
	}
	return assetID
}

func mediaContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}
