package mediaprocessing_test

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
	"sync"
	"testing"
	"time"

	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

type fakeOutboxSource struct {
	events    []mediaports.OutboxEvent
	lastLimit int
}

func (f *fakeOutboxSource) ReadMediaOutboxAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	f.lastLimit = limit
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
	err    error
}

func (f *fakeAssetLoader) LoadMediaAsset(
	_ context.Context,
	assetID string,
) (*mediamodel.MediaAsset, bool, error) {
	if f.err != nil {
		return nil, false, f.err
	}
	asset, found := f.assets[assetID]
	return asset, found, nil
}

type fakeCheckpoints struct {
	mu    sync.Mutex
	saved []string
	owner string
	until time.Time
}

func (f *fakeCheckpoints) LoadCheckpoint(context.Context, string) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.saved) == 0 {
		return "", nil
	}
	return f.saved[len(f.saved)-1], nil
}

func (f *fakeCheckpoints) SaveCheckpoint(_ context.Context, _ string, checkpoint string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.saved = append(f.saved, checkpoint)
	return nil
}

func (f *fakeCheckpoints) TryAcquireMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.owner != "" && f.owner != owner && f.until.After(now) {
		return false, nil
	}
	f.owner = owner
	f.until = now.Add(ttl)
	return true, nil
}

func (f *fakeCheckpoints) RenewMediaProcessingLease(
	_ context.Context,
	_ string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.owner != owner || !f.until.After(now) {
		return false, nil
	}
	f.until = now.Add(ttl)
	return true, nil
}

func (f *fakeCheckpoints) SaveMediaProcessingCheckpointWithLease(
	ctx context.Context,
	_ string,
	owner string,
	checkpoint string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	f.mu.Lock()
	if f.owner != owner || !f.until.After(now) {
		f.mu.Unlock()
		return false, nil
	}
	f.until = now.Add(ttl)
	f.mu.Unlock()
	return true, f.SaveCheckpoint(ctx, "", checkpoint)
}

type fakeProcessor struct {
	mu       sync.Mutex
	requests []ProcessRequest
	outcome  ProcessOutcome
	err      error
	started  chan struct{}
	release  <-chan struct{}
	start    sync.Once
}

