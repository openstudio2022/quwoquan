package media_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

func TestMediaProcessingWorkerRecordsReadyAndAdvancesCheckpoint(t *testing.T) {
	asset := processingAsset(t, "media-worker-ready", "video", true)
	descriptor := processingDescriptor(asset.ID(), asset.Version()+1)
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{
		processingEvent("evt-worker-ready", asset.ID(), "cp-ready"),
	}}
	checkpoints := &workerCheckpointStore{}
	processor := &workerProcessor{
		outcome: mediaprocessing.ProcessOutcome{Descriptor: descriptor},
	}
	recorder := &workerResultRecorder{asset: asset}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&workerPoisonEvents{},
	)

	processed, err := worker.Drain(context.Background(), 10)

	if err != nil || processed != 1 {
		t.Fatalf("drain ready event: processed=%d err=%v", processed, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf("asset status=%s, want ready", asset.ProcessingStatus())
	}
	if checkpoints.current != "cp-ready" {
		t.Fatalf("checkpoint=%q, want cp-ready", checkpoints.current)
	}
	if processor.calls != 1 || recorder.calls != 1 {
		t.Fatalf("processor calls=%d recorder calls=%d", processor.calls, recorder.calls)
	}
	if recorder.idempotencyKeys[0] != "media-processing-result:evt-worker-ready" {
		t.Fatalf("server idempotency key=%q", recorder.idempotencyKeys[0])
	}
	if recorder.commands[0].Descriptor != descriptor {
		t.Fatalf("recorded descriptor drift: %#v", recorder.commands[0].Descriptor)
	}
}

func TestMediaProcessingWorkerReplaysDiscardCleanupBeforeCheckpoint(t *testing.T) {
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{{
		EventID:       "evt-worker-discard",
		EventType:     "content.media_asset.discarded",
		AggregateType: "MediaAsset",
		AggregateID:   "asset-discard",
		Checkpoint:    "cp-discard",
		OccurredAt:    time.Now().UTC(),
	}}}
	checkpoints := &workerCheckpointStore{}
	cleanup := &workerArtifactCleanupStore{work: mediaprocessing.ArtifactCleanupWork{
		WorkID:            "work-discard",
		PublicSliceKeys:   []string{"media/image/s/asset-discard/v1/source.jpg"},
		PrivateObjectKeys: []string{"media/cas/sha256/aa/source.jpg"},
	}}
	reclaimer := &workerArtifactReclaimer{err: errors.New("temporary object outage")}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&workerProcessor{},
		&workerResultRecorder{},
		&workerPoisonEvents{},
		mediaprocessing.WithArtifactCleanup(cleanup, reclaimer),
	)

	if processed, err := worker.Drain(context.Background(), 10); err == nil || processed != 0 {
		t.Fatalf("first cleanup must retain checkpoint: processed=%d err=%v", processed, err)
	}
	if checkpoints.current != "" || cleanup.markCalls != 0 {
		t.Fatalf("failed cleanup advanced durable state: checkpoint=%q marks=%d", checkpoints.current, cleanup.markCalls)
	}

	reclaimer.err = nil
	processed, err := worker.Drain(context.Background(), 10)
	if err != nil || processed != 1 {
		t.Fatalf("replay cleanup: processed=%d err=%v", processed, err)
	}
	if checkpoints.current != "cp-discard" || cleanup.markCalls != 1 || reclaimer.calls != 2 {
		t.Fatalf(
			"cleanup replay evidence drift: checkpoint=%q marks=%d reclaims=%d",
			checkpoints.current,
			cleanup.markCalls,
			reclaimer.calls,
		)
	}
}

func TestMediaProcessingWorkerRecordsReadyImageDescriptor(t *testing.T) {
	asset := processingAsset(t, "media-worker-image-ready", "image", true)
	descriptor := imageProcessingDescriptor(asset.ID(), asset.Version()+1)
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{
		processingEvent("evt-worker-image-ready", asset.ID(), "cp-image-ready"),
	}}
	checkpoints := &workerCheckpointStore{}
	processor := &workerProcessor{
		outcome: mediaprocessing.ProcessOutcome{Descriptor: descriptor},
	}
	recorder := &workerResultRecorder{asset: asset}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&workerPoisonEvents{},
	)

	processed, err := worker.Drain(context.Background(), 10)

	if err != nil || processed != 1 {
		t.Fatalf("drain ready image event: processed=%d err=%v", processed, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf("image asset status=%s, want ready", asset.ProcessingStatus())
	}
	if asset.ImageProcessingDescriptor() != descriptor.Image {
		t.Fatalf(
			"image descriptor drift: got=%#v want=%#v",
			asset.ImageProcessingDescriptor(),
			descriptor.Image,
		)
	}
	if checkpoints.current != "cp-image-ready" ||
		processor.calls != 1 ||
		recorder.calls != 1 {
		t.Fatalf(
			"image processing evidence drift: checkpoint=%q processor=%d recorder=%d",
			checkpoints.current,
			processor.calls,
			recorder.calls,
		)
	}
}

