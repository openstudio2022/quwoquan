package mediaprocessing

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	mediaports "quwoquan_service/services/content-service/internal/content/post/domain/media/ports"
)

const (
	defaultConsumer         = "content-media-processing"
	maxBatchSize            = 10
	assetCreatedEventType   = "content.media_asset.created"
	assetDiscardedEventType = "content.media_asset.discarded"
	mediaAssetAggregate     = "MediaAsset"
	defaultLeaseTTL         = 30 * time.Second

	poisonReasonInvalidEventMetadata = "invalid_event_metadata"
	poisonReasonInvalidAssetSnapshot = "invalid_asset_snapshot"
	poisonReasonMissingMediaAsset    = "missing_media_asset"
	poisonReasonUnexpectedTarget     = "unexpected_event_target"
	poisonReasonInvalidSourceCursor  = "invalid_source_cursor"
)

var errMediaProcessingLeaseLost = errors.New("media processing worker lease lost")

// Worker is the sole production consumer of the media outbox. It fulfils the
// `MediaAssetCreated -> media-processing` contract declared in
// services/content-service/contracts/media/media_asset/events.yaml: every uploaded image or
// video asset is probed, normalized and recorded ready/rejected, so publication
// can reach ready state without fixtures or test-only processing-result calls.
type Worker struct {
	source       OutboxSource
	assets       AssetSnapshotLoader
	checkpoints  CheckpointStore
	leases       CheckpointLeaseStore
	processor    Processor
	recorder     ResultRecorder
	poisons      PoisonEventRecorder
	cleanupStore ArtifactCleanupStore
	reclaimer    ArtifactReclaimer
	observer     Observer
	consumer     string
	leaseOwner   string
	leaseTTL     time.Duration
	now          func() time.Time

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

type WorkerOption func(*Worker)

func WithConsumer(consumer string) WorkerOption {
	return func(w *Worker) {
		if consumer = strings.TrimSpace(consumer); consumer != "" {
			w.consumer = consumer
		}
	}
}

func WithObserver(observer Observer) WorkerOption {
	return func(w *Worker) {
		if observer != nil {
			w.observer = observer
		}
	}
}

func WithClock(now func() time.Time) WorkerOption {
	return func(w *Worker) {
		if now != nil {
			w.now = now
		}
	}
}

func WithLeaseOwner(owner string) WorkerOption {
	return func(w *Worker) {
		if owner = strings.TrimSpace(owner); owner != "" {
			w.leaseOwner = owner
		}
	}
}

func WithLeaseTTL(ttl time.Duration) WorkerOption {
	return func(w *Worker) {
		if ttl > 0 {
			w.leaseTTL = ttl
		}
	}
}

func WithArtifactCleanup(
	store ArtifactCleanupStore,
	reclaimer ArtifactReclaimer,
) WorkerOption {
	return func(w *Worker) {
		if store != nil && reclaimer != nil {
			w.cleanupStore = store
			w.reclaimer = reclaimer
		}
	}
}

func NewWorker(
	source OutboxSource,
	assets AssetSnapshotLoader,
	checkpoints CheckpointStore,
	processor Processor,
	recorder ResultRecorder,
	poisons PoisonEventRecorder,
	options ...WorkerOption,
) *Worker {
	if source == nil || assets == nil || checkpoints == nil ||
		processor == nil || recorder == nil || poisons == nil {
		panic("media processing worker requires outbox source, asset loader, checkpoints, processor, result recorder and poison recorder")
	}
	leases, ok := checkpoints.(CheckpointLeaseStore)
	if !ok {
		panic("media processing worker requires a checkpoint store with durable lease controls")
	}
	worker := &Worker{
		source:      source,
		assets:      assets,
		checkpoints: checkpoints,
		leases:      leases,
		processor:   processor,
		recorder:    recorder,
		poisons:     poisons,
		consumer:    defaultConsumer,
		leaseOwner:  newLeaseOwner(),
		leaseTTL:    defaultLeaseTTL,
		now:         time.Now,
	}
	for _, option := range options {
		option(worker)
	}
	return worker
}

// Drain consumes at most limit durable media facts. Content-level failures
// record the asset as rejected and advance; infrastructure failures leave the
// event for replay so nothing is silently dropped.
func (w *Worker) Drain(ctx context.Context, limit int) (int, error) {
	limit = normalizedBatchLimit(limit)
	if w.leases == nil || strings.TrimSpace(w.leaseOwner) == "" || w.leaseTTL <= 0 {
		return 0, errors.New("media processing worker lease is not configured")
	}
	acquired, err := w.leases.TryAcquireMediaProcessingLease(
		ctx,
		w.consumer,
		w.leaseOwner,
		w.now().UTC(),
		w.leaseTTL,
	)
	if err != nil {
		return 0, fmt.Errorf("acquire media processing lease: %w", err)
	}
	if !acquired {
		// Standby replicas share this consumer cursor but never invoke FFmpeg
		// for the same asset concurrently. They retry after the active lease
		// owner exits or expires.
		if w.observer != nil {
			w.observer.BatchObserved(0, limit)
		}
		return 0, nil
	}
	checkpoint, err := w.checkpoints.LoadCheckpoint(ctx, w.consumer)
	if err != nil {
		return 0, fmt.Errorf("load media processing checkpoint: %w", err)
	}
	events, err := w.source.ReadMediaOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read media outbox: %w", err)
	}
	if w.observer != nil {
		w.observer.BatchObserved(len(events), limit)
		w.observer.OutboxOldestEventAge(oldestEventAge(events, w.now().UTC()))
	}
	for index, event := range events {
		if strings.TrimSpace(event.EventID) == "" {
			w.observePoison(poisonReasonInvalidSourceCursor, 0)
			return index, fmt.Errorf("media outbox event at checkpoint %q has no event id", event.Checkpoint)
		}
		if strings.TrimSpace(event.Checkpoint) == "" {
			w.observePoison(poisonReasonInvalidSourceCursor, 0)
			return index, fmt.Errorf("media outbox event %q has no checkpoint", event.EventID)
		}
		if event.OccurredAt.IsZero() {
			w.observePoison(poisonReasonInvalidSourceCursor, 0)
			return index, fmt.Errorf(
				"media outbox event %q at checkpoint %q has no occurred time",
				event.EventID,
				event.Checkpoint,
			)
		}
		if err := w.handleEventUnderLease(ctx, event); err != nil {
			return index, err
		}
		advanced, err := w.leases.SaveMediaProcessingCheckpointWithLease(
			ctx,
			w.consumer,
			w.leaseOwner,
			event.Checkpoint,
			w.now().UTC(),
			w.leaseTTL,
		)
		if err != nil {
			return index, fmt.Errorf(
				"save media processing checkpoint for event %q: %w",
				event.EventID,
				err,
			)
		}
		if !advanced {
			return index, fmt.Errorf(
				"save media processing checkpoint for event %q: %w",
				event.EventID,
				errMediaProcessingLeaseLost,
			)
		}
	}
	return len(events), nil
}

