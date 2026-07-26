package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestMediaProcessingWorkerConsumesDurableVideoCreatedFact(t *testing.T) {
	store := persistence.NewMongoMediaStore(mongoDB)
	consumer := fmt.Sprintf("media-processing-api-%d", time.Now().UnixNano())
	t.Cleanup(func() {
		_, _ = mongoDB.Collection("media_projection_checkpoints").DeleteOne(
			context.Background(),
			bson.M{"_id": consumer},
		)
	})

	baseline := latestMediaOutboxCheckpoint(t, store)
	if baseline != "" {
		if err := store.SaveCheckpoint(context.Background(), consumer, baseline); err != nil {
			t.Fatalf("seed media processing checkpoint: %v", err)
		}
	}

	digest := sha256.Sum256([]byte(consumer))
	assetID := completeMediaForHTTPPacket(
		t,
		"media-processing-api-owner",
		"video",
		"video/mp4",
		hex.EncodeToString(digest[:]),
		"owner_only",
	)
	pending, err := store.ReadMediaOutboxAfter(context.Background(), baseline, 100)
	if err != nil {
		t.Fatalf("read newly committed media facts: %v", err)
	}
	var createdEventID string
	for _, event := range pending {
		if event.EventType == "content.media_asset.created" && event.AggregateID == assetID {
			createdEventID = event.EventID
			break
		}
	}
	if createdEventID == "" {
		t.Fatalf("video completion did not commit MediaAssetCreated: %#v", pending)
	}

	processor := &apiIntegrationVideoProcessor{}
	mediaService := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		newAPIIntegrationMediaObjectGateway(),
	)
	worker := mediaprocessing.NewWorker(
		store,
		store,
		store,
		processor,
		mediaService,
		store,
		mediaprocessing.WithConsumer(consumer),
	)

	processed, err := worker.Drain(context.Background(), 100)
	if err != nil {
		t.Fatalf("drain durable media outbox: %v", err)
	}
	if processed != len(pending) {
		t.Fatalf("drained=%d, pending snapshot=%d", processed, len(pending))
	}
	asset, found, err := store.LoadMediaAsset(context.Background(), assetID)
	if err != nil || !found {
		t.Fatalf("reload processed asset: found=%v err=%v", found, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady || processor.calls != 1 {
		t.Fatalf(
			"worker did not converge video: status=%s processor calls=%d",
			asset.ProcessingStatus(),
			processor.calls,
		)
	}
	receiptKey := "media-processing-result:" + createdEventID
	if count, err := mongoDB.Collection("media_asset_command_receipts").CountDocuments(
		context.Background(),
		bson.M{"_id": receiptKey, "commandName": "RecordMediaProcessingResult"},
	); err != nil || count != 1 {
		t.Fatalf(
			"deterministic server receipt missing: key=%q count=%d err=%v",
			receiptKey,
			count,
			err,
		)
	}

	// 处理结果命令会发出 MediaAssetProcessingUpdated；它不是触发事实，后续扫描
	// 只确认 checkpoint，不应再次调用 FFmpeg。
	if _, err := worker.Drain(context.Background(), 100); err != nil {
		t.Fatalf("drain processing-updated fact: %v", err)
	}
	if processor.calls != 1 {
		t.Fatalf("non-created media fact repeated processing: calls=%d", processor.calls)
	}
}

func TestDiscardedMediaCleanupDeletesSharedCASOnlyAfterLastLiveAsset(t *testing.T) {
	store := persistence.NewMongoMediaStore(mongoDB)
	mediaService := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		newAPIIntegrationMediaObjectGateway(),
	)
	digest := sha256.Sum256([]byte(fmt.Sprintf("shared-cas-%d", time.Now().UnixNano())))
	digestHex := hex.EncodeToString(digest[:])
	firstID := completeSharedCASMediaForCleanup(
		t,
		"media-cleanup-owner-one",
		"media-cleanup-one",
		digestHex,
	)
	secondID := completeSharedCASMediaForCleanup(
		t,
		"media-cleanup-owner-two",
		"media-cleanup-two",
		digestHex,
	)
	firstAsset, found, err := store.LoadMediaAsset(context.Background(), firstID)
	if err != nil || !found {
		t.Fatalf("load first shared-CAS asset: found=%v err=%v", found, err)
	}
	secondAsset, found, err := store.LoadMediaAsset(context.Background(), secondID)
	if err != nil || !found {
		t.Fatalf("load second shared-CAS asset: found=%v err=%v", found, err)
	}
	if firstAsset.ObjectKey() != secondAsset.ObjectKey() {
		t.Fatalf(
			"fixture does not share CAS: first=%q second=%q",
			firstAsset.ObjectKey(),
			secondAsset.ObjectKey(),
		)
	}

	if _, err := mediaService.DiscardMediaAsset(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"media-cleanup-discard-one",
		),
		mediaapp.DiscardMediaAssetCommand{
			AssetID: firstID,
			OwnerID: "media-cleanup-owner-one",
		},
	); err != nil {
		t.Fatalf("discard first shared-CAS asset: %v", err)
	}
	firstWork, done, err := store.PrepareMediaAssetArtifactCleanup(
		context.Background(),
		firstID,
		"event-cleanup-one",
	)
	if err != nil || done {
		t.Fatalf("prepare first cleanup: done=%v err=%v", done, err)
	}
	if containsString(firstWork.PrivateObjectKeys, firstAsset.ObjectKey()) {
		t.Fatalf(
			"first discard claimed source still referenced by second asset: %#v",
			firstWork.PrivateObjectKeys,
		)
	}

	if _, err := mediaService.DiscardMediaAsset(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"media-cleanup-discard-two",
		),
		mediaapp.DiscardMediaAssetCommand{
			AssetID: secondID,
			OwnerID: "media-cleanup-owner-two",
		},
	); err != nil {
		t.Fatalf("discard second shared-CAS asset: %v", err)
	}
	secondWork, done, err := store.PrepareMediaAssetArtifactCleanup(
		context.Background(),
		secondID,
		"event-cleanup-two",
	)
	if err != nil || done {
		t.Fatalf("prepare second cleanup: done=%v err=%v", done, err)
	}
	if !containsString(secondWork.PrivateObjectKeys, secondAsset.ObjectKey()) {
		t.Fatalf(
			"last live discard did not claim shared source: %#v",
			secondWork.PrivateObjectKeys,
		)
	}
	if err := store.MarkMediaAssetArtifactsDeleted(
		context.Background(),
		secondID,
		secondWork.WorkID,
	); err != nil {
		t.Fatalf("complete second cleanup: %v", err)
	}
	if _, done, err := store.PrepareMediaAssetArtifactCleanup(
		context.Background(),
		secondID,
		"event-cleanup-two",
	); err != nil || !done {
		t.Fatalf("cleanup completion did not replay: done=%v err=%v", done, err)
	}
}

