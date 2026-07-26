// Package reprocess orchestrates versioned image descriptor reprocessing. It
// intentionally delegates every descriptor mutation to the MediaAsset command
// facet so it can later move to its own service without duplicating media state.
package reprocess

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
	reprocessports "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/ports"
)

const receiptTTL = 24 * time.Hour

type ImageAssetReader interface {
	LoadMediaAsset(context.Context, string) (*mediamodel.MediaAsset, bool, error)
}

type DescriptorCommandWriter interface {
	ActivateReprocessedImageDescriptor(
		context.Context,
		mediaapp.ActivateReprocessedImageDescriptorCommand,
	) (mediaapp.ImageDescriptorActivationResult, error)
	RollbackReprocessedImageDescriptor(
		context.Context,
		mediaapp.RollbackReprocessedImageDescriptorCommand,
	) (mediaapp.MediaAssetCommandResult, error)
}

type Service struct {
	runs   reprocessports.RunStore
	assets ImageAssetReader
	now    func() time.Time
}

func NewService(runs reprocessports.RunStore, assets ImageAssetReader) *Service {
	if runs == nil || assets == nil {
		panic("media image reprocess service requires run store and image asset reader")
	}
	return &Service{runs: runs, assets: assets, now: time.Now}
}

type StartCommand struct {
	RunID    string
	AssetIDs []string
}

func (s *Service) Start(
	ctx context.Context,
	command StartCommand,
	targetPolicyVersion int,
) (*reprocessmodel.Run, bool, error) {
	if targetPolicyVersion <= 0 {
		return nil, false, fmt.Errorf(
			"%w: target policy version is required",
			reprocessmodel.ErrInvalidRun,
		)
	}
	if err := s.validateStartAssets(ctx, command.AssetIDs); err != nil {
		return nil, false, err
	}
	digest, err := commandDigest("StartMediaImageReprocessRun", command)
	if err != nil {
		return nil, false, err
	}
	if replayed, found, err := s.replay(ctx, "StartMediaImageReprocessRun", digest); err != nil || found {
		return replayed, found, err
	}
	run, err := reprocessmodel.Start(reprocessmodel.StartParams{
		RunID:                         command.RunID,
		TargetDerivativePolicyVersion: targetPolicyVersion,
		AssetIDs:                      command.AssetIDs,
		Now:                           s.now().UTC(),
	})
	if err != nil {
		return nil, false, err
	}
	committed, err := s.commit(ctx, run, 0, "StartMediaImageReprocessRun", digest)
	if err != nil {
		return nil, false, err
	}
	return committed.Aggregate, committed.Replayed, nil
}

func (s *Service) Pause(ctx context.Context, runID string) (*reprocessmodel.Run, bool, error) {
	return s.transition(ctx, runID, "PauseMediaImageReprocessRun", func(run *reprocessmodel.Run) error {
		return run.Pause(s.now().UTC())
	})
}

func (s *Service) Resume(ctx context.Context, runID string) (*reprocessmodel.Run, bool, error) {
	return s.transition(ctx, runID, "ResumeMediaImageReprocessRun", func(run *reprocessmodel.Run) error {
		return run.Resume(s.now().UTC())
	})
}

func (s *Service) StartRollback(ctx context.Context, runID string) (*reprocessmodel.Run, bool, error) {
	return s.transition(ctx, runID, "RollbackMediaImageReprocessRun", func(run *reprocessmodel.Run) error {
		return run.StartRollback(s.now().UTC())
	})
}

func (s *Service) Get(ctx context.Context, runID string) (*reprocessmodel.Run, error) {
	run, found, err := s.runs.LoadMediaImageReprocessRun(ctx, runID)
	if err != nil {
		return nil, fmt.Errorf("load media image reprocess run: %w", err)
	}
	if !found {
		return nil, fmt.Errorf("%w: %q", reprocessmodel.ErrRunNotFound, strings.TrimSpace(runID))
	}
	return run, nil
}