func normalizedBatchLimit(limit int) int {
	if limit <= 0 || limit > maxBatchSize {
		return maxBatchSize
	}
	return limit
}

func (w *Worker) handleEvent(
	ctx context.Context,
	event mediaports.OutboxEvent,
) error {
	if event.AggregateType != mediaAssetAggregate {
		return w.quarantine(ctx, event, poisonReasonUnexpectedTarget)
	}
	if strings.TrimSpace(event.AggregateID) == "" {
		return w.quarantine(ctx, event, poisonReasonInvalidEventMetadata)
	}
	if event.EventType == assetDiscardedEventType {
		return w.cleanupDiscardedAsset(ctx, event)
	}
	if event.EventType != assetCreatedEventType {
		return w.quarantine(ctx, event, poisonReasonUnexpectedTarget)
	}
	asset, found, err := w.assets.LoadMediaAsset(ctx, event.AggregateID)
	if err != nil {
		if errors.Is(err, mediamodel.ErrInvalidMediaAsset) {
			return w.quarantine(ctx, event, poisonReasonInvalidAssetSnapshot)
		}
		return fmt.Errorf(
			"load media asset %q for processing: %w",
			event.AggregateID,
			err,
		)
	}
	if !found {
		return w.quarantine(ctx, event, poisonReasonMissingMediaAsset)
	}
	if asset == nil {
		return w.quarantine(ctx, event, poisonReasonInvalidAssetSnapshot)
	}
	// 非视觉媒体或已离开 processing（重放、并发回写）是幂等 no-op。
	if (asset.MediaType() != "image" && asset.MediaType() != "video") ||
		asset.ProcessingStatus() != mediamodel.ProcessingStatusProcessing {
		return nil
	}
	started := w.now()
	outcome, err := w.processor.Process(ctx, ProcessRequest{
		AssetID:         asset.ID(),
		AssetVersion:    asset.Version() + 1,
		SourceObjectKey: asset.ObjectKey(),
		MediaType:       asset.MediaType(),
		ContentType:     asset.ContentType(),
		FileSize:        asset.FileSize(),
	})
	duration := w.now().Sub(started)
	recordContext := commandmeta.WithIdempotencyKey(
		ctx,
		mediaProcessingResultIdempotencyKey(event.EventID),
	)
	var rejection *RejectionError
	switch {
	case err == nil:
		if _, recordErr := w.recorder.RecordMediaProcessingResult(recordContext, mediaapp.RecordMediaProcessingResultCommand{
			AssetID:    asset.ID(),
			Processing: mediamodel.ProcessingStatusReady,
			Descriptor: outcome.Descriptor,
		}); recordErr != nil {
			w.observe(asset.MediaType(), inputSizeClass(asset.FileSize()), "record_failed", duration)
			return fmt.Errorf("record ready processing result for %q: %w", asset.ID(), recordErr)
		}
		w.observe(asset.MediaType(), inputSizeClass(asset.FileSize()), "ready", duration)
		w.observeCompleteToReady(
			asset.MediaType(),
			inputSizeClass(asset.FileSize()),
			nonNegativeAge(w.now().UTC().Sub(event.OccurredAt.UTC())),
		)
		return nil
	case errors.As(err, &rejection):
		if _, recordErr := w.recorder.RecordMediaProcessingResult(recordContext, mediaapp.RecordMediaProcessingResultCommand{
			AssetID:       asset.ID(),
			Processing:    mediamodel.ProcessingStatusRejected,
			FailureReason: rejection.Reason,
		}); recordErr != nil {
			w.observe(asset.MediaType(), inputSizeClass(asset.FileSize()), "record_failed", duration)
			return fmt.Errorf("record rejected processing result for %q: %w", asset.ID(), recordErr)
		}
		w.observe(asset.MediaType(), inputSizeClass(asset.FileSize()), "rejected", duration)
		return nil
	default:
		w.observe(asset.MediaType(), inputSizeClass(asset.FileSize()), "infrastructure_error", duration)
		return fmt.Errorf("process media asset %q: %w", asset.ID(), err)
	}
}

