// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
package application_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	mediamessaging "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/messaging"
)

type mediaAssetOutboxFixture struct {
	event      mediaports.OutboxEvent
	checkpoint string
	saves      int
}

func (fixture *mediaAssetOutboxFixture) ReadMediaAssetOutboxAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]mediaports.OutboxEvent, error) {
	if checkpoint == fixture.event.Checkpoint {
		return nil, nil
	}
	return []mediaports.OutboxEvent{fixture.event}, nil
}

func (fixture *mediaAssetOutboxFixture) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return fixture.checkpoint, nil
}

func (fixture *mediaAssetOutboxFixture) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	fixture.checkpoint = checkpoint
	fixture.saves++
	return nil
}

type mediaAssetTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *mediaAssetTransportFixture) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *mediaAssetTransportFixture) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestMediaAssetOutboxRelayRetriesWithoutAdvancingCheckpoint(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 10, 0, 0, time.UTC)
	outbox := &mediaAssetOutboxFixture{event: mediaports.OutboxEvent{
		EventID: "media-1:1", EventType: "MediaAssetCreated",
		AggregateType: "MediaAsset", AggregateID: "media-1", AggregateVersion: 1,
		Payload: []byte(`{"assetId":"media-1","ownerId":"owner-1","sourceSessionId":"session-1",` +
			`"objectKey":"objects/media-1","sha256":"sha256:21d37dbf2b61bc06cc4d0f447e65753a3988c2e23061d185bc8ab16eb0183fea","processingStatus":"processing"}`),
		OccurredAt: now, Checkpoint: now.Format(time.RFC3339Nano) + "|media-1:1",
	}}
	transport := &mediaAssetTransportFixture{fail: true}
	publisher, err := mediamessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := mediaapp.NewMediaAssetOutboxRelay(
		outbox,
		outbox,
		publisher,
		"media-asset-stream-test",
	)
	if err != nil {
		t.Fatalf("NewMediaAssetOutboxRelay() error = %v", err)
	}

	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.saves != 0 || outbox.checkpoint != "" {
		t.Fatalf("failed publish advanced checkpoint: saves=%d checkpoint=%q", outbox.saves, outbox.checkpoint)
	}

	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.saves != 1 || outbox.checkpoint != outbox.event.Checkpoint ||
		transport.message.Stream != mediamessaging.MediaAssetEventStream ||
		fields["aggregateType"] != "MediaAsset" ||
		fields["eventId"] != outbox.event.EventID || transport.retention <= 0 {
		t.Fatalf("MediaAsset delivery mismatch: saves=%d checkpoint=%q stream=%q fields=%v retention=%s", outbox.saves, outbox.checkpoint, transport.message.Stream, fields, transport.retention)
	}
}

func TestMediaAssetPublisherEmitsExactCanonicalEventPayloads(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 10, 0, 0, time.UTC)
	tests := []struct {
		name, sourceType, canonicalType, payload, want string
	}{
		{
			name: "created", sourceType: "content.media_asset.created", canonicalType: "MediaAssetCreated",
			payload: `{"assetId":"media-1","ownerId":"owner-1","sourceSessionId":"session-1","objectKey":"objects/media-1","sha256":"sha256:21d37dbf2b61bc06cc4d0f447e65753a3988c2e23061d185bc8ab16eb0183fea","processingStatus":"processing","mimeType":"image/jpeg"}`,
			want:    `{"id":"media-1","version":7,"ownerId":"owner-1","sourceSessionId":"session-1","objectKey":"objects/media-1","sha256":"sha256:21d37dbf2b61bc06cc4d0f447e65753a3988c2e23061d185bc8ab16eb0183fea","processingStatus":"processing"}`,
		},
		{
			name: "processing", sourceType: "content.media_asset.processing_updated", canonicalType: "MediaAssetProcessingUpdated",
			payload: `{"assetId":"media-1","processingStatus":"ready","failureReason":""}`,
			want:    `{"id":"media-1","version":7,"processingStatus":"ready","processedAt":"2026-08-05T12:10:00Z"}`,
		},
		{
			name: "access policy", sourceType: "content.media_asset.access_policy_updated", canonicalType: "MediaAssetAccessPolicyUpdated",
			payload: `{"assetId":"media-1","ownerId":"owner-1","accessPolicy":"private"}`,
			want:    `{"id":"media-1","version":7,"ownerId":"owner-1","accessPolicy":"private"}`,
		},
		{
			name: "discarded", sourceType: "content.media_asset.discarded", canonicalType: "MediaAssetDiscarded",
			payload: `{"id":"media-1","version":7,"ownerId":"owner-1","objectKey":"objects/media-1","processingStatus":"deleted"}`,
			want:    `{"id":"media-1","version":7,"ownerId":"owner-1","objectKey":"objects/media-1","processingStatus":"deleted"}`,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			transport := &mediaAssetTransportFixture{}
			publisher, err := mediamessaging.NewEventPublisher(transport)
			if err != nil {
				t.Fatalf("NewEventPublisher() error = %v", err)
			}
			err = publisher.Publish(context.Background(), mediaports.OutboxEvent{
				EventID: "event-1", EventType: test.sourceType, AggregateType: "MediaAsset",
				AggregateID: "media-1", AggregateVersion: 7, Payload: []byte(test.payload),
				OccurredAt: now, Checkpoint: "checkpoint-1",
			})
			if err != nil {
				t.Fatalf("Publish() error = %v", err)
			}
			fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
			if fields["eventType"] != test.canonicalType {
				t.Fatalf("eventType = %q, want %q", fields["eventType"], test.canonicalType)
			}
			assertCanonicalJSON(t, fields["payload"], test.want)
		})
	}
}

func assertCanonicalJSON(t *testing.T, got, want string) {
	t.Helper()
	decode := func(raw string) any {
		decoder := json.NewDecoder(bytes.NewBufferString(raw))
		decoder.UseNumber()
		var value any
		if err := decoder.Decode(&value); err != nil {
			t.Fatalf("decode JSON %q: %v", raw, err)
		}
		return value
	}
	if gotValue, wantValue := decode(got), decode(want); !reflect.DeepEqual(gotValue, wantValue) {
		t.Fatalf("payload = %s, want %s", got, want)
	}
}
