package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	experimenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/adapters/inbound"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	experimentports "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
)

func TestExperimentAssignmentHTTPBoundaryRejectsPublicWriteAndReadsObservedFact(t *testing.T) {
	store := newLocalExperimentStore()
	facade, err := experimentapp.NewFacade(store, store, store, store)
	if err != nil {
		t.Fatalf("build experiment facade: %v", err)
	}
	handler, err := experimenthttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("build experiment handler: %v", err)
	}
	path := "/ops/experiments/discovery_feed/assignment"

	spoofed := requestWithPersona(http.MethodPost, path, []byte(`{"subjectKey":"persona:attacker"}`))
	spoofedResponse := httptest.NewRecorder()
	handler.ServeHTTP(spoofedResponse, spoofed)
	if spoofedResponse.Code != http.StatusBadRequest {
		t.Fatalf("public assignment write status=%d body=%s", spoofedResponse.Code, spoofedResponse.Body.String())
	}
	if got := store.assignmentCount(); got != 0 {
		t.Fatalf("public assignment write stored %d facts, want 0", got)
	}

	observedAt := time.Date(2026, time.July, 14, 10, 0, 0, 0, time.UTC)
	expected, err := store.experiment.Assign("persona:persona-local-contract", observedAt)
	if err != nil {
		t.Fatalf("derive canonical assignment: %v", err)
	}
	observation := assignmentapp.AssignmentObservation{
		ExperimentID: store.experiment.ID, ExperimentRevision: store.experiment.Version,
		SubjectKey: expected.SubjectKey, Variant: expected.Variant, ObservedAt: observedAt,
	}
	first, inserted, err := facade.AssignmentFacts().AppendObserved(context.Background(), observation)
	if err != nil || !inserted {
		t.Fatalf("append observed assignment: inserted=%v fact=%+v err=%v", inserted, first, err)
	}
	replayed, inserted, err := facade.AssignmentFacts().AppendObserved(context.Background(), observation)
	if err != nil || inserted || replayed != first {
		t.Fatalf("replay observed assignment: inserted=%v first=%+v replay=%+v err=%v", inserted, first, replayed, err)
	}
	if got := store.assignmentCount(); got != 1 {
		t.Fatalf("observed assignment replay stored %d facts, want 1", got)
	}

	readResponse := httptest.NewRecorder()
	handler.ServeHTTP(readResponse, requestWithPersona(http.MethodGet, path, nil))
	if readResponse.Code != http.StatusOK {
		t.Fatalf("read observed assignment status=%d body=%s", readResponse.Code, readResponse.Body.String())
	}
	var read experimentmodel.AssignmentFact
	decodeLocalResponse(t, readResponse, &read)
	if read != first {
		t.Fatalf("read observed assignment=%+v, want %+v", read, first)
	}

	unauthorizedResponse := httptest.NewRecorder()
	handler.ServeHTTP(unauthorizedResponse, httptest.NewRequest(http.MethodGet, path, nil))
	if unauthorizedResponse.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted assignment read status=%d body=%s", unauthorizedResponse.Code, unauthorizedResponse.Body.String())
	}
}

func requestWithPersona(method, path string, body []byte) *http.Request {
	request := httptest.NewRequest(method, path, bytes.NewReader(body))
	principal := rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "persona-local-contract"},
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

func decodeLocalResponse(t *testing.T, recorder *httptest.ResponseRecorder, target any) {
	t.Helper()
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response %s: %v", recorder.Body.String(), err)
	}
}

type localExperimentStore struct {
	mu          sync.Mutex
	experiment  experimentmodel.Experiment
	assignments map[string]experimentmodel.AssignmentFact
}

func newLocalExperimentStore() *localExperimentStore {
	return &localExperimentStore{
		experiment: experimentmodel.Experiment{
			ID: "discovery_feed", Key: "discovery_feed", Version: 1,
			Status:       "running",
			AudienceRule: experimentmodel.AudienceRule{Kind: "all"},
			Variants: []experimentmodel.Variant{
				{Key: "control", AllocationBasisPoints: 5000},
				{Key: "treatment", AllocationBasisPoints: 5000},
			},
			CreatedAt: "2026-07-14T00:00:00Z", UpdatedAt: "2026-07-14T00:00:00Z",
		},
		assignments: map[string]experimentmodel.AssignmentFact{},
	}
}

func (s *localExperimentStore) Load(_ context.Context, id string) (experimentmodel.Experiment, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if id != s.experiment.ID {
		return experimentmodel.Experiment{}, experimentmodel.ErrNotFound
	}
	return s.experiment, nil
}

func (s *localExperimentStore) LoadRevision(
	ctx context.Context,
	id string,
	revision int64,
) (experimentmodel.Experiment, error) {
	experiment, err := s.Load(ctx, id)
	if err != nil || experiment.Version != revision {
		return experimentmodel.Experiment{}, experimentmodel.ErrNotFound
	}
	return experiment, nil
}

func (s *localExperimentStore) Replay(context.Context, string, string, string) (experimentports.CommitReceipt, bool, error) {
	return experimentports.CommitReceipt{}, false, nil
}

func (s *localExperimentStore) Commit(context.Context, int64, experimentports.ChangeSet) (experimentports.CommitReceipt, error) {
	return experimentports.CommitReceipt{}, nil
}

func (s *localExperimentStore) List(context.Context) ([]experimentmodel.Experiment, error) {
	return []experimentmodel.Experiment{s.experiment}, nil
}

func (s *localExperimentStore) Append(
	_ context.Context,
	fact experimentmodel.AssignmentFact,
) (experimentmodel.AssignmentFact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := fact.ExperimentID + "\x00" + strconv.FormatInt(fact.ExperimentRevision, 10) + "\x00" + fact.SubjectKey
	if existing, found := s.assignments[key]; found {
		return existing, false, nil
	}
	s.assignments[key] = fact
	return fact, true, nil
}

func (s *localExperimentStore) Get(
	_ context.Context,
	experimentID string,
	experimentRevision int64,
	subjectKey string,
) (experimentmodel.AssignmentFact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := experimentID + "\x00" + strconv.FormatInt(experimentRevision, 10) + "\x00" + subjectKey
	fact, found := s.assignments[key]
	if !found {
		return experimentmodel.AssignmentFact{}, experimentmodel.ErrAssignmentNotFound
	}
	return fact, nil
}

func (s *localExperimentStore) Stats(
	_ context.Context,
	experimentID string,
	experimentRevision int64,
) (experimentports.AssignmentStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	stats := experimentports.AssignmentStats{VariantCounts: map[string]int{}}
	for _, fact := range s.assignments {
		if fact.ExperimentID == experimentID && fact.ExperimentRevision == experimentRevision {
			stats.VariantCounts[fact.Variant]++
			stats.AssignedSubjects++
		}
	}
	return stats, nil
}

func (s *localExperimentStore) assignmentCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.assignments)
}

var (
	_ experimentports.AggregateStore   = (*localExperimentStore)(nil)
	_ experimentports.CatalogReader    = (*localExperimentStore)(nil)
	_ experimentports.AssignmentSink   = (*localExperimentStore)(nil)
	_ experimentports.AssignmentReader = (*localExperimentStore)(nil)
)
