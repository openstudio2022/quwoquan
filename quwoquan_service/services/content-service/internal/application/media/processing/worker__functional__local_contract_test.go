package mediaprocessing

import (
	"context"
	"errors"
	"testing"
	"time"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
)

type fakeOutboxSource struct {
	events []mediaports.OutboxEvent
}

func (f *fakeOutboxSource) ReadMediaOutboxAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	remaining := make([]mediaports.OutboxEvent, 0, limit)
	for _, event := range f.events {
		if checkpoint != "" && event.Checkpoint <= checkpoint {
			continue
		}
		remaining = append(remaining, event)
		if len(remaining) >= limit {
			break
		}
	}
	return remaining, nil
}

type fakeAssetLoader struct {
	assets map[string]*mediamodel.MediaAsset
}

func (f *fakeAssetLoader) LoadMediaAsset(
	_ context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	asset, found := f.assets[assetID]
	return asset, found, nil
}

type fakeCheckpoints struct {
	saved []string
}

func (f *fakeCheckpoints) LoadCheckpoint(context.Context, string) (string, error) {
	if len(f.saved) == 0 {
		return "", nil
	}
	return f.saved[len(f.saved)-1], nil
}

func (f *fakeCheckpoints) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	f.saved = append(f.saved, checkpoint)
	return nil
}

type fakeProcessor struct {
	requests []ProcessRequest
	outcome  ProcessOutcome
	err      error
}

func (f *fakeProcessor) Process(_ context.Context, request ProcessRequest) (ProcessOutcome, error) {
	f.requests = append(f.requests, request)
	if f.err != nil {
		return ProcessOutcome{}, f.err
	}
	return f.outcome, nil
}

type recordedResult struct {
	command mediaapp.RecordMediaProcessingResultCommand
}

type fakeRecorder struct {
	recorded []recordedResult
	err      error
}

func (f *fakeRecorder) RecordMediaProcessingResult(
	_ context.Context,
	command mediaapp.RecordMediaProcessingResultCommand,
) (mediaapp.MediaAssetCommandResult, error) {
	if f.err != nil {
		return mediaapp.MediaAssetCommandResult{}, f.err
	}
	f.recorded = append(f.recorded, recordedResult{command: command})
	return mediaapp.MediaAssetCommandResult{AssetID: command.AssetID}, nil
}

func newProcessingVideoAsset(t *testing.T, assetID string) *mediamodel.MediaAsset {
	t.Helper()
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID:                 assetID,
		OwnerID:            "owner-1",
		SourceSessionID:    "session-" + assetID,
		ObjectKey:          "media/objects/sha256/ab/cd/" + assetID + ".mp4",
		SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType:          "video",
		ContentType:        "video/mp4",
		FileSize:           1024,
		AccessPolicy:       mediamodel.AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                time.Now(),
	})
	if err != nil {
		t.Fatalf("create processing video asset: %v", err)
	}
	return asset
}

func assetCreatedEvent(assetID string, checkpoint string) mediaports.OutboxEvent {
	return mediaports.OutboxEvent{
		EventID:       "event-" + assetID,
		EventType:     "content.media_asset.created",
		AggregateType: "MediaAsset",
		AggregateID:   assetID,
		OccurredAt:    time.Now(),
		Checkpoint:    checkpoint,
	}
}

func validDescriptor(assetID string) mediamodel.MediaProcessingDescriptor {
	prefix := "media/video/s/asset/" + assetID + "/v2"
	return mediamodel.MediaProcessingDescriptor{
		Video: mediamodel.VideoProcessingDescriptor{
			ProcessorProfile:             "content_processing_progressive_mp4_v1",
			VerifiedDurationMs:           12_000,
			VideoWidth:                   540,
			VideoHeight:                  960,
			VideoCodec:                   "h264",
			VideoContainer:               "mp4",
			VideoAudioCodec:              "aac",
			VideoKeyframeIntervalMs:      2000,
			VideoFastStart:               true,
			VideoPublicSliceKey:          prefix + "/source.mp4",
			CoverPublicSliceKey:          prefix + "/cover.jpg",
			PreviewTrackVersion:          1,
			PreviewTrackManifestSliceKey: prefix + "/preview/manifest.json",
		},
	}
}

