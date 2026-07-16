package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	experimentapp "quwoquan_service/services/product-ops-service/internal/application/product_ops/experiment"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/domain/product_ops/experiment/model"
	experimentports "quwoquan_service/services/product-ops-service/internal/domain/product_ops/experiment/ports"
)

type testExperimentStore struct {
	mu          sync.Mutex
	experiments map[string]experimentmodel.Experiment
	assignments map[string]experimentmodel.AssignmentFact
	receipts    map[string]experimentports.CommitReceipt
	digests     map[string]string
	events      []experimentmodel.Event
}

func newTestExperimentFacade(t *testing.T) *experimentapp.Facade {
	t.Helper()
	now := time.Now().UTC().Format(time.RFC3339)
	store := &testExperimentStore{
		experiments: map[string]experimentmodel.Experiment{
			"discovery_feed_v3": {
				ID: "discovery_feed_v3", Key: "discovery_feed_v3", Version: 1, Status: "running",
				AllocationSeed: "discovery-feed-v3-seed",
				AudienceRule:   experimentmodel.AudienceRule{Kind: "all"},
				CreatedAt:      now, UpdatedAt: now,
				Variants: []experimentmodel.Variant{
					{Key: "control", AllocationBasisPoints: 5000},
					{Key: "variant_a", AllocationBasisPoints: 2500},
					{Key: "variant_b", AllocationBasisPoints: 2500},
				},
			},
		},
		assignments: map[string]experimentmodel.AssignmentFact{},
		receipts:    map[string]experimentports.CommitReceipt{},
		digests:     map[string]string{},
	}
	facade, err := experimentapp.NewFacade(store, store, store, store)
	if err != nil {
		t.Fatalf("build experiment facade: %v", err)
	}
	return facade
}

func (s *testExperimentStore) Load(_ context.Context, id string) (experimentmodel.Experiment, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	experiment, ok := s.experiments[id]
	if !ok {
		return experimentmodel.Experiment{}, experimentmodel.ErrNotFound
	}
	return cloneExperiment(experiment), nil
}

func (s *testExperimentStore) List(context.Context) ([]experimentmodel.Experiment, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]experimentmodel.Experiment, 0, len(s.experiments))
	for _, experiment := range s.experiments {
		out = append(out, cloneExperiment(experiment))
	}
	return out, nil
}

func (s *testExperimentStore) Replay(
	_ context.Context,
	experimentID, idempotencyKey, commandDigest string,
) (experimentports.CommitReceipt, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receiptKey := experimentID + "\x00" + idempotencyKey
	receipt, ok := s.receipts[receiptKey]
	if !ok {
		return experimentports.CommitReceipt{}, false, nil
	}
	if s.digests[receiptKey] != commandDigest {
		return experimentports.CommitReceipt{}, false, experimentmodel.ErrIdempotencyConflict
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *testExperimentStore) Commit(
	_ context.Context,
	expectedVersion int64,
	changes experimentports.ChangeSet,
) (experimentports.CommitReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receiptKey := changes.Experiment.ID + "\x00" + changes.IdempotencyKey
	if receipt, ok := s.receipts[receiptKey]; ok {
		if s.digests[receiptKey] != changes.CommandDigest {
			return experimentports.CommitReceipt{}, experimentmodel.ErrIdempotencyConflict
		}
		receipt.Replayed = true
		return receipt, nil
	}
	current, ok := s.experiments[changes.Experiment.ID]
	if !ok {
		return experimentports.CommitReceipt{}, experimentmodel.ErrNotFound
	}
	if current.Version != expectedVersion {
		return experimentports.CommitReceipt{}, experimentmodel.ErrVersionConflict
	}
	s.experiments[changes.Experiment.ID] = cloneExperiment(changes.Experiment)
	s.events = append(s.events, changes.Events...)
	receipt := experimentports.CommitReceipt{
		ExperimentID: changes.Experiment.ID,
		Version:      changes.Experiment.Version,
	}
	s.receipts[receiptKey] = receipt
	s.digests[receiptKey] = changes.CommandDigest
	return receipt, nil
}

func (s *testExperimentStore) Append(
	_ context.Context,
	fact experimentmodel.AssignmentFact,
	event experimentmodel.Event,
) (experimentmodel.AssignmentFact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := assignmentKey(fact.ExperimentID, fact.PolicyVersion, fact.SubjectKey)
	if existing, ok := s.assignments[key]; ok {
		return existing, false, nil
	}
	s.assignments[key] = fact
	s.events = append(s.events, event)
	return fact, true, nil
}

func (s *testExperimentStore) Get(
	_ context.Context,
	experimentID, policyVersion, subjectKey string,
) (experimentmodel.AssignmentFact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	fact, ok := s.assignments[assignmentKey(experimentID, policyVersion, subjectKey)]
	if !ok {
		return experimentmodel.AssignmentFact{}, experimentmodel.ErrAssignmentNotFound
	}
	return fact, nil
}

func (s *testExperimentStore) Stats(
	_ context.Context,
	experimentID, policyVersion string,
) (experimentports.AssignmentStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := experimentports.AssignmentStats{VariantCounts: map[string]int{}}
	for _, fact := range s.assignments {
		if fact.ExperimentID != experimentID || fact.PolicyVersion != policyVersion {
			continue
		}
		out.VariantCounts[fact.Variant]++
		out.AssignedSubjects++
	}
	return out, nil
}

func cloneExperiment(in experimentmodel.Experiment) experimentmodel.Experiment {
	raw, err := json.Marshal(in)
	if err != nil {
		panic(err)
	}
	var out experimentmodel.Experiment
	if err := json.Unmarshal(raw, &out); err != nil {
		panic(err)
	}
	return out
}

func assignmentKey(experimentID, policyVersion, subjectKey string) string {
	return fmt.Sprintf("%s:%s:%s", experimentID, policyVersion, subjectKey)
}

var (
	_ experimentports.AggregateStore   = (*testExperimentStore)(nil)
	_ experimentports.CatalogReader    = (*testExperimentStore)(nil)
	_ experimentports.AssignmentSink   = (*testExperimentStore)(nil)
	_ experimentports.AssignmentReader = (*testExperimentStore)(nil)
)

func TestExperimentTestStorePreservesStableAssignmentFact(t *testing.T) {
	facade := newTestExperimentFacade(t)
	first, created, err := facade.Assign(context.Background(), "discovery_feed_v3", "persona-1")
	if err != nil {
		t.Fatalf("assign experiment: %v", err)
	}
	if !created || first.SubjectKey != "persona-1" {
		t.Fatalf("unexpected first assignment: created=%v fact=%+v", created, first)
	}
	second, created, err := facade.Assign(context.Background(), "discovery_feed_v3", "persona-1")
	if err != nil {
		t.Fatalf("replay assignment: %v", err)
	}
	if created || second.Variant != first.Variant {
		t.Fatalf("assignment fact was not stable: created=%v first=%+v second=%+v", created, first, second)
	}
}