func (s *Service) transition(
	ctx context.Context,
	runID string,
	commandName string,
	mutate func(*reprocessmodel.Run) error,
) (*reprocessmodel.Run, bool, error) {
	digest, err := commandDigest(commandName, struct {
		RunID string `json:"runId"`
	}{RunID: strings.TrimSpace(runID)})
	if err != nil {
		return nil, false, err
	}
	if replayed, found, err := s.replay(ctx, commandName, digest); err != nil || found {
		return replayed, found, err
	}
	run, found, err := s.runs.LoadMediaImageReprocessRun(ctx, runID)
	if err != nil {
		return nil, false, fmt.Errorf("load media image reprocess run: %w", err)
	}
	if !found {
		return nil, false, fmt.Errorf("%w: %q", reprocessmodel.ErrRunNotFound, strings.TrimSpace(runID))
	}
	expectedVersion := run.Version()
	if err := mutate(run); err != nil {
		return nil, false, err
	}
	committed, err := s.commit(ctx, run, expectedVersion, commandName, digest)
	if err != nil {
		return nil, false, err
	}
	return committed.Aggregate, committed.Replayed, nil
}

func (s *Service) validateStartAssets(ctx context.Context, assetIDs []string) error {
	if len(assetIDs) == 0 || len(assetIDs) > reprocessmodel.MaxRunAssets {
		return fmt.Errorf(
			"%w: requires 1..%d explicit asset ids",
			reprocessmodel.ErrInvalidRun,
			reprocessmodel.MaxRunAssets,
		)
	}
	seen := make(map[string]struct{}, len(assetIDs))
	for _, rawAssetID := range assetIDs {
		assetID := strings.TrimSpace(rawAssetID)
		if assetID == "" {
			return fmt.Errorf("%w: asset id is required", reprocessmodel.ErrInvalidRun)
		}
		if _, exists := seen[assetID]; exists {
			return fmt.Errorf("%w: asset %q is duplicated", reprocessmodel.ErrInvalidRun, assetID)
		}
		seen[assetID] = struct{}{}
		asset, found, err := s.assets.LoadMediaAsset(ctx, assetID)
		if err != nil {
			return fmt.Errorf("load image reprocess asset %q: %w", assetID, err)
		}
		if !found || asset.MediaType() != "image" ||
			asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
			return fmt.Errorf(
				"%w: asset %q must be a ready image",
				reprocessmodel.ErrInvalidRun,
				assetID,
			)
		}
	}
	return nil
}

func (s *Service) replay(
	ctx context.Context,
	commandName string,
	digest string,
) (*reprocessmodel.Run, bool, error) {
	key := commandmeta.IdempotencyKey(ctx)
	if key == "" {
		return nil, false, fmt.Errorf(
			"%w: idempotency key is required",
			reprocessmodel.ErrInvalidRun,
		)
	}
	result, found, err := s.runs.FindMediaImageReprocessRunReceipt(ctx, key, commandName, digest)
	if err != nil {
		return nil, false, fmt.Errorf("find media image reprocess receipt: %w", err)
	}
	if !found {
		return nil, false, nil
	}
	if result.Aggregate == nil {
		return nil, false, errors.New("media image reprocess receipt has no run")
	}
	return result.Aggregate, true, nil
}

func (s *Service) commit(
	ctx context.Context,
	run *reprocessmodel.Run,
	expectedVersion int64,
	commandName string,
	digest string,
) (reprocessports.CommitResult, error) {
	key := commandmeta.IdempotencyKey(ctx)
	if key == "" {
		return reprocessports.CommitResult{}, fmt.Errorf(
			"%w: idempotency key is required",
			reprocessmodel.ErrInvalidRun,
		)
	}
	result, err := s.runs.CommitMediaImageReprocessRun(ctx, reprocessports.Commit{
		Aggregate:        run,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   key,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: s.now().UTC().Add(receiptTTL),
	})
	if err != nil {
		return reprocessports.CommitResult{}, fmt.Errorf("commit media image reprocess run: %w", err)
	}
	return result, nil
}

func commandDigest(commandName string, command any) (string, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return "", err
	}
	hash := sha256.Sum256(append([]byte(commandName+":"), encoded...))
	return hex.EncodeToString(hash[:]), nil
}

// Worker processes exactly one durable run cursor per Drain call. It obtains a
// per-run lease so replicas can safely take over after a crash.
type Worker struct {
	runs      reprocessports.RunStore
	assets    ImageAssetReader
	processor mediaprocessing.Processor
	media     DescriptorCommandWriter
	owner     string
	leaseTTL  time.Duration
	now       func() time.Time
}

func NewWorker(
	runs reprocessports.RunStore,
	assets ImageAssetReader,
	processor mediaprocessing.Processor,
	media DescriptorCommandWriter,
	owner string,
) *Worker {
	if runs == nil || assets == nil || processor == nil || media == nil {
		panic("media image reprocess worker requires run store, asset reader, processor and media facet")
	}
	if strings.TrimSpace(owner) == "" {
		panic("media image reprocess worker requires a stable lease owner")
	}
	return &Worker{
		runs: runs, assets: assets, processor: processor, media: media,
		owner: strings.TrimSpace(owner), leaseTTL: 30 * time.Second, now: time.Now,
	}
}

