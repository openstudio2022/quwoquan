package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func TestMediaProcessingWorkerConsumesDurableVideoCreatedFact(t *testing.T) {
	store := persistence.NewMongoMediaStore(mongoDB.Collection("media_upload_sessions"))
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