func (w *Worker) cleanupDiscardedAsset(
	ctx context.Context,
	event mediaports.OutboxEvent,
) error {
	if w.cleanupStore == nil || w.reclaimer == nil {
		return errors.New("media artifact cleanup is not configured")
	}
	work, done, err := w.cleanupStore.PrepareMediaAssetArtifactCleanup(
		ctx,
		event.AggregateID,
		event.EventID,
	)
	if err != nil {
		return fmt.Errorf(
			"prepare discarded MediaAsset %q cleanup: %w",
			event.AggregateID,
			err,
		)
	}
	if done {
		return nil
	}
	if err := w.reclaimer.ReclaimMediaArtifacts(
		ctx,
		work.PublicSliceKeys,
		work.PublicPrefixes,
		work.PrivateObjectKeys,
		work.PrivatePrefixes,
	); err != nil {
		return fmt.Errorf(
			"reclaim discarded MediaAsset %q artifacts: %w",
			event.AggregateID,
			err,
		)
	}
	if err := w.cleanupStore.MarkMediaAssetArtifactsDeleted(
		ctx,
		event.AggregateID,
		work.WorkID,
	); err != nil {
		return fmt.Errorf(
			"complete discarded MediaAsset %q cleanup: %w",
			event.AggregateID,
			err,
		)
	}
	return nil
}

func (w *Worker) handleEventUnderLease(
	ctx context.Context,
	event mediaports.OutboxEvent,
) error {
	processingCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	renewalDone := make(chan struct{})
	leaseLost := make(chan error, 1)
	go func() {
		defer close(renewalDone)
		interval := w.leaseTTL / 3
		if interval <= 0 {
			interval = time.Second
		}
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-processingCtx.Done():
				return
			case <-ticker.C:
				renewed, err := w.leases.RenewMediaProcessingLease(
					processingCtx,
					w.consumer,
					w.leaseOwner,
					w.now().UTC(),
					w.leaseTTL,
				)
				if err != nil {
					select {
					case leaseLost <- fmt.Errorf("renew media processing lease: %w", err):
					default:
					}
					cancel()
					return
				}
				if !renewed {
					select {
					case leaseLost <- errMediaProcessingLeaseLost:
					default:
					}
					cancel()
					return
				}
			}
		}
	}()

	err := w.handleEvent(processingCtx, event)
	cancel()
	<-renewalDone
	select {
	case leaseErr := <-leaseLost:
		return leaseErr
	default:
		return err
	}
}

