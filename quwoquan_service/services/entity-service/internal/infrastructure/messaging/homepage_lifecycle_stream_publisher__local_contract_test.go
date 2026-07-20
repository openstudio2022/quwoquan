package messaging

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	homepageports "quwoquan_service/services/entity-service/internal/domain/homepage/ports"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	statusports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
)

func TestHomepageLifecyclePublishersPreserveDurableIdentity(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	occurredAt := time.Date(2026, 7, 20, 9, 30, 0, 0, time.UTC)
	payload, err := json.Marshal(map[string]any{"homepageId": "homepage-42"})
	if err != nil {
		t.Fatal(err)
	}

	if err := NewHomepageLifecycleStreamPublisher(client).Publish(
		ctx,
		homepageports.OutboxEvent{
			EventID:          "homepage-42:2:HomepagePublished",
			EventType:        "HomepagePublished",
			AggregateID:      "homepage-42",
			AggregateVersion: 2,
			Payload:          payload,
			OccurredAt:       occurredAt,
		},
	); err != nil {
		t.Fatalf("publish homepage event: %v", err)
	}
	if err := NewHomepageClaimLifecycleStreamPublisher(client).Publish(
		ctx,
		claimports.OutboxEvent{
			EventID:          "claim-7:2:HomepageClaimReviewed",
			EventType:        "HomepageClaimReviewed",
			AggregateID:      "claim-7",
			AggregateVersion: 2,
			Payload:          payload,
			OccurredAt:       occurredAt,
		},
	); err != nil {
		t.Fatalf("publish claim event: %v", err)
	}
	if err := NewHomepageStatusLifecycleStreamPublisher(client).Publish(
		ctx,
		statusports.OutboxEvent{
			EventID:          "report-9:2:HomepageStatusReportReviewed",
			EventType:        "HomepageStatusReportReviewed",
			AggregateID:      "report-9",
			AggregateVersion: 2,
			Payload:          payload,
			OccurredAt:       occurredAt,
		},
	); err != nil {
		t.Fatalf("publish status report event: %v", err)
	}

	const group = "homepage-lifecycle-contract"
	if err := client.XGroupCreateMkStream(
		ctx,
		HomepageLifecycleStream,
		group,
		"0",
	); err != nil {
		t.Fatal(err)
	}
	messages, err := client.XReadGroup(
		ctx,
		group,
		"test",
		map[string]string{HomepageLifecycleStream: ">"},
		3,
		0,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(messages) != 3 {
		t.Fatalf("messages=%d want=3", len(messages))
	}

	wantAggregateTypes := []string{
		"Homepage",
		"HomepageClaimRequest",
		"HomepageStatusReport",
	}
	for index, message := range messages {
		values := message.Values
		if values["aggregateType"] != wantAggregateTypes[index] {
			t.Fatalf(
				"message[%d] aggregateType=%q want=%q",
				index,
				values["aggregateType"],
				wantAggregateTypes[index],
			)
		}
		if values["aggregateVersion"] != "2" ||
			values["occurredAt"] != occurredAt.Format(time.RFC3339Nano) ||
			values["payload"] != string(payload) {
			t.Fatalf("message[%d] identity drift: %#v", index, values)
		}
	}
}

func TestHomepageLifecyclePublisherRejectsInvalidPayload(t *testing.T) {
	publisher := NewHomepageLifecycleStreamPublisher(rtredis.NewMemoryClient())
	err := publisher.Publish(
		context.Background(),
		homepageports.OutboxEvent{
			EventID:          "event-1",
			EventType:        "HomepagePublished",
			AggregateID:      "homepage-1",
			AggregateVersion: 1,
			Payload:          []byte("not-json"),
			OccurredAt:       time.Now().UTC(),
		},
	)
	if err == nil {
		t.Fatal("invalid payload must fail before XADD")
	}
}