func TestMediaProcessingPoisonEventIsDurableAndIdempotent(t *testing.T) {
	store := persistence.NewMongoMediaStore(mongoDB)
	consumer := fmt.Sprintf("media-processing-poison-%d", time.Now().UnixNano())
	eventID := fmt.Sprintf("evt-poison-%d", time.Now().UnixNano())
	collection := mongoDB.Collection("media_processing_dead_letters")
	documentID := consumer + ":" + eventID
	t.Cleanup(func() {
		_, _ = collection.DeleteOne(context.Background(), bson.M{"_id": documentID})
	})
	now := time.Now().UTC()
	event := mediaprocessing.PoisonEvent{
		Consumer:      consumer,
		EventID:       eventID,
		EventType:     "content.media_asset.created",
		AggregateType: "MediaAsset",
		AggregateID:   "asset-corrupt",
		Checkpoint:    now.Format(time.RFC3339Nano) + "|" + eventID,
		OccurredAt:    now,
		Reason:        "invalid_asset_snapshot",
		QuarantinedAt: now,
	}

	if err := store.QuarantineMediaProcessingEvent(context.Background(), event); err != nil {
		t.Fatalf("persist poison event: %v", err)
	}
	if err := store.QuarantineMediaProcessingEvent(context.Background(), event); err != nil {
		t.Fatalf("replay poison event must be idempotent: %v", err)
	}
	count, err := collection.CountDocuments(
		context.Background(),
		bson.M{
			"_id":        documentID,
			"checkpoint": event.Checkpoint,
			"reason":     event.Reason,
		},
	)
	if err != nil || count != 1 {
		t.Fatalf("durable poison event count=%d err=%v", count, err)
	}
}

func completeSharedCASMediaForCleanup(
	t *testing.T,
	owner string,
	keyPrefix string,
	digest string,
) string {
	t.Helper()
	initialized := performMediaCommand(
		t,
		"POST",
		"/content/media/uploads:init",
		`{"mediaType":"image","contentType":"image/jpeg","fileSize":128,"expectedSha256":"sha256:`+digest+`"}`,
		owner,
		keyPrefix+"-init",
	)
	sessionID := asTestString(initialized["sessionId"])
	completed := performMediaCommand(
		t,
		"POST",
		"/content/media/uploads/"+sessionID+":complete",
		`{"accessPolicy":"owner_only"}`,
		owner,
		keyPrefix+"-complete",
	)
	assetID := asTestString(completed["assetId"])
	if assetID == "" {
		t.Fatalf("shared-CAS completion has no asset: %#v", completed)
	}
	return assetID
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func latestMediaOutboxCheckpoint(
	t *testing.T,
	store *persistence.MongoMediaStore,
) string {
	t.Helper()
	checkpoint := ""
	for {
		events, err := store.ReadMediaOutboxAfter(context.Background(), checkpoint, 1000)
		if err != nil {
			t.Fatalf("scan existing media outbox: %v", err)
		}
		if len(events) == 0 {
			return checkpoint
		}
		checkpoint = events[len(events)-1].Checkpoint
	}
}

type apiIntegrationVideoProcessor struct {
	calls int
}

func (p *apiIntegrationVideoProcessor) Process(
	_ context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	p.calls++
	prefix := fmt.Sprintf(
		"media/video/s/asset/%s/v%d",
		request.AssetID,
		request.AssetVersion,
	)
	return mediaprocessing.ProcessOutcome{
		Descriptor: mediamodel.MediaProcessingDescriptor{
			Video: mediamodel.VideoProcessingDescriptor{
				ProcessorProfile:             "content_processing_progressive_mp4_v1",
				VerifiedDurationMs:           30_000,
				VideoWidth:                   720,
				VideoHeight:                  1280,
				VideoCodec:                   "h264",
				VideoContainer:               "mp4",
				VideoAudioCodec:              "aac",
				VideoKeyframeIntervalMs:      2_000,
				VideoFastStart:               true,
				VideoPublicSliceKey:          prefix + "/source.mp4",
				CoverPublicSliceKey:          prefix + "/cover.jpg",
				PreviewTrackVersion:          1,
				PreviewTrackManifestSliceKey: prefix + "/preview/manifest.json",
			},
		},
	}, nil
}