func TestMediaProcessingWorkerRecordsContentRejectionAndAdvancesCheckpoint(t *testing.T) {
	asset := processingAsset(t, "media-worker-rejected", "video", true)
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{
		processingEvent("evt-worker-rejected", asset.ID(), "cp-rejected"),
	}}
	checkpoints := &workerCheckpointStore{}
	processor := &workerProcessor{err: &mediaprocessing.RejectionError{
		Reason: "uploaded media has no decodable video stream",
	}}
	recorder := &workerResultRecorder{asset: asset}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&workerPoisonEvents{},
	)

	processed, err := worker.Drain(context.Background(), 10)

	if err != nil || processed != 1 {
		t.Fatalf("drain rejected event: processed=%d err=%v", processed, err)
	}
	if asset.ProcessingStatus() != mediamodel.ProcessingStatusRejected {
		t.Fatalf("asset status=%s, want rejected", asset.ProcessingStatus())
	}
	if checkpoints.current != "cp-rejected" {
		t.Fatalf("checkpoint=%q, want cp-rejected", checkpoints.current)
	}
	if recorder.commands[0].FailureReason == "" ||
		recorder.commands[0].Descriptor != (mediamodel.MediaProcessingDescriptor{}) {
		t.Fatalf("rejection command drift: %#v", recorder.commands[0])
	}
}

func TestMediaProcessingWorkerReplaysAfterCheckpointFailureWithoutRepeatingTerminalWork(t *testing.T) {
	asset := processingAsset(t, "media-worker-replay", "video", true)
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{
		processingEvent("evt-worker-replay", asset.ID(), "cp-replay"),
	}}
	checkpoints := &workerCheckpointStore{saveFailures: 1}
	processor := &workerProcessor{outcome: mediaprocessing.ProcessOutcome{
		Descriptor: processingDescriptor(asset.ID(), asset.Version()+1),
	}}
	recorder := &workerResultRecorder{asset: asset}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&workerPoisonEvents{},
	)

	if processed, err := worker.Drain(context.Background(), 10); err == nil || processed != 0 {
		t.Fatalf("checkpoint failure must leave event replayable: processed=%d err=%v", processed, err)
	}
	if checkpoints.current != "" {
		t.Fatalf("failed save advanced checkpoint to %q", checkpoints.current)
	}
	if processed, err := worker.Drain(context.Background(), 10); err != nil || processed != 1 {
		t.Fatalf("replay terminal event: processed=%d err=%v", processed, err)
	}
	if processor.calls != 1 || recorder.calls != 1 {
		t.Fatalf(
			"terminal replay repeated work: processor calls=%d recorder calls=%d",
			processor.calls,
			recorder.calls,
		)
	}
	if checkpoints.current != "cp-replay" {
		t.Fatalf("replay checkpoint=%q, want cp-replay", checkpoints.current)
	}
}

func TestMediaProcessingWorkerDoesNotAdvanceOnInfrastructureFailure(t *testing.T) {
	asset := processingAsset(t, "media-worker-infra", "video", true)
	checkpoints := &workerCheckpointStore{}
	recorder := &workerResultRecorder{asset: asset}
	worker := mediaprocessing.NewWorker(
		&workerOutboxSource{events: []mediaports.OutboxEvent{
			processingEvent("evt-worker-infra", asset.ID(), "cp-infra"),
		}},
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		&workerProcessor{err: errors.New("object storage unavailable")},
		recorder,
		&workerPoisonEvents{},
	)

	if processed, err := worker.Drain(context.Background(), 10); err == nil || processed != 0 {
		t.Fatalf("infrastructure failure must stop drain: processed=%d err=%v", processed, err)
	}
	if checkpoints.current != "" || recorder.calls != 0 {
		t.Fatalf(
			"infrastructure failure advanced state: checkpoint=%q recorder calls=%d",
			checkpoints.current,
			recorder.calls,
		)
	}
}

