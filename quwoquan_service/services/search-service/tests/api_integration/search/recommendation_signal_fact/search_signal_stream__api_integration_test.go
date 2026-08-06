// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: append-recommendation-signal-api
package api_integration

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
)

func TestRecommendationSignalUsesRealRedisAndTrimsActiveStreamByAge(
	t *testing.T,
) {
	ctx := context.Background()
	if err := realRedisClient.Del(ctx, searchsignals.StreamName); err != nil {
		t.Fatalf("clear signal stream: %v", err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransport(
		realRedisClient,
		realRedisClient,
	)
	if err != nil {
		t.Fatalf("create Redis message transport: %v", err)
	}
	publisher, err := searchsignals.NewStreamPublisher(transport, nil)
	if err != nil {
		t.Fatalf("create signal publisher: %v", err)
	}
	appender, err := signalapplication.NewAppender(publisher)
	if err != nil {
		t.Fatalf("create recommendation signal appender: %v", err)
	}
	if err := appender.Append(ctx, signalapplication.Signal{
		SignalID:        "query:request-old",
		SignalType:      "query",
		SearchRequestID: "request-old",
		UserID:          "persona-1",
		NormalizedQuery: "成都 火锅",
		RelatedTerms:    []string{"成都", "火锅"},
		ResultCount:     4,
		CreatedAt:       time.Now().UTC(),
	}); err != nil {
		t.Fatalf("publish old query signal: %v", err)
	}
	time.Sleep(250 * time.Millisecond)
	if err := appender.Append(ctx, signalapplication.Signal{
		SignalID:         "feedback:click-recent",
		SignalType:       "click",
		SearchRequestID:  "request-recent",
		UserID:           "persona-1",
		EngagedObjectIDs: []string{"post-1"},
		CreatedAt:        time.Now().UTC(),
	}); err != nil {
		t.Fatalf("publish recent click signal: %v", err)
	}

	if err := transport.SetDurableRetention(
		ctx,
		searchsignals.StreamName,
		100*time.Millisecond,
	); err != nil {
		t.Fatalf("trim active signal stream: %v", err)
	}
	if err := transport.EnsureDurableConsumerGroup(
		ctx,
		searchsignals.StreamName,
		"retention-audit",
		"0",
	); err != nil {
		t.Fatalf("create retention audit group: %v", err)
	}
	deliveries, err := transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   searchsignals.StreamName,
			Group:    "retention-audit",
			Consumer: "audit-1",
			Count:    10,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil {
		t.Fatalf("read retained signals: %v", err)
	}
	if len(deliveries) != 1 {
		t.Fatalf(
			"retained signal count=%d want=1 deliveries=%+v",
			len(deliveries),
			deliveries,
		)
	}
	values := durableValues(deliveries[0].Fields)
	if values["signalId"] != "feedback:click-recent" ||
		values["signalType"] != "click" ||
		values["engagedObjectIds"] != `["post-1"]` {
		t.Fatalf("retained signal=%#v", values)
	}
	if values["normalizedQuery"] != "" || values["relatedTerms"] != "[]" {
		t.Fatalf("click signal leaked query content: %#v", values)
	}
}

func durableValues(
	fields []runtimemessaging.DurableField,
) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}
