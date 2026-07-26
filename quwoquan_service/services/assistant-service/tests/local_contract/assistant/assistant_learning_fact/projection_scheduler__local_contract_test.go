// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
)

type recordingLearningFactProjector struct {
	limit int
	count int
	err   error
}

func (projector *recordingLearningFactProjector) ProjectAvailable(
	_ context.Context,
	limit int,
) (int, error) {
	projector.limit = limit
	projector.count++
	return 1, projector.err
}

type rebuildingLearningFactProjector struct {
	recordingLearningFactProjector
	rebuildCount int
	rebuilt      chan struct{}
}

func (projector *rebuildingLearningFactProjector) ProjectAvailable(
	_ context.Context,
	limit int,
) (int, error) {
	projector.limit = limit
	projector.count++
	return 0, learningprojection.ErrDefinitionMismatch
}

func (projector *rebuildingLearningFactProjector) Rebuild(
	context.Context,
) (int, error) {
	projector.rebuildCount++
	close(projector.rebuilt)
	return 2, nil
}

func TestLearningProjectionSchedulerProjectsCanonicalFactBatch(t *testing.T) {
	projector := &recordingLearningFactProjector{}
	scheduler, err := learningprojection.NewScheduler(
		projector,
		time.Second,
		37,
		nil,
	)
	if err != nil {
		t.Fatalf("NewScheduler() error = %v", err)
	}
	projected, err := scheduler.RunOnce(t.Context())
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	if projected != 1 || projector.count != 1 || projector.limit != 37 {
		t.Fatalf(
			"projection invocation = projected=%d count=%d limit=%d",
			projected,
			projector.count,
			projector.limit,
		)
	}
}

func TestLearningProjectionSchedulerRejectsMissingProjectorAndInterval(t *testing.T) {
	if _, err := learningprojection.NewScheduler(nil, time.Second, 1, nil); err == nil {
		t.Fatal("missing projector must be rejected")
	}
	projector := &recordingLearningFactProjector{err: errors.New("storage unavailable")}
	if _, err := learningprojection.NewScheduler(projector, 0, 1, nil); err == nil {
		t.Fatal("non-positive interval must be rejected")
	}
}

func TestLearningProjectionSchedulerRebuildsObsoleteDefinition(t *testing.T) {
	projector := &rebuildingLearningFactProjector{
		rebuilt: make(chan struct{}),
	}
	scheduler, err := learningprojection.NewScheduler(
		projector,
		time.Hour,
		1,
		nil,
	)
	if err != nil {
		t.Fatalf("NewScheduler() error = %v", err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	go scheduler.Run(ctx)
	select {
	case <-projector.rebuilt:
	case <-time.After(time.Second):
		t.Fatal("obsolete projection definition was not rebuilt")
	}
	deadline := time.Now().Add(time.Second)
	for scheduler.Healthy(t.Context(), time.Second) != nil &&
		time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if err := scheduler.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("rebuilt scheduler health after completion: %v", err)
	}
	if projector.rebuildCount != 1 || projector.count != 1 {
		t.Fatalf(
			"rebuild invocation = rebuilds=%d projections=%d",
			projector.rebuildCount,
			projector.count,
		)
	}
}