func TestMediaProcessingWorkerSkipsUploadSessionAndUnrelatedFacts(t *testing.T) {
	source := &workerOutboxSource{events: []mediaports.OutboxEvent{
		{
			EventID:       "evt-upload-session",
			EventType:     "content.media_upload.completed",
			AggregateType: "MediaUploadSession",
			AggregateID:   "upload-session-1",
			Checkpoint:    "cp-session",
			OccurredAt:    time.Now().UTC(),
		},
		{
			EventID:       "evt-unrelated",
			EventType:     "content.media_asset.processing_updated",
			AggregateType: "MediaAsset",
			AggregateID:   "media-worker-unrelated",
			Checkpoint:    "cp-unrelated",
			OccurredAt:    time.Now().UTC(),
		},
	}}
	checkpoints := &workerCheckpointStore{}
	processor := &workerProcessor{}
	recorder := &workerResultRecorder{}
	worker := mediaprocessing.NewWorker(
		source,
		&workerAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		processor,
		recorder,
		&workerPoisonEvents{},
	)

	processed, err := worker.Drain(context.Background(), 10)

	if err != nil || processed != 2 {
		t.Fatalf("drain skipped facts: processed=%d err=%v", processed, err)
	}
	if processor.calls != 0 || recorder.calls != 0 {
		t.Fatalf("skipped facts invoked processor=%d recorder=%d", processor.calls, recorder.calls)
	}
	if checkpoints.current != "cp-unrelated" {
		t.Fatalf("skipped facts did not advance checkpoint: %q", checkpoints.current)
	}
}

type workerOutboxSource struct {
	events []mediaports.OutboxEvent
	err    error
}

func (s *workerOutboxSource) ReadMediaOutboxAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	if s.err != nil {
		return nil, s.err
	}
	start := 0
	if checkpoint != "" {
		start = len(s.events)
		for index, event := range s.events {
			if event.Checkpoint == checkpoint {
				start = index + 1
				break
			}
		}
	}
	if limit <= 0 || start+limit > len(s.events) {
		limit = len(s.events) - start
	}
	return append([]mediaports.OutboxEvent(nil), s.events[start:start+limit]...), nil
}

type workerAssetLoader struct {
	assets map[string]*mediamodel.MediaAsset
	err    error
}

func (l *workerAssetLoader) LoadMediaAsset(
	_ context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	if l.err != nil {
		return nil, false, l.err
	}
	asset, found := l.assets[assetID]
	return asset, found, nil
}

type workerCheckpointStore struct {
	current      string
	loadErr      error
	saveFailures int
	leaseOwner   string
	leaseUntil   time.Time
}

type workerPoisonEvents struct {
	recorded []mediaprocessing.PoisonEvent
	err      error
}

func (s *workerPoisonEvents) QuarantineMediaProcessingEvent(
	_ context.Context,
	event mediaprocessing.PoisonEvent,
) error {
	if s.err != nil {
		return s.err
	}
	s.recorded = append(s.recorded, event)
	return nil
}

func (s *workerCheckpointStore) LoadCheckpoint(
	_ context.Context,
	_ string,
) (string, error) {
	return s.current, s.loadErr
}

func (s *workerCheckpointStore) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	if s.saveFailures > 0 {
		s.saveFailures--
		return errors.New("checkpoint store unavailable")
	}
	s.current = checkpoint
	return nil
}

func (s *workerCheckpointStore) TryAcquireMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	if s.leaseOwner != "" && s.leaseOwner != owner && s.leaseUntil.After(now) {
		return false, nil
	}
	s.leaseOwner = owner
	s.leaseUntil = now.Add(ttl)
	return true, nil
}

func (s *workerCheckpointStore) RenewMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	if s.leaseOwner != owner || !s.leaseUntil.After(now) {
		return false, nil
	}
	s.leaseUntil = now.Add(ttl)
	return true, nil
}

func (s *workerCheckpointStore) SaveMediaProcessingCheckpointWithLease(
	ctx context.Context,
	_ string,
	owner string,
	checkpoint string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	if s.leaseOwner != owner || !s.leaseUntil.After(now) {
		return false, nil
	}
	s.leaseUntil = now.Add(ttl)
	if err := s.SaveCheckpoint(ctx, "", checkpoint); err != nil {
		return false, err
	}
	return true, nil
}

type workerProcessor struct {
	outcome mediaprocessing.ProcessOutcome
	err     error
	calls   int
}

func (p *workerProcessor) Process(
	_ context.Context,
	_ mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	p.calls++
	return p.outcome, p.err
}

type workerResultRecorder struct {
	asset           *mediamodel.MediaAsset
	err             error
	calls           int
	idempotencyKeys []string
	commands        []mediaapp.RecordMediaProcessingResultCommand
}

