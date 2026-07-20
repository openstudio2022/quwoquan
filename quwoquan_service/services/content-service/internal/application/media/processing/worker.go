package mediaprocessing

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

const (
	defaultConsumer       = "content-media-processing"
	assetCreatedEventType = "content.media_asset.created"
	mediaAssetAggregate   = "MediaAsset"
)

// Worker is the sole production consumer of the media outbox. It fulfils the
// `MediaAssetCreated -> media-processing` contract declared in
// contracts/metadata/content/media_asset/events.yaml: every uploaded image or
// video asset is probed, normalized and recorded ready/rejected, so publication
// can reach ready state without fixtures or test-only processing-result calls.
type Worker struct {
	source      OutboxSource
	assets      AssetSnapshotLoader
	checkpoints CheckpointStore
	processor   Processor
	recorder    ResultRecorder
	observer    Observer
	consumer    string
	now         func() time.Time

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

func NewWorker(
	source OutboxSource,
	assets AssetSnapshotLoader,
	checkpoints CheckpointStore,
	processor Processor,
	recorder ResultRecorder,
	options ...WorkerOption,
) *Worker {
	if source == nil || assets == nil || checkpoints == nil ||
		processor == nil || recorder == nil {
		panic("media processing worker requires outbox source, asset loader, checkpoints, processor and recorder")
	}
	worker := &Worker{
		source:      source,
		assets:      assets,
		checkpoints: checkpoints,
		processor:   processor,
		recorder:    recorder,
		consumer:    defaultConsumer,
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
	checkpoint, err := w.checkpoints.LoadCheckpoint(ctx, w.consumer)
	if err != nil {
		return 0, fmt.Errorf("load media processing checkpoint: %w", err)
	}
	events, err := w.source.ReadMediaOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read media outbox: %w", err)
	}
	if w.observer != nil {
		w.observer.OutboxLag(len(events))
	}
	for index, event := range events {
		if strings.TrimSpace(event.EventID) == "" {
			return index, fmt.Errorf("media outbox event at checkpoint %q has no event id", event.Checkpoint)
		}
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("media outbox event %q has no checkpoint", event.EventID)
		}
		if err := w.handleEvent(
			ctx,
			event.EventID,
			event.EventType,
			event.AggregateType,
			event.AggregateID,
		); err != nil {
			return index, err
		}
		if err := w.checkpoints.SaveCheckpoint(ctx, w.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf(
				"save media processing checkpoint for event %q: %w",
				event.EventID,
				err,
			)
		}
	}
	return len(events), nil
}

func (w *Worker) handleEvent(
	ctx context.Context,
	eventID string,
	eventType string,
	aggregateType string,
	aggregateID string,
) error {
	if eventType != assetCreatedEventType || aggregateType != mediaAssetAggregate {
		return nil
	}
	asset, found, err := w.assets.LoadMediaAsset(ctx, aggregateID)
	if err != nil {
		return fmt.Errorf("load media asset %q for processing: %w", aggregateID, err)
	}
	// 资产缺失、非视觉媒体或已离开 processing（重放、并发回写、已删除）
	// 都是幂等 no-op。
	if !found ||
		(asset.MediaType() != "image" && asset.MediaType() != "video") ||
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
		mediaProcessingResultIdempotencyKey(eventID),
	)
	var rejection *RejectionError
	switch {
	case err == nil:
		if _, recordErr := w.recorder.RecordMediaProcessingResult(recordContext, mediaapp.RecordMediaProcessingResultCommand{
			AssetID:    asset.ID(),
			Processing: mediamodel.ProcessingStatusReady,
			Descriptor: outcome.Descriptor,
		}); recordErr != nil {
			w.observe("record_failed", duration)
			return fmt.Errorf("record ready processing result for %q: %w", asset.ID(), recordErr)
		}
		w.observe("ready", duration)
		return nil
	case errors.As(err, &rejection):
		if _, recordErr := w.recorder.RecordMediaProcessingResult(recordContext, mediaapp.RecordMediaProcessingResultCommand{
			AssetID:       asset.ID(),
			Processing:    mediamodel.ProcessingStatusRejected,
			FailureReason: rejection.Reason,
		}); recordErr != nil {
			w.observe("record_failed", duration)
			return fmt.Errorf("record rejected processing result for %q: %w", asset.ID(), recordErr)
		}
		w.observe("rejected", duration)
		return nil
	default:
		w.observe("infrastructure_error", duration)
		return fmt.Errorf("process media asset %q: %w", asset.ID(), err)
	}
}

// 处理结果幂等键只由耐久源事实派生，跨进程重启与多副本保持稳定；
// 聚合版本 CAS 仍完全由应用服务在服务端管理。
func mediaProcessingResultIdempotencyKey(eventID string) string {
	return "media-processing-result:" + strings.TrimSpace(eventID)
}

func (w *Worker) observe(result string, duration time.Duration) {
	if w.observer != nil {
		w.observer.JobCompleted(result, duration)
	}
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
		if _, err := w.Drain(ctx, 20); err != nil {
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

// Healthy reports whether the worker recently completed a scan. Video
// processing is minute-grade work, so staleness tolerance is far looser than
// event relays; the readiness boundary owns the exact threshold.
func (w *Worker) Healthy(maxStaleness time.Duration) error {
	if w == nil {
		return fmt.Errorf("media processing worker is not configured")
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

func (w *Worker) recordSuccess() {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastSuccess = time.Now().UTC()
	w.lastFailure = nil
}

func (w *Worker) recordFailure(err error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastFailure = err
}