func (f *fakeProcessor) Process(ctx context.Context, request ProcessRequest) (ProcessOutcome, error) {
	f.mu.Lock()
	f.requests = append(f.requests, request)
	f.mu.Unlock()
	if f.started != nil {
		f.start.Do(func() { close(f.started) })
	}
	if f.release != nil {
		select {
		case <-f.release:
		case <-ctx.Done():
			return ProcessOutcome{}, ctx.Err()
		}
	}
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

type fakePoisonEvents struct {
	recorded []PoisonEvent
	err      error
}

func (f *fakePoisonEvents) QuarantineMediaProcessingEvent(
	_ context.Context,
	event PoisonEvent,
) error {
	if f.err != nil {
		return f.err
	}
	f.recorded = append(f.recorded, event)
	return nil
}

type recordingObserver struct {
	batchEvents              []int
	batchLimits              []int
	jobs                     []observedJob
	outboxOldestAges         []time.Duration
	completeToReady          []observedCompleteToReady
	poisons                  []string
	poisonQuarantineFailures []string
}

type observedJob struct {
	mediaType      string
	inputSizeClass string
	result         string
	duration       time.Duration
}

type observedCompleteToReady struct {
	mediaType      string
	inputSizeClass string
	duration       time.Duration
}

func (o *recordingObserver) JobCompleted(
	mediaType string,
	inputSizeClass string,
	result string,
	duration time.Duration,
) {
	o.jobs = append(o.jobs, observedJob{
		mediaType:      mediaType,
		inputSizeClass: inputSizeClass,
		result:         result,
		duration:       duration,
	})
}

func (o *recordingObserver) BatchObserved(eventCount int, batchLimit int) {
	o.batchEvents = append(o.batchEvents, eventCount)
	o.batchLimits = append(o.batchLimits, batchLimit)
}

func (o *recordingObserver) OutboxOldestEventAge(age time.Duration) {
	o.outboxOldestAges = append(o.outboxOldestAges, age)
}

func (o *recordingObserver) CompleteToReady(
	mediaType string,
	inputSizeClass string,
	duration time.Duration,
) {
	o.completeToReady = append(o.completeToReady, observedCompleteToReady{
		mediaType:      mediaType,
		inputSizeClass: inputSizeClass,
		duration:       duration,
	})
}

func (o *recordingObserver) Poisoned(reason string, _ time.Duration) {
	o.poisons = append(o.poisons, reason)
}

func (o *recordingObserver) PoisonQuarantineFailed(reason string) {
	o.poisonQuarantineFailures = append(o.poisonQuarantineFailures, reason)
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
		MimeType:           "video/mp4",
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
			ProcessorProfile:             "content_processing_progressive_mp4",
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
	observer := &recordingObserver{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-ready", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-ready": asset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
		WithObserver(observer),
	)

	handled, err := worker.Process(context.Background(), 10)
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
	if len(observer.jobs) != 1 ||
		observer.jobs[0].mediaType != "video" ||
		observer.jobs[0].inputSizeClass != "under_1mb" ||
		observer.jobs[0].result != "ready" {
		t.Fatalf("job SLI labels drift: %#v", observer.jobs)
	}
	if len(observer.outboxOldestAges) != 1 ||
		len(observer.completeToReady) != 1 ||
		observer.completeToReady[0].mediaType != "video" ||
		observer.completeToReady[0].inputSizeClass != "under_1mb" {
		t.Fatalf(
			"completion SLI signals drift: oldest=%#v complete=%#v",
			observer.outboxOldestAges,
			observer.completeToReady,
		)
	}
}

func TestWorkerStandbyDoesNotDuplicateActiveReplicaProcessing(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-single-active-worker")
	checkpoints := &fakeCheckpoints{}
	release := make(chan struct{})
	processor := &fakeProcessor{
		outcome: ProcessOutcome{
			Descriptor: validDescriptor("asset-single-active-worker"),
		},
		started: make(chan struct{}),
		release: release,
	}
	recorder := &fakeRecorder{}
	source := &fakeOutboxSource{events: []mediaports.OutboxEvent{
		assetCreatedEvent("asset-single-active-worker", "cp-1"),
	}}
	active := NewMediaProcessingHandler(
		source,
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
		WithLeaseOwner("active-replica"),
		WithLeaseTTL(30*time.Millisecond),
	)
	standby := NewMediaProcessingHandler(
		source,
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
		WithLeaseOwner("standby-replica"),
		WithLeaseTTL(30*time.Millisecond),
	)

	activeResult := make(chan error, 1)
	go func() {
		_, err := active.Process(context.Background(), 1)
		activeResult <- err
	}()
	<-processor.started
	time.Sleep(75 * time.Millisecond)

	handled, err := standby.Process(context.Background(), 1)
	if err != nil || handled != 0 {
		t.Fatalf("standby must not process an active owner batch: handled=%d err=%v", handled, err)
	}
	close(release)
	if err := <-activeResult; err != nil {
		t.Fatalf("active replica drain: %v", err)
	}
	if len(processor.requests) != 1 || len(recorder.recorded) != 1 {
		t.Fatalf(
			"exactly one replica may process the asset: calls=%d records=%d",
			len(processor.requests),
			len(recorder.recorded),
		)
	}
	if len(checkpoints.saved) != 1 || checkpoints.saved[0] != "cp-1" {
		t.Fatalf("active replica did not advance the shared cursor: %v", checkpoints.saved)
	}
}

func TestWorkerRunStopsWithinBoundWhenTerminationCancelsActiveProcessing(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-termination")
	processor := &fakeProcessor{
		outcome: ProcessOutcome{Descriptor: validDescriptor(asset.ID())},
		started: make(chan struct{}),
		release: make(chan struct{}),
	}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent(asset.ID(), "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{asset.ID(): asset}},
		checkpoints,
		processor,
		&fakeRecorder{},
		&fakePoisonEvents{},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	stopped := make(chan error, 1)
	go func() {
		stopped <- worker.Run(ctx, time.Hour)
	}()
	<-processor.started

	cancel()
	select {
	case err := <-stopped:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("termination must return context cancellation, got %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("worker did not stop within the SIGTERM shutdown bound")
	}
	if len(checkpoints.saved) != 0 {
		t.Fatalf("cancelled processing must not advance its checkpoint: %v", checkpoints.saved)
	}
}

func TestWorkerRecordsRejectionForContentFailure(t *testing.T) {
	asset := newProcessingVideoAsset(t, "asset-broken")
	processor := &fakeProcessor{
		err: &RejectionError{Reason: "uploaded media has no decodable video stream"},
	}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-broken", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-broken": asset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
	)

	if _, err := worker.Process(context.Background(), 10); err != nil {
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
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-infra", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-infra": asset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
	)

	if _, err := worker.Process(context.Background(), 10); err == nil {
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
	if _, err := worker.Process(context.Background(), 10); err != nil {
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

func TestWorkerQuarantinesCorruptAssetEventBeforeCheckpointAdvance(t *testing.T) {
	poisons := &fakePoisonEvents{}
	checkpoints := &fakeCheckpoints{}
	observer := &recordingObserver{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("", "cp-corrupt"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
		WithObserver(observer),
	)

	handled, err := worker.Process(context.Background(), 10)
	if err != nil || handled != 1 {
		t.Fatalf("corrupt event must be isolated and consumed: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 1 {
		t.Fatalf("expected one durable poison event, got %#v", poisons.recorded)
	}
	poison := poisons.recorded[0]
	if poison.Reason != "invalid_event_metadata" ||
		poison.Checkpoint != "cp-corrupt" ||
		poison.Consumer != "content-media-processing" {
		t.Fatalf("poison event identity drift: %#v", poison)
	}
	if len(checkpoints.saved) != 1 || checkpoints.saved[0] != "cp-corrupt" {
		t.Fatalf("checkpoint must advance only after quarantine: %v", checkpoints.saved)
	}
	if len(observer.poisons) != 1 ||
		observer.poisons[0] != "invalid_event_metadata" {
		t.Fatalf("poison metric signal drift: %v", observer.poisons)
	}
}

func TestWorkerRetainsCheckpointWhenPoisonPersistenceFails(t *testing.T) {
	checkpoints := &fakeCheckpoints{}
	observer := &recordingObserver{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("", "cp-corrupt"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		&fakePoisonEvents{err: errors.New("dead-letter store unavailable")},
		WithObserver(observer),
	)

	if handled, err := worker.Process(context.Background(), 10); err == nil || handled != 0 {
		t.Fatalf("dead-letter write failure must leave event replayable: handled=%d err=%v", handled, err)
	}
	if len(checkpoints.saved) != 0 {
		t.Fatalf("checkpoint advanced despite poison persistence failure: %v", checkpoints.saved)
	}
	if len(observer.poisons) != 0 ||
		len(observer.poisonQuarantineFailures) != 1 ||
		observer.poisonQuarantineFailures[0] != "invalid_event_metadata" {
		t.Fatalf(
			"dead-letter persistence failure must emit only quarantine-failure signal: poisons=%v failures=%v",
			observer.poisons,
			observer.poisonQuarantineFailures,
		)
	}
}

func TestWorkerFailsClosedWhenSourceCursorCannotBeQuarantined(t *testing.T) {
	now := time.Now()
	testCases := []struct {
		name  string
		event mediaports.OutboxEvent
	}{
		{
			name: "missing event id",
			event: mediaports.OutboxEvent{
				EventType:     "content.media_asset.created",
				AggregateType: "MediaAsset",
				AggregateID:   "asset-1",
				Checkpoint:    "cp-missing-id",
				OccurredAt:    now,
			},
		},
		{
			name: "missing checkpoint",
			event: mediaports.OutboxEvent{
				EventID:       "event-missing-checkpoint",
				EventType:     "content.media_asset.created",
				AggregateType: "MediaAsset",
				AggregateID:   "asset-1",
				OccurredAt:    now,
			},
		},
		{
			name: "missing occurred time",
			event: mediaports.OutboxEvent{
				EventID:       "event-missing-occurred-at",
				EventType:     "content.media_asset.created",
				AggregateType: "MediaAsset",
				AggregateID:   "asset-1",
				Checkpoint:    "cp-missing-occurred-at",
			},
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			checkpoints := &fakeCheckpoints{}
			poisons := &fakePoisonEvents{}
			observer := &recordingObserver{}
			worker := NewMediaProcessingHandler(
				&fakeOutboxSource{events: []mediaports.OutboxEvent{testCase.event}},
				&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
				checkpoints,
				&fakeProcessor{},
				&fakeRecorder{},
				poisons,
				WithObserver(observer),
			)

			handled, err := worker.Process(context.Background(), 10)
			if err == nil || handled != 0 {
				t.Fatalf(
					"unquarantinable source cursor must stop the worker: handled=%d err=%v",
					handled,
					err,
				)
			}
			if len(checkpoints.saved) != 0 || len(poisons.recorded) != 0 {
				t.Fatalf(
					"unquarantinable cursor must not persist or advance: checkpoints=%v poisons=%#v",
					checkpoints.saved,
					poisons.recorded,
				)
			}
			if len(observer.poisons) != 1 ||
				observer.poisons[0] != "invalid_source_cursor" ||
				len(observer.poisonQuarantineFailures) != 0 {
				t.Fatalf(
					"source cursor signal drift: poisons=%v failures=%v",
					observer.poisons,
					observer.poisonQuarantineFailures,
				)
			}
		})
	}
}

func TestWorkerQuarantinesCorruptPersistedAssetSnapshot(t *testing.T) {
	poisons := &fakePoisonEvents{}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-corrupt-snapshot", "cp-corrupt-snapshot"),
		}},
		&fakeAssetLoader{
			assets: map[string]*mediamodel.MediaAsset{},
			err: fmt.Errorf(
				"restore media asset: %w",
				mediamodel.ErrInvalidMediaAsset,
			),
		},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
	)

	if handled, err := worker.Process(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("corrupt snapshot must be isolated: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 1 ||
		poisons.recorded[0].Reason != "invalid_asset_snapshot" {
		t.Fatalf("snapshot poison reason drift: %#v", poisons.recorded)
	}
	if len(checkpoints.saved) != 1 ||
		checkpoints.saved[0] != "cp-corrupt-snapshot" {
		t.Fatalf("checkpoint must follow snapshot quarantine: %v", checkpoints.saved)
	}
}

func TestWorkerQuarantinesMissingMediaAssetBeforeCheckpointAdvance(t *testing.T) {
	poisons := &fakePoisonEvents{}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-deleted-before-processing", "cp-missing-asset"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
	)

	if handled, err := worker.Process(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("missing aggregate must be quarantined and consumed: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 1 ||
		poisons.recorded[0].Reason != "missing_media_asset" {
		t.Fatalf("missing aggregate poison reason drift: %#v", poisons.recorded)
	}
	if len(checkpoints.saved) != 1 ||
		checkpoints.saved[0] != "cp-missing-asset" {
		t.Fatalf("checkpoint must follow missing aggregate quarantine: %v", checkpoints.saved)
	}
}

func TestWorkerSkipsEveryDeclaredNonProcessingFactWithoutQuarantine(t *testing.T) {
	now := time.Now().UTC()
	declaredNoops := []mediaports.OutboxEvent{
		{
			EventID:       "event-upload-initialized",
			EventType:     "content.media_upload.initialized",
			AggregateType: "MediaUploadSession",
			AggregateID:   "mus-initialized",
			OccurredAt:    now,
			Checkpoint:    "cp-1",
		},
		{
			EventID:       "event-upload-completed",
			EventType:     "content.media_upload.completed",
			AggregateType: "MediaUploadSession",
			AggregateID:   "mus-completed",
			OccurredAt:    now.Add(time.Nanosecond),
			Checkpoint:    "cp-2",
		},
		{
			EventID:       "event-upload-aborted",
			EventType:     "content.media_upload.aborted",
			AggregateType: "MediaUploadSession",
			AggregateID:   "mus-aborted",
			OccurredAt:    now.Add(2 * time.Nanosecond),
			Checkpoint:    "cp-3",
		},
		{
			EventID:       "event-processing-updated",
			EventType:     "content.media_asset.processing_updated",
			AggregateType: "MediaAsset",
			AggregateID:   "asset-processing-updated",
			OccurredAt:    now.Add(3 * time.Nanosecond),
			Checkpoint:    "cp-4",
		},
		{
			EventID:       "event-access-policy-updated",
			EventType:     "content.media_asset.access_policy_updated",
			AggregateType: "MediaAsset",
			AggregateID:   "asset-policy-updated",
			OccurredAt:    now.Add(4 * time.Nanosecond),
			Checkpoint:    "cp-5",
		},
	}
	poisons := &fakePoisonEvents{}
	checkpoints := &fakeCheckpoints{}
	source := &fakeOutboxSource{events: declaredNoops}
	worker := NewMediaProcessingHandler(
		source,
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
		WithLeaseOwner("media-processing-first-process"),
		WithClock(func() time.Time { return now }),
	)

	if handled, err := worker.Process(context.Background(), 10); err != nil || handled != len(declaredNoops) {
		t.Fatalf("declared no-op facts must advance only the processing cursor: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 0 {
		t.Fatalf("declared no-op facts must not be quarantined: %#v", poisons.recorded)
	}
	if len(checkpoints.saved) != len(declaredNoops) ||
		checkpoints.saved[len(checkpoints.saved)-1] != "cp-5" {
		t.Fatalf("processing cursor did not traverse declared no-op facts: %v", checkpoints.saved)
	}

	// A fresh worker process must resume from the same durable processing
	// checkpoint and must not re-quarantine or re-handle the declared facts.
	restarted := NewMediaProcessingHandler(
		source,
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
		WithLeaseOwner("media-processing-restarted-process"),
		WithClock(func() time.Time { return now.Add(time.Minute) }),
	)
	if handled, err := restarted.Process(context.Background(), 10); err != nil || handled != 0 {
		t.Fatalf("restarted worker must resume after declared no-op facts: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 0 || len(checkpoints.saved) != len(declaredNoops) {
		t.Fatalf(
			"restart changed no-op evidence: poisons=%#v checkpoints=%v",
			poisons.recorded,
			checkpoints.saved,
		)
	}
}

func TestWorkerQuarantinesUndeclaredOutboxTargetBeforeCheckpointAdvance(t *testing.T) {
	poisons := &fakePoisonEvents{}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{{
			EventID:       "event-undeclared-target",
			EventType:     "content.media_upload.reopened",
			AggregateType: "MediaUploadSession",
			AggregateID:   "mus-undeclared-target",
			OccurredAt:    time.Now(),
			Checkpoint:    "cp-undeclared-target",
		}}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		checkpoints,
		&fakeProcessor{},
		&fakeRecorder{},
		poisons,
	)

	if handled, err := worker.Process(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("undeclared target must be quarantined and consumed: handled=%d err=%v", handled, err)
	}
	if len(poisons.recorded) != 1 ||
		poisons.recorded[0].Reason != "unexpected_event_target" {
		t.Fatalf("undeclared target poison reason drift: %#v", poisons.recorded)
	}
	if len(checkpoints.saved) != 1 ||
		checkpoints.saved[0] != "cp-undeclared-target" {
		t.Fatalf("checkpoint must follow undeclared target quarantine: %v", checkpoints.saved)
	}
}

func TestWorkerCapsEachOutboxScanAtCommercialBatchLimit(t *testing.T) {
	const commercialBatchLimit = 10
	events := make([]mediaports.OutboxEvent, 0, commercialBatchLimit+1)
	for index := 0; index < commercialBatchLimit+1; index++ {
		events = append(events, mediaports.OutboxEvent{
			EventID:       fmt.Sprintf("event-session-%d", index),
			EventType:     "content.media_upload.completed",
			AggregateType: "MediaUploadSession",
			AggregateID:   fmt.Sprintf("session-%d", index),
			OccurredAt:    time.Now(),
			Checkpoint:    fmt.Sprintf("cp-%d", index),
		})
	}
	source := &fakeOutboxSource{events: events}
	observer := &recordingObserver{}
	worker := NewMediaProcessingHandler(
		source,
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{}},
		&fakeCheckpoints{},
		&fakeProcessor{},
		&fakeRecorder{},
		&fakePoisonEvents{},
		WithObserver(observer),
	)

	handled, err := worker.Process(context.Background(), commercialBatchLimit+1)
	if err != nil || handled != commercialBatchLimit {
		t.Fatalf("scan must be capped at %d: handled=%d err=%v", commercialBatchLimit, handled, err)
	}
	if source.lastLimit != commercialBatchLimit {
		t.Fatalf("source limit=%d, want commercial cap %d", source.lastLimit, commercialBatchLimit)
	}
	if len(observer.batchEvents) != 1 ||
		observer.batchEvents[0] != commercialBatchLimit ||
		observer.batchLimits[0] != commercialBatchLimit {
		t.Fatalf(
			"batch observability drift: events=%v limits=%v",
			observer.batchEvents,
			observer.batchLimits,
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
	worker := NewMediaProcessingHandler(
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
		&fakePoisonEvents{},
	)

	handled, err := worker.Process(context.Background(), 10)
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
		MimeType:           "image/jpeg",
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
			ProcessorProfile:         "content_image_normalization",
			ImageWidth:               1200,
			ImageHeight:              900,
			ImageDeliveryMimeType:    "image/jpeg",
			ImageNormalizedObjectKey: "media/processed/image/asset-image/v2/source.jpg",
			ImagePublicSliceKey:      "media/image/s/asset/asset-image/v2/source.jpg",
			ImageDominantColor:       "#1A2B3C",
			ImageLQIP:                "data:image/jpeg;base64,/9j/2Q==",
			ImageContentProfile:      "photographic",
			DerivativePolicyVersion:  1,
		},
	}
	processor := &fakeProcessor{outcome: ProcessOutcome{Descriptor: descriptor}}
	recorder := &fakeRecorder{}
	checkpoints := &fakeCheckpoints{}
	worker := NewMediaProcessingHandler(
		&fakeOutboxSource{events: []mediaports.OutboxEvent{
			assetCreatedEvent("asset-image", "cp-1"),
		}},
		&fakeAssetLoader{assets: map[string]*mediamodel.MediaAsset{"asset-image": imageAsset}},
		checkpoints,
		processor,
		recorder,
		&fakePoisonEvents{},
	)

	if _, err := worker.Process(context.Background(), 10); err != nil {
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