func (r *workerResultRecorder) RecordMediaProcessingResult(
	ctx context.Context,
	command mediaapp.RecordMediaProcessingResultCommand,
) (mediaapp.MediaAssetCommandResult, error) {
	r.calls++
	r.idempotencyKeys = append(r.idempotencyKeys, commandmeta.IdempotencyKey(ctx))
	r.commands = append(r.commands, command)
	if r.err != nil {
		return mediaapp.MediaAssetCommandResult{}, r.err
	}
	if r.asset == nil {
		return mediaapp.MediaAssetCommandResult{}, errors.New("test recorder asset is missing")
	}
	if err := r.asset.RecordProcessingResult(
		command.Processing,
		command.FailureReason,
		command.Descriptor,
		time.Now().UTC().Add(time.Second),
	); err != nil {
		return mediaapp.MediaAssetCommandResult{}, err
	}
	return mediaapp.MediaAssetCommandResult{}, nil
}

type workerArtifactCleanupStore struct {
	work      mediaprocessing.ArtifactCleanupWork
	done      bool
	err       error
	markCalls int
}

func (store *workerArtifactCleanupStore) PrepareMediaAssetArtifactCleanup(
	_ context.Context,
	_ string,
	_ string,
) (mediaprocessing.ArtifactCleanupWork, bool, error) {
	return store.work, store.done, store.err
}

func (store *workerArtifactCleanupStore) MarkMediaAssetArtifactsDeleted(
	_ context.Context,
	_ string,
	_ string,
) error {
	store.markCalls++
	return store.err
}

type workerArtifactReclaimer struct {
	err   error
	calls int
}

func (reclaimer *workerArtifactReclaimer) ReclaimMediaArtifacts(
	_ context.Context,
	_ []string,
	_ []string,
	_ []string,
	_ []string,
) error {
	reclaimer.calls++
	return reclaimer.err
}

func processingEvent(eventID string, assetID string, checkpoint string) mediaports.OutboxEvent {
	return mediaports.OutboxEvent{
		EventID:       eventID,
		EventType:     "content.media_asset.created",
		AggregateType: "MediaAsset",
		AggregateID:   assetID,
		Checkpoint:    checkpoint,
		OccurredAt:    time.Now().UTC(),
	}
}

func processingAsset(
	t *testing.T,
	assetID string,
	mediaType mediamodel.MediaType,
	processingRequired bool,
) *mediamodel.MediaAsset {
	t.Helper()
	contentType := "image/jpeg"
	if mediaType == "video" {
		contentType = "video/mp4"
	}
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID:                 assetID,
		OwnerID:            "persona-media-worker",
		SourceSessionID:    "session-" + assetID,
		ObjectKey:          "media/cas/" + assetID,
		SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType:          mediaType,
		MimeType:           contentType,
		FileSize:           1024,
		AccessPolicy:       mediamodel.AccessPolicyOwnerOnly,
		ProcessingRequired: processingRequired,
		Now:                time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("create %s asset: %v", mediaType, err)
	}
	return asset
}

func processingDescriptor(assetID string, version int64) mediamodel.MediaProcessingDescriptor {
	prefix := fmt.Sprintf("media/video/s/asset/%s/v%d", assetID, version)
	return mediamodel.MediaProcessingDescriptor{
		Video: mediamodel.VideoProcessingDescriptor{
			ProcessorProfile:             "content_processing_progressive_mp4",
			VerifiedDurationMs:           20_000,
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
	}
}

func imageProcessingDescriptor(
	assetID string,
	version int64,
) mediamodel.MediaProcessingDescriptor {
	publicPrefix := fmt.Sprintf("media/image/s/asset/%s/v%d", assetID, version)
	return mediamodel.MediaProcessingDescriptor{
		Image: mediamodel.ImageProcessingDescriptor{
			ProcessorProfile:      "content_processing_image_baseline",
			ImageWidth:            1080,
			ImageHeight:           1440,
			ImageDeliveryMimeType: "image/jpeg",
			ImageNormalizedObjectKey: fmt.Sprintf(
				"media/processed/image/%s/v%d/source.jpg",
				assetID,
				version,
			),
			ImagePublicSliceKey:     publicPrefix + "/source.jpg",
			ImageDominantColor:      "#1A2B3C",
			ImageLQIP:               "data:image/jpeg;base64,/9j/2Q==",
			ImageContentProfile:     "photographic",
			DerivativePolicyVersion: 1,
		},
	}
}
