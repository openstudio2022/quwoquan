// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t3
// readiness_case: apply-search-experiment-policy-api
package api_integration

import (
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	consumer "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/experimentpolicy"
)

func TestExperimentPolicyConsumerPersistsRealMongoPolicyAndAcknowledges(t *testing.T) {
	cleanSearchCollections(t)
	store, err := experimentpolicy.NewMongoStore(mongoDB)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	experiments, err := application.NewExperiments(testAssignmentPublisher{})
	if err != nil {
		t.Fatal(err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransport(
		realRedisClient,
		realRedisClient,
	)
	if err != nil {
		t.Fatal(err)
	}
	runner, err := consumer.NewExperimentPolicyConsumer(
		transport, store, experiments, "search-experiment-policy-api", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := transport.AppendDurable(t.Context(), runtimemessaging.DurableMessage{
		Stream: consumer.ExperimentPolicyStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "search-policy-api-4"},
			{Name: "eventType", Value: "ExperimentPolicyActivated"},
			{Name: "producer", Value: "product-ops-service"},
			{Name: "aggregateType", Value: "Experiment"},
			{Name: "experimentId", Value: application.SearchRankingExperimentID},
			{Name: "payloadJson", Value: `{"id":"search_ranking","version":4,"status":"running","variants":[{"key":"control","allocationBasisPoints":5000},{"key":"term_heat","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"},"updatedAt":"2026-08-05T09:00:00Z"}`},
		},
	}); err != nil {
		t.Fatal(err)
	}
	processed, err := runner.ProcessOnce(t.Context())
	if err != nil || processed != 1 {
		t.Fatalf("ProcessOnce() processed=%d err=%v", processed, err)
	}
	pending, err := realRedisClient.XPendingCount(
		t.Context(), consumer.ExperimentPolicyStream, consumer.ExperimentPolicyConsumerGroup,
	)
	if err != nil || pending != 0 {
		t.Fatalf("pending=%d err=%v, want acknowledged source event", pending, err)
	}
	stored, found, err := store.Load(t.Context(), application.SearchRankingExperimentID)
	if err != nil || !found || stored.Revision != 4 {
		t.Fatalf("stored=%+v found=%v err=%v", stored, found, err)
	}
	assignment, err := experiments.Assign(t.Context(), "persona:search-api-policy")
	if err != nil || assignment == "" {
		t.Fatalf("assignment=%+v err=%v", assignment, err)
	}
}
