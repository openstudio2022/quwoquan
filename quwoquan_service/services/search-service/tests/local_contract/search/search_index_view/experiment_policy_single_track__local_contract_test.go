package local_contract

import (
	"context"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	experimentpolicymq "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/experimentassignment"
)

func TestSearchExperimentPolicyProjectsAndPublishesObservedAssignment(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	publisher, err := experimentassignment.NewPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	experiments, err := application.NewExperiments(publisher)
	if err != nil {
		t.Fatal(err)
	}
	repository := &policyRepository{}
	consumer, err := experimentpolicymq.NewExperimentPolicyConsumer(
		transport, repository, experiments, "local-contract", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: experimentpolicymq.ExperimentPolicyStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "experiment-policy-search-4"},
			{Name: "eventType", Value: "ExperimentPolicyActivated"},
			{Name: "producer", Value: "product-ops-service"},
			{Name: "aggregateType", Value: "Experiment"},
			{Name: "experimentId", Value: application.SearchRankingExperimentID},
			{Name: "payloadJson", Value: `{"id":"search_ranking","version":4,"status":"running","variants":[{"key":"control","allocationBasisPoints":5000},{"key":"term_heat","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"},"updatedAt":"2026-07-31T10:00:00Z"}`},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	processed, err := consumer.ProcessOnce(ctx)
	if err != nil || processed != 1 || repository.current.Revision != 4 {
		t.Fatalf("policy projection processed=%d policy=%+v err=%v", processed, repository.current, err)
	}
	if _, err := experiments.Assign(ctx, "persona:search-local-contract"); err != nil {
		t.Fatalf("Assign() error = %v", err)
	}
	if err := transport.EnsureDurableConsumerGroup(ctx, experimentassignment.StreamName, "assignment-reader", "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream: experimentassignment.StreamName, Group: "assignment-reader",
		Consumer: "reader", Count: 1, Block: time.Millisecond,
	})
	if err != nil || len(messages) != 1 {
		t.Fatalf("assignment observations=%d err=%v", len(messages), err)
	}
	values := map[string]string{}
	for _, field := range messages[0].Fields {
		values[field.Name] = field.Value
	}
	if values["producer"] != "search-service" || values["experimentRevision"] != "4" || values["variant"] == "" {
		t.Fatalf("assignment observation=%v", values)
	}
}

type policyRepository struct {
	mu      sync.Mutex
	current application.ExperimentPolicy
}

func (r *policyRepository) Apply(
	_ context.Context,
	policy application.ExperimentPolicy,
) (application.ExperimentPolicy, bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	canonical, err := application.CanonicalExperimentPolicy(policy)
	if err != nil {
		return application.ExperimentPolicy{}, false, err
	}
	if r.current.Revision >= canonical.Revision {
		return r.current, false, nil
	}
	r.current = canonical
	return canonical, true, nil
}
