package local_contract

import (
	"context"
	"strconv"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	experimentports "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
	assignmentstream "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/stream"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

func TestAssignmentObservedConsumerProjectsCanonicalFactAndRejectsUnauthorizedProducer(t *testing.T) {
	ctx := context.Background()
	redisClient := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redisClient, redisClient)
	if err != nil {
		t.Fatal(err)
	}
	store := newAssignmentStore()
	facade, err := assignmentapp.NewFacade(store, store, store)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := assignmentstream.NewConsumer(transport, facade, "local-contract", nil)
	if err != nil {
		t.Fatal(err)
	}
	assignedAt := time.Date(2026, time.July, 31, 10, 0, 0, 0, time.UTC)
	expected, err := store.experiment.Assign("persona:observed", assignedAt)
	if err != nil {
		t.Fatal(err)
	}
	appendAssignmentMessage(t, ctx, transport, "event-valid", "search-service", expected, assignedAt)
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 || store.count() != 1 {
		t.Fatalf("valid observation processed=%d facts=%d err=%v", processed, store.count(), err)
	}

	appendAssignmentMessage(t, ctx, transport, "event-invalid", "app-client", expected, assignedAt)
	processed, err = consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 || store.count() != 1 {
		t.Fatalf("unauthorized producer processed=%d facts=%d err=%v", processed, store.count(), err)
	}
}

func appendAssignmentMessage(
	t *testing.T,
	ctx context.Context,
	transport runtimemessaging.MessageTransport,
	eventID string,
	producer string,
	fact assignmentdomain.Fact,
	assignedAt time.Time,
) {
	t.Helper()
	_, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: assignmentstream.AssignmentObservedStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventType", Value: "ExperimentAssignmentObserved"},
			{Name: "eventId", Value: eventID},
			{Name: "producer", Value: producer},
			{Name: "experimentId", Value: fact.ExperimentID},
			{Name: "experimentRevision", Value: strconv.FormatInt(fact.ExperimentRevision, 10)},
			{Name: "subjectKey", Value: fact.SubjectKey},
			{Name: "variant", Value: fact.Variant},
			{Name: "assignedAt", Value: assignedAt.Format(time.RFC3339Nano)},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
}

type assignmentStore struct {
	mu          sync.Mutex
	experiment  experimentmodel.Experiment
	assignments map[string]assignmentdomain.Fact
}

func newAssignmentStore() *assignmentStore {
	return &assignmentStore{
		experiment: experimentmodel.Experiment{
			ID: "search_ranking", Key: "search_ranking", Version: 7, Status: "running",
			AudienceRule: experimentmodel.AudienceRule{Kind: "all"},
			Variants: []experimentmodel.Variant{
				{Key: "control", AllocationBasisPoints: 5000},
				{Key: "term_heat", AllocationBasisPoints: 5000},
			},
			CreatedAt: "2026-07-31T09:00:00Z", UpdatedAt: "2026-07-31T09:00:00Z",
		},
		assignments: map[string]assignmentdomain.Fact{},
	}
}

func (s *assignmentStore) Load(context.Context, string) (experimentmodel.Experiment, error) {
	return s.experiment, nil
}

func (s *assignmentStore) LoadRevision(_ context.Context, id string, revision int64) (experimentmodel.Experiment, error) {
	if id != s.experiment.ID || revision != s.experiment.Version {
		return experimentmodel.Experiment{}, experimentmodel.ErrNotFound
	}
	return s.experiment, nil
}

func (*assignmentStore) Replay(context.Context, string, string, string) (experimentports.CommitReceipt, bool, error) {
	return experimentports.CommitReceipt{}, false, nil
}

func (*assignmentStore) Commit(context.Context, int64, experimentports.ChangeSet) (experimentports.CommitReceipt, error) {
	return experimentports.CommitReceipt{}, nil
}

func (s *assignmentStore) Append(_ context.Context, fact assignmentdomain.Fact) (assignmentdomain.Fact, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := fact.ExperimentID + "\x00" + strconv.FormatInt(fact.ExperimentRevision, 10) + "\x00" + fact.SubjectKey
	if existing, ok := s.assignments[key]; ok {
		return existing, false, nil
	}
	s.assignments[key] = fact
	return fact, true, nil
}

func (s *assignmentStore) Get(_ context.Context, experimentID string, revision int64, subjectKey string) (assignmentdomain.Fact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	fact, ok := s.assignments[experimentID+"\x00"+strconv.FormatInt(revision, 10)+"\x00"+subjectKey]
	if !ok {
		return assignmentdomain.Fact{}, assignmentdomain.ErrNotFound
	}
	return fact, nil
}

func (s *assignmentStore) Stats(context.Context, string, int64) (assignmentdomain.Stats, error) {
	return assignmentdomain.Stats{}, nil
}

func (s *assignmentStore) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.assignments)
}

var (
	_ experimentports.AggregateStore = (*assignmentStore)(nil)
	_ assignmentapp.Sink             = (*assignmentStore)(nil)
	_ assignmentapp.Reader           = (*assignmentStore)(nil)
)