func TestWorkerRecordsReadyResultAndAdvancesCheckpoint(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-ready")
	processor := &fakeProcessor{
		outcome: ProcessOutcome{Descriptor: validDescriptor("asset-ready")},
	}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewWorker(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-ready", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-ready": asset}},
		checkpoints,
		processor,
		recorder,
	)

	handled, err := worker.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("drain: %v", err)
	}
	if handled != 1 {
		t.Fatalf("expected 1 handled event, got %d", handled)
	}
	if len(processor.requests) != 1 {
		t.Fatalf("expected exactly one process request, got %d", len(processor.requests))
	}
	request := processor.requests[0]
	if request.AssetID != "asset-ready" ||
		request.AssetVersion != asset.Version()+1 ||
		request.SourceObjectKey != asset.ObjectKey() {
		t.Fatalf("process request lost asset binding: %+v", request)
	}
	if len(recorder.recorded) != 1 {
		t.Fatalf("expected one recorded result, got %d", len(recorder.recorded))
	}
	command := recorder.recorded[0].command
	if command.Processing != mediamodel.ProcessingStatusReady ||
		command.Descriptor != validDescriptor("asset-ready") ||
		command.FailureReason != "" {
		t.Fatalf("ready result command is wrong: %+v", command)
	}
	if len(checkpoints.saved) != 1 || checkpoints.saved[0] != "cp-1" {
		t.Fatalf("checkpoint was not advanced exactly once: %v", checkpoints.saved)
	}
}

func TestWorkerRecordsRejectionForContentFailure(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-broken")
	processor := &fakeProcessor{
		err: &RejectionError{Reason: "uploaded media has no decodable video stream"},
	}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewWorker(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-broken", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-broken": asset}},
		checkpoints,
		processor,
		recorder,
	)

	if _, err := worker.Drain(context.Background(), 10); err != nil {
		t.Fatalf("drain: %v", err)
	}
	if len(recorder.recorded) != 1 {
		t.Fatalf("expected one recorded result, got %d", len(recorder.recorded))
	}
	command := recorder.recorded[0].command
	if command.Processing != mediamodel.ProcessingStatusRejected ||
		command.FailureReason == "" ||
		command.Descriptor != (mediamodel.MediaProcessingDescriptor{}) {
		t.Fatalf("rejected result command is wrong: %+v", command)
	}
	if len(checkpoints.saved) != 1 {
		t.Fatalf("rejected content must still advance the checkpoint: %v", checkpoints.saved)
	}
}

func TestWorkerRetriesInfrastructureFailureWithoutCheckpoint(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-infra")
	processor := &fakeProcessor{err: errors.New("object storage unavailable")}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewWorker(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-infra", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-infra": asset}},
		checkpoints,
		processor,
		recorder,
	)

	if _, err := worker.Drain(context.Background(), 10); err == nil {
		t.Fatal("infrastructure failure must surface as a drain error")
	}
	if len(recorder.recorded) != 0 {
		t.Fatalf("infrastructure failure must not record a result: %+v", recorder.recorded)
	}
	if len(checkpoints.saved) != 0 {
		t.Fatalf("infrastructure failure must not advance the checkpoint: %v", checkpoints.saved)
	}

	// 故障恢复后重放同一事件必须成功并推进 checkpoint。
	processor.err = nil
	processor.outcome = ProcessOutcome{Descriptor: validDescriptor("asset-infra")}
	if _, err := worker.Drain(context.Background(), 10); err != nil {
		t.Fatalf("drain after recovery: %v", err)
	}
	if len(recorder.recorded) != 1 || len(checkpoints.saved) != 1 {
		t.Fatalf(
			"recovered replay must record once and checkpoint once: recorded=%d checkpoints=%v",
			len(recorder.recorded),
			checkpoints.saved,
		)
	}
}

