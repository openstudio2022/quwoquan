package local_contract

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	experimentmessaging "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/messaging"
)

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t3
func TestExperimentPolicyPublisherUsesOnlyDurableObjectOwnedStream(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	publisher, err := experimentmessaging.NewPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	if err := publisher.Publish(ctx, runtimemessaging.DomainEvent{
		EventID: "experiment-policy-1", Type: "ExperimentPolicyActivated",
		AggregateType: "Experiment", AggregateID: "search_ranking",
		Payload: map[string]any{
			"id": "search_ranking", "key": "search_ranking", "version": float64(3),
			"status": "running",
			"variants": []any{
				map[string]any{"key": "control", "allocationBasisPoints": float64(5000)},
				map[string]any{"key": "term_heat", "allocationBasisPoints": float64(5000)},
			},
			"updatedAt": "2026-07-31T10:00:00Z",
		},
		OccurredAt: "2026-07-31T10:00:00Z",
	}); err != nil {
		t.Fatal(err)
	}
	if err := transport.EnsureDurableConsumerGroup(ctx, experimentmessaging.ExperimentPolicyActivatedStream, "local-contract", "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream: experimentmessaging.ExperimentPolicyActivatedStream,
		Group:  "local-contract", Consumer: "reader", Count: 1, Block: time.Millisecond,
	})
	if err != nil || len(messages) != 1 {
		t.Fatalf("durable policy messages=%d err=%v", len(messages), err)
	}
	values := map[string]string{}
	for _, field := range messages[0].Fields {
		values[field.Name] = field.Value
	}
	if values["eventId"] != "experiment-policy-1" || values["producer"] != "product-ops-service" {
		t.Fatalf("durable policy identity=%v", values)
	}
}
