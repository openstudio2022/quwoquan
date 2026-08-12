// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/media-status-pipeline/spec.md#gwt-001
// readiness_case: process-media-outbox-local
package application_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

func TestMediaProcessingLifecycleConsumerRecordsReadyAndAcknowledgesCheckpoint(t *testing.T) {
	createdAt := time.Date(2030, time.January, 2, 3, 4, 5, 0, time.UTC)
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: "media-lifecycle-local", OwnerID: "persona-media-local", SourceSessionID: "upload-media-local",
		ObjectKey: "media/cas/media-lifecycle-local", SHA256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType: mediamodel.MediaTypeVideo, MimeType: "video/mp4", FileSize: 1024,
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly, ProcessingRequired: true, Now: createdAt,
	})
	if err != nil {
		t.Fatalf("create processing asset: %v", err)
	}
	source := &processingOutboxSource{event: mediaports.OutboxEvent{
		EventID: "media-lifecycle-local:1", EventType: "content.media_asset.created",
		AggregateType: "MediaAsset", AggregateID: asset.ID(), AggregateVersion: asset.Version(),
		Checkpoint: "checkpoint-media-lifecycle-local", OccurredAt: createdAt,
	}}
	checkpoint := &processingCheckpoint{}
	processor := &processingProcessor{}
	recorder := &processingRecorder{asset: asset, now: createdAt.Add(time.Second)}
	handler := mediaprocessing.NewMediaProcessingHandler(
		source,
		processingAssetLoader{asset: asset},
		checkpoint,
		processor,
		recorder,
		processingPoisonRecorder{},
		mediaprocessing.WithLeaseOwner("media-lifecycle-local-runner"),
		mediaprocessing.WithClock(func() time.Time { return createdAt }),
	)

	processed, err := handler.Process(context.Background(), 1)
	if err != nil || processed != 1 {
		t.Fatalf("drain lifecycle event: processed=%d err=%v", processed, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf("processed asset status=%s, want ready", asset.ProcessingStatus())
	}
	if processor.calls != 1 || recorder.calls != 1 {
		t.Fatalf("processor calls=%d recorder calls=%d", processor.calls, recorder.calls)
	}
	if checkpoint.value != source.event.Checkpoint {
		t.Fatalf("checkpoint=%q, want %q", checkpoint.value, source.event.Checkpoint)
	}
	if recorder.idempotencyKey != "media-processing-result:"+source.event.EventID {
		t.Fatalf("result idempotency=%q", recorder.idempotencyKey)
	}
}

type processingOutboxSource struct {
	event mediaports.OutboxEvent
}

func (source *processingOutboxSource) ReadMediaOutboxAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]mediaports.OutboxEvent, error) {
	if checkpoint == source.event.Checkpoint {
		return nil, nil
	}
	return []mediaports.OutboxEvent{source.event}, nil
}

type processingAssetLoader struct {
	asset *mediamodel.MediaAsset
}

func (loader processingAssetLoader) LoadMediaAsset(
	_ context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	if loader.asset.ID() != assetID {
		return nil, false, nil
	}
	return loader.asset, true, nil
}

type processingCheckpoint struct {
	value      string
	leaseOwner string
	leaseUntil time.Time
}

func (checkpoint *processingCheckpoint) LoadCheckpoint(context.Context, string) (string, error) {
	return checkpoint.value, nil
}

func (checkpoint *processingCheckpoint) SaveCheckpoint(
	_ context.Context,
	_ string,
	value string,
) error {
	checkpoint.value = value
	return nil
}

func (checkpoint *processingCheckpoint) TryAcquireMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	checkpoint.leaseOwner = owner
	checkpoint.leaseUntil = now.Add(ttl)
	return true, nil
}

func (checkpoint *processingCheckpoint) RenewMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	if owner != checkpoint.leaseOwner || !checkpoint.leaseUntil.After(now) {
		return false, nil
	}
	checkpoint.leaseUntil = now.Add(ttl)
	return true, nil
}

func (checkpoint *processingCheckpoint) SaveMediaProcessingCheckpointWithLease(
	ctx context.Context,
	consumer string,
	owner string,
	value string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	if owner != checkpoint.leaseOwner || !checkpoint.leaseUntil.After(now) {
		return false, nil
	}
	checkpoint.leaseUntil = now.Add(ttl)
	return true, checkpoint.SaveCheckpoint(ctx, consumer, value)
}

type processingProcessor struct {
	calls int
}

func (processor *processingProcessor) Process(
	_ context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	processor.calls++
	prefix := fmt.Sprintf("media/video/s/asset/%s/v%d", request.AssetID, request.AssetVersion)
	return mediaprocessing.ProcessOutcome{Descriptor: mediamodel.MediaProcessingDescriptor{
		Video: mediamodel.VideoProcessingDescriptor{
			ProcessorProfile: "content_processing_progressive_mp4", VerifiedDurationMs: 30_000,
			VideoWidth: 720, VideoHeight: 1280, VideoCodec: "h264", VideoContainer: "mp4",
			VideoAudioCodec: "aac", VideoKeyframeIntervalMs: 2_000, VideoFastStart: true,
			VideoPublicSliceKey:          prefix + "/source.mp4",
			CoverPublicSliceKey:          prefix + "/cover.jpg",
			PreviewTrackVersion:          1,
			PreviewTrackManifestSliceKey: prefix + "/preview/manifest.json",
		},
	}}, nil
}

type processingRecorder struct {
	asset          *mediamodel.MediaAsset
	now            time.Time
	calls          int
	idempotencyKey string
}

func (recorder *processingRecorder) RecordMediaProcessingResult(
	ctx context.Context,
	command mediaapp.RecordMediaProcessingResultCommand,
) (mediaapp.MediaAssetCommandResult, error) {
	recorder.calls++
	recorder.idempotencyKey = commandmeta.IdempotencyKey(ctx)
	if err := recorder.asset.RecordProcessingResult(
		command.Processing,
		command.FailureReason,
		command.Descriptor,
		recorder.now,
	); err != nil {
		return mediaapp.MediaAssetCommandResult{}, err
	}
	return mediaapp.MediaAssetCommandResult{}, nil
}

type processingPoisonRecorder struct{}

func (processingPoisonRecorder) QuarantineMediaProcessingEvent(
	context.Context,
	mediaprocessing.PoisonEvent,
) error {
	return nil
}