func (w *Worker) quarantine(
	ctx context.Context,
	event mediaports.OutboxEvent,
	reason string,
) error {
	if err := w.poisons.QuarantineMediaProcessingEvent(ctx, PoisonEvent{
		Consumer:      w.consumer,
		EventID:       event.EventID,
		EventType:     event.EventType,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Checkpoint:    event.Checkpoint,
		OccurredAt:    event.OccurredAt.UTC(),
		Reason:        reason,
		QuarantinedAt: w.now().UTC(),
	}); err != nil {
		w.observePoisonQuarantineFailure(reason)
		return fmt.Errorf(
			"quarantine media event %q before checkpoint advance: %w",
			event.EventID,
			err,
		)
	}
	w.observePoison(reason, nonNegativeAge(w.now().UTC().Sub(event.OccurredAt.UTC())))
	return nil
}

// 处理结果幂等键只由耐久源事实派生，跨进程重启与多副本保持稳定；
// 聚合版本 CAS 仍完全由应用服务在服务端管理。
func mediaProcessingResultIdempotencyKey(eventID string) string {
	return "media-processing-result:" + strings.TrimSpace(eventID)
}

func (w *Worker) observe(
	mediaType string,
	inputSizeClass string,
	result string,
	duration time.Duration,
) {
	if w.observer != nil {
		w.observer.JobCompleted(mediaType, inputSizeClass, result, duration)
	}
}

func inputSizeClass(fileSize int64) string {
	switch {
	case fileSize <= 0:
		return "unknown"
	case fileSize <= 1*1024*1024:
		return "under_1mb"
	case fileSize <= 10*1024*1024:
		return "one_to_10mb"
	case fileSize <= 100*1024*1024:
		return "ten_to_100mb"
	default:
		return "over_100mb"
	}
}

func oldestEventAge(events []mediaports.OutboxEvent, now time.Time) time.Duration {
	var oldest time.Time
	for _, event := range events {
		if event.OccurredAt.IsZero() {
			continue
		}
		if oldest.IsZero() || event.OccurredAt.Before(oldest) {
			oldest = event.OccurredAt
		}
	}
	if oldest.IsZero() {
		return 0
	}
	return nonNegativeAge(now.Sub(oldest.UTC()))
}

func nonNegativeAge(age time.Duration) time.Duration {
	if age < 0 {
		return 0
	}
	return age
}

func (w *Worker) observeCompleteToReady(
	mediaType string,
	inputSizeClass string,
	duration time.Duration,
) {
	if w.observer != nil {
		w.observer.CompleteToReady(mediaType, inputSizeClass, duration)
	}
}

func (w *Worker) observePoison(reason string, eventAge time.Duration) {
	if w.observer != nil {
		w.observer.Poisoned(reason, eventAge)
	}
}

func (w *Worker) observePoisonQuarantineFailure(reason string) {
	if w.observer != nil {
		w.observer.PoisonQuarantineFailed(reason)
	}
}

func newLeaseOwner() string {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err == nil {
		return "content-media-worker-" + hex.EncodeToString(raw[:])
	}
	return fmt.Sprintf("content-media-worker-fallback-%d", time.Now().UnixNano())
}

// Run drains until the application context ends. A failed batch is retried
// after interval without advancing its checkpoint, matching the Post outbox
// relay semantics.
func (w *Worker) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		if _, err := w.Drain(ctx, maxBatchSize); err != nil {
			w.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
				continue
			}
		}
		w.recordSuccess()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Live proves the in-process worker module is wired. It deliberately does not
// inspect scan freshness: liveness answers whether this process should be
// restarted, while readiness determines whether it can accept media work.
func (w *Worker) Live() error {
	if w == nil {
		return fmt.Errorf("media processing worker is not configured")
	}
	return nil
}

// Ready reports whether the worker recently completed a scan. Video
// processing is minute-grade work, so staleness tolerance is far looser than
// event relays; the readiness boundary owns the exact threshold.
func (w *Worker) Ready(maxStaleness time.Duration) error {
	if err := w.Live(); err != nil {
		return err
	}
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Minute
	}
	w.mu.RLock()
	defer w.mu.RUnlock()
	if w.lastSuccess.IsZero() {
		return fmt.Errorf("media processing worker has not completed a scan")
	}
	if w.lastFailure != nil {
		return fmt.Errorf("media processing worker last failure: %w", w.lastFailure)
	}
	if time.Since(w.lastSuccess) > maxStaleness {
		return fmt.Errorf(
			"media processing worker heartbeat is stale: %s",
			time.Since(w.lastSuccess).Round(time.Millisecond),
		)
	}
	return nil
}

// Healthy remains the worker-local readiness compatibility name. HTTP
// lifecycle routes must call Ready or Live explicitly.
func (w *Worker) Healthy(maxStaleness time.Duration) error {
	return w.Ready(maxStaleness)
}

func (w *Worker) recordSuccess() {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastSuccess = w.now().UTC()
	w.lastFailure = nil
}

func (w *Worker) recordFailure(err error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastFailure = err
}
