package reprocess_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
	reprocessports "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/ports"
)

func TestWorkerContinuesAfterContentFailureAndRollsBackActivation(t *testing.T) {
	now := time.Date(2026, 7, 21, 2, 0, 0, 0, time.UTC)
	first := readyImageAsset(t, "image-first", now)
	second := readyImageAsset(t, "image-second", now)
	run, err := reprocessmodel.Start(reprocessmodel.StartParams{
		RunID: "run-1", TargetDerivativePolicyVersion: 1,
		AssetIDs: []string{first.ID(), second.ID()}, Now: now,
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	store := &fakeRunStore{run: run}
	processor := &fakeProcessor{outcomes: map[string]mediaprocessing.ProcessOutcome{
		first.ID(): {Descriptor: mediamodel.MediaProcessingDescriptor{
			Image: testDescriptor(first.ID(), 3),
		}},
	}, errors: map[string]error{
		second.ID(): &mediaprocessing.RejectionError{Reason: "corrupt image bytes"},
	}}
	media := &fakeDescriptorWriter{}
	worker := NewWorker(
		store,
		&fakeAssetReader{assets: map[string]*mediamodel.MediaAsset{
			first.ID(): first, second.ID(): second,
		}},
		processor,
		media,
		"replica-1",
	)
	worker.SetClock(func() time.Time { return now.Add(time.Second) })

	if handled, err := worker.Drain(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("first drain=(handled=%d, err=%v)", handled, err)
	}
	if handled, err := worker.Drain(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("second drain=(handled=%d, err=%v)", handled, err)
	}
	if run.Status() != reprocessmodel.StatusCompleted {
		t.Fatalf("run status=%s, want completed", run.Status())
	}
	snapshot := run.Snapshot()
	if snapshot.ProcessedCount != 1 || snapshot.FailedCount != 1 ||
		len(snapshot.Activations) != 1 || len(media.activations) != 1 {
		t.Fatalf("content failure must be audited and remaining assets processed: %+v", snapshot)
	}
	if err := run.StartRollback(now.Add(2 * time.Second)); err != nil {
		t.Fatalf("start rollback: %v", err)
	}
	worker.SetClock(func() time.Time { return now.Add(3 * time.Second) })
	if handled, err := worker.Drain(context.Background(), 10); err != nil || handled != 1 {
		t.Fatalf("rollback drain=(handled=%d, err=%v)", handled, err)
	}
	if run.Status() != reprocessmodel.StatusRolledBack || len(media.rollbacks) != 1 {
		t.Fatalf("rollback must restore exactly activated descriptors: %+v", run.Snapshot())
	}
}

type fakeRunStore struct{ run *reprocessmodel.Run }

func (s *fakeRunStore) LoadMediaImageReprocessRun(_ context.Context, runID string) (*reprocessmodel.Run, bool, error) {
	return s.run, s.run != nil && s.run.RunID() == runID, nil
}
func (s *fakeRunStore) FindMediaImageReprocessRunReceipt(context.Context, string, string, string) (reprocessports.CommitResult, bool, error) {
	return reprocessports.CommitResult{}, false, nil
}
func (s *fakeRunStore) CommitMediaImageReprocessRun(_ context.Context, commit reprocessports.Commit) (reprocessports.CommitResult, error) {
	s.run = commit.Aggregate
	return reprocessports.CommitResult{Aggregate: commit.Aggregate}, nil
}
func (s *fakeRunStore) ListRunnableMediaImageReprocessRuns(_ context.Context, _ int) ([]*reprocessmodel.Run, error) {
	if s.run == nil || (s.run.Status() != reprocessmodel.StatusRunning && s.run.Status() != reprocessmodel.StatusRollingBack) {
		return nil, nil
	}
	return []*reprocessmodel.Run{s.run}, nil
}
func (s *fakeRunStore) TryAcquireMediaImageReprocessRunLease(context.Context, string, string, time.Time, time.Duration) (bool, error) {
	return true, nil
}
func (s *fakeRunStore) RenewMediaImageReprocessRunLease(context.Context, string, string, time.Time, time.Duration) (bool, error) {
	return true, nil
}

type fakeAssetReader struct {
	assets map[string]*mediamodel.MediaAsset
}

func (r *fakeAssetReader) LoadMediaAsset(_ context.Context, assetID string) (*mediamodel.MediaAsset, bool, error) {
	asset, found := r.assets[assetID]
	return asset, found, nil
}

type fakeProcessor struct {
	outcomes map[string]mediaprocessing.ProcessOutcome
	errors   map[string]error
}

func (p *fakeProcessor) Process(_ context.Context, request mediaprocessing.ProcessRequest) (mediaprocessing.ProcessOutcome, error) {
	if err := p.errors[request.AssetID]; err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	return p.outcomes[request.AssetID], nil
}

type fakeDescriptorWriter struct {
	activations []mediaapp.ActivateReprocessedImageDescriptorCommand
	rollbacks   []mediaapp.RollbackReprocessedImageDescriptorCommand
}

func (w *fakeDescriptorWriter) ActivateReprocessedImageDescriptor(
	_ context.Context,
	command mediaapp.ActivateReprocessedImageDescriptorCommand,
) (mediaapp.ImageDescriptorActivationResult, error) {
	w.activations = append(w.activations, command)
	return mediaapp.ImageDescriptorActivationResult{
		AssetID: command.AssetID, Version: 3, PreviousRevision: 1, ActivatedRevision: 2,
	}, nil
}

func (w *fakeDescriptorWriter) RollbackReprocessedImageDescriptor(
	_ context.Context,
	command mediaapp.RollbackReprocessedImageDescriptorCommand,
) (mediaapp.MediaAssetCommandResult, error) {
	w.rollbacks = append(w.rollbacks, command)
	return mediaapp.MediaAssetCommandResult{AssetID: command.AssetID}, nil
}

func readyImageAsset(t *testing.T, assetID string, now time.Time) *mediamodel.MediaAsset {
	t.Helper()
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: assetID, OwnerID: "owner", SourceSessionID: "session-" + assetID,
		ObjectKey: "private/" + assetID + "/source.jpg",
		SHA256:    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly, ProcessingRequired: true, Now: now,
	})
	if err != nil {
		t.Fatalf("create asset: %v", err)
	}
	if err := asset.RecordProcessingResult(
		mediamodel.ProcessingStatusReady,
		"",
		mediamodel.MediaProcessingDescriptor{Image: testDescriptor(assetID, 2)},
		now.Add(time.Millisecond),
	); err != nil {
		t.Fatalf("record asset: %v", err)
	}
	return asset
}

func testDescriptor(assetID string, version int64) mediamodel.ImageProcessingDescriptor {
	return mediamodel.ImageProcessingDescriptor{
		ProcessorProfile: "test", ImageWidth: 100, ImageHeight: 100,
		ImageDeliveryContentType: "image/jpeg",
		ImageNormalizedObjectKey: "private/" + assetID + "/v/source.jpg",
		ImagePublicSliceKey:      runtimemedia.BuildContentMediaPublicSliceKey("image", assetID, version, "image/jpeg"),
		ImageDominantColor:       "#112233", ImageLQIP: "data:image/jpeg;base64,/9j/2Q==",
		ImageContentProfile: "photographic", DerivativePolicyVersion: 1,
	}
}