func TestWorkerSkipsNonProcessingAndForeignEvents(t *testing.T) {
	readyAsset := newProcessingVideoAsset(t, "asset-done")
	if err := readyAsset.RecordProcessingResult(
		mediamodel.ProcessingStatusReady,
		"",
		validDescriptor("asset-done"),
		time.Now(),
	); err != nil {
		t.Fatalf("prepare ready asset: %v", err)
	}
	processor := &fakeProcessor{}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewWorker(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			// 重放：资产已 ready，必须幂等跳过。
			assetCreatedEvent("asset-done", "cp-1"),
			// 非资产创建事实：processing_updated 由本 worker 自身产生，跳过。
			{
				EventID:       "event-updated",
				EventType:     "content.media_asset.processing_updated",
				AggregateType: "MediaAsset",
				AggregateID:   "asset-done",
				OccurredAt:    time.Now(),
				Checkpoint:    "cp-2",
			},
			// 上传会话事实：不属于处理管线。
			{
				EventID:       "event-session",
				EventType:     "content.media_upload.completed",
				AggregateType: "MediaUploadSession",
				AggregateID:   "session-1",
				OccurredAt:    time.Now(),
				Checkpoint:    "cp-3",
			},
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-done": readyAsset}},
		checkpoints,
		processor,
		recorder,
	)

	handled, err := worker.Drain(context.Background(), 10)
	if err != nil {
		t.Fatalf("drain: %v", err)
	}
	if handled != 3 {
		t.Fatalf("expected 3 handled events, got %d", handled)
	}
	if len(processor.requests) != 0 || len(recorder.recorded) != 0 {
		t.Fatalf(
			"skipped events must not process or record: requests=%d recorded=%d",
			len(processor.requests),
			len(recorder.recorded),
		)
	}
	if len(checkpoints.saved) != 3 || checkpoints.saved[2] != "cp-3" {
		t.Fatalf("all skipped events must advance the checkpoint: %v", checkpoints.saved)
	}
}

func TestWorkerProcessesImageAssetsThroughTheSharedPipeline(t *testing.T) {
	imageAsset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID:                 "asset-image",
		OwnerID:            "owner-1",
		SourceSessionID:    "session-image",
		ObjectKey:          "media/objects/sha256/ab/cd/asset-image.jpg",
		SHA256:             "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		MediaType:          "image",
		ContentType:        "image/jpeg",
		FileSize:           512,
		AccessPolicy:       mediamodel.AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                time.Now(),
	})
	if err != nil {
		t.Fatalf("create image asset: %v", err)
	}
	descriptor := mediamodel.MediaProcessingDescriptor{
		Image: mediamodel.ImageProcessingDescriptor{
			ProcessorProfile:         "content_image_normalization_v1",
			ImageWidth:               1200,
			ImageHeight:              900,
			ImageDeliveryContentType: "image/jpeg",
			ImageNormalizedObjectKey: "media/processed/image/asset-image/v2/source.jpg",
			ImagePublicSliceKey:      "media/image/s/asset/asset-image/v2/source.jpg",
		},
	}
	processor := &fakeProcessor{outcome: ProcessOutcome{Descriptor: descriptor}}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewWorker(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-image", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-image": imageAsset}},
		checkpoints,
		processor,
		recorder,
	)

	if _, err := worker.Drain(context.Background(), 10); err != nil {
		t.Fatalf("drain: %v", err)
	}
	if len(processor.requests) != 1 || processor.requests[0].MediaType != "image" {
		t.Fatalf("image must enter the shared processing pipeline: %+v", processor.requests)
	}
	if len(recorder.recorded) != 1 ||
		recorder.recorded[0].command.Processing != mediamodel.ProcessingStatusReady ||
		recorder.recorded[0].command.Descriptor != descriptor {
		t.Fatalf("image ready result is wrong: %+v", recorder.recorded)
	}
	if len(checkpoints.saved) != 1 {
		t.Fatalf("image event must advance the checkpoint: %v", checkpoints.saved)
	}
}