// SetClock injects the worker clock for deterministic contract verification.
// The worker remains service-internal, so this does not expand the public wire API.
func (w *Worker) SetClock(now func() time.Time) {
	if now == nil {
		w.now = time.Now
		return
	}
	w.now = now
}

func (w *Worker) Drain(ctx context.Context, limit int) (int, error) {
	runs, err := w.runs.ListRunnableMediaImageReprocessRuns(ctx, limit)
	if err != nil {
		return 0, err
	}
	handled := 0
	for _, run := range runs {
		acquired, err := w.runs.TryAcquireMediaImageReprocessRunLease(
			ctx, run.RunID(), w.owner, w.now().UTC(), w.leaseTTL,
		)
		if err != nil {
			return handled, err
		}
		if !acquired {
			continue
		}
		current, found, err := w.runs.LoadMediaImageReprocessRun(ctx, run.RunID())
		if err != nil {
			return handled, fmt.Errorf("reload leased media image reprocess run: %w", err)
		}
		if !found || (current.Status() != reprocessmodel.StatusRunning &&
			current.Status() != reprocessmodel.StatusRollingBack) {
			continue
		}
		if err := w.processOne(ctx, current); err != nil {
			return handled, err
		}
		handled++
	}
	return handled, nil
}

func (w *Worker) processOne(ctx context.Context, run *reprocessmodel.Run) error {
	jobContext, cancel := context.WithCancel(ctx)
	defer cancel()
	renewed := make(chan error, 1)
	renewalDone := make(chan struct{})
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
			case <-jobContext.Done():
				return
			case <-ticker.C:
				renewedOK, err := w.runs.RenewMediaImageReprocessRunLease(
					jobContext,
					run.RunID(),
					w.owner,
					w.now().UTC(),
					w.leaseTTL,
				)
				if err != nil {
					select {
					case renewed <- fmt.Errorf("renew media image reprocess run lease: %w", err):
					default:
					}
					cancel()
					return
				}
				if !renewedOK {
					select {
					case renewed <- errors.New("media image reprocess run lease lost"):
					default:
					}
					cancel()
					return
				}
			}
		}
	}()
	err := w.processOneUnderLease(jobContext, run)
	cancel()
	<-renewalDone
	select {
	case renewErr := <-renewed:
		return renewErr
	default:
		return err
	}
}

func (w *Worker) processOneUnderLease(ctx context.Context, run *reprocessmodel.Run) error {
	switch run.Status() {
	case reprocessmodel.StatusRunning:
		assetID, found := run.NextAssetID()
		if !found {
			return nil
		}
		asset, found, err := w.assets.LoadMediaAsset(ctx, assetID)
		if err != nil {
			return fmt.Errorf("load image reprocess asset: %w", err)
		}
		if !found || asset.MediaType() != "image" ||
			asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
			return w.commitContentFailure(ctx, run, assetID, "asset is no longer a ready image")
		}
		// The MediaAsset activation commits before the run cursor. If a process
		// dies between those two durable writes, recover the immutable activation
		// audit instead of producing a second candidate descriptor.
		if prior, activated := asset.ImageDescriptorActivationForRun(run.RunID()); activated {
			return w.commitOutcome(ctx, run, assetID, &reprocessmodel.Activation{
				AssetID:           assetID,
				PreviousRevision:  prior.PreviousRevision,
				ActivatedRevision: prior.Revision,
				ActivatedAt:       prior.ActivatedAt,
			}, "")
		}
		outcome, err := w.processor.Process(ctx, mediaprocessing.ProcessRequest{
			AssetID: asset.ID(), AssetVersion: asset.Version() + 1,
			SourceObjectKey: asset.ObjectKey(), MediaType: asset.MediaType(),
			ContentType: asset.ContentType(), FileSize: asset.FileSize(),
		})
		if err != nil {
			var rejected *mediaprocessing.RejectionError
			if errors.As(err, &rejected) {
				return w.commitContentFailure(ctx, run, assetID, rejected.Reason)
			}
			return fmt.Errorf("process image reprocess asset: %w", err)
		}
		if outcome.Descriptor.Image.DerivativePolicyVersion != run.TargetDerivativePolicyVersion() {
			return fmt.Errorf(
				"processor policy version %d does not match run policy version %d",
				outcome.Descriptor.Image.DerivativePolicyVersion,
				run.TargetDerivativePolicyVersion(),
			)
		}
		activationContext := commandmeta.WithIdempotencyKey(
			ctx,
			"media-image-reprocess:"+run.RunID()+":"+assetID+":activate",
		)
		activation, err := w.media.ActivateReprocessedImageDescriptor(
			activationContext,
			mediaapp.ActivateReprocessedImageDescriptorCommand{
				AssetID: assetID, RunID: run.RunID(), Descriptor: outcome.Descriptor.Image,
			},
		)
		if err != nil {
			return fmt.Errorf("activate image reprocess descriptor: %w", err)
		}
		if activation.PreviousRevision <= 0 || activation.ActivatedRevision <= 0 {
			return errors.New("replayed image reprocess activation lacks immutable audit revisions")
		}
		return w.commitOutcome(ctx, run, assetID, &reprocessmodel.Activation{
			AssetID: assetID, PreviousRevision: activation.PreviousRevision,
			ActivatedRevision: activation.ActivatedRevision, ActivatedAt: w.now().UTC(),
		}, "")
	case reprocessmodel.StatusRollingBack:
		activation, found := run.NextRollbackActivation()
		if !found {
			return nil
		}
		rollbackContext := commandmeta.WithIdempotencyKey(
			ctx,
			"media-image-reprocess:"+run.RunID()+":"+activation.AssetID+":rollback",
		)
		if _, err := w.media.RollbackReprocessedImageDescriptor(
			rollbackContext,
			mediaapp.RollbackReprocessedImageDescriptorCommand{
				AssetID: activation.AssetID, RunID: run.RunID(),
				PreviousRevision:  activation.PreviousRevision,
				ActivatedRevision: activation.ActivatedRevision,
			},
		); err != nil {
			return fmt.Errorf("rollback image reprocess descriptor: %w", err)
		}
		return w.commitRollback(ctx, run, activation)
	default:
		return nil
	}
}

func (w *Worker) commitContentFailure(ctx context.Context, run *reprocessmodel.Run, assetID string, reason string) error {
	return w.commitOutcome(ctx, run, assetID, nil, reason)
}

func (w *Worker) commitOutcome(
	ctx context.Context,
	run *reprocessmodel.Run,
	assetID string,
	activation *reprocessmodel.Activation,
	failure string,
) error {
	expectedVersion := run.Version()
	if err := run.RecordAssetOutcome(assetID, activation, failure, w.now().UTC()); err != nil {
		return err
	}
	digest, err := commandDigest("RecordMediaImageReprocessRunOutcome", run.Snapshot())
	if err != nil {
		return err
	}
	_, err = w.runs.CommitMediaImageReprocessRun(
		commandmeta.WithIdempotencyKey(ctx, "media-image-reprocess:"+run.RunID()+":"+assetID+":outcome"),
		reprocessports.Commit{
			Aggregate: run, ExpectedVersion: expectedVersion,
			IdempotencyKey: "media-image-reprocess:" + run.RunID() + ":" + assetID + ":outcome",
			CommandName:    "RecordMediaImageReprocessRunOutcome", CommandDigest: digest,
			ReceiptExpiresAt: w.now().UTC().Add(receiptTTL),
		},
	)
	return err
}

func (w *Worker) commitRollback(ctx context.Context, run *reprocessmodel.Run, activation reprocessmodel.Activation) error {
	expectedVersion := run.Version()
	if err := run.RecordRollback(activation, w.now().UTC()); err != nil {
		return err
	}
	digest, err := commandDigest("RecordMediaImageReprocessRollback", run.Snapshot())
	if err != nil {
		return err
	}
	_, err = w.runs.CommitMediaImageReprocessRun(
		commandmeta.WithIdempotencyKey(ctx, "media-image-reprocess:"+run.RunID()+":"+activation.AssetID+":rollback-outcome"),
		reprocessports.Commit{
			Aggregate: run, ExpectedVersion: expectedVersion,
			IdempotencyKey: "media-image-reprocess:" + run.RunID() + ":" + activation.AssetID + ":rollback-outcome",
			CommandName:    "RecordMediaImageReprocessRollback", CommandDigest: digest,
			ReceiptExpiresAt: w.now().UTC().Add(receiptTTL),
		},
	)
	return err
}
