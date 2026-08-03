package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	ports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
	projectionmessaging "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/messaging"
)

func TestUserProfileTagConsumerAppliesAndAcknowledgesTypedProjection(
	t *testing.T,
) {
	payload, err := json.Marshal(map[string]any{
		"userId":            "user-1",
		"tagRefs":           []string{"Audience/用户/兴趣偏好/科技/AI"},
		"taxonomyReleaseId": "taxonomy-release-1",
		"profileVersion":    3,
		"occurredAt":        "2026-07-24T10:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	transport := &profileTagTransportFake{
		fresh: []runtimemessaging.StreamDelivery{{
			ID: "100-1",
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: "profile-tags-event-1"},
				{Name: "eventName", Value: "UserProfileTagsChanged"},
				{Name: "accountId", Value: "user-1"},
				{Name: "accountVersion", Value: "3"},
				{Name: "payload", Value: string(payload)},
				{Name: "occurredAt", Value: "2026-07-24T10:00:00Z"},
			},
		}},
	}
	projector := &profileTagProjectorFake{}
	consumer, err := projectionmessaging.NewUserProfileTagConsumer(
		transport,
		projector,
		"tag-consumer-test",
		nil,
	)
	if err != nil {
		t.Fatalf("construct consumer: %v", err)
	}
	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("process typed projection: %v", err)
	}
	if processed != 1 || projector.calls != 1 {
		t.Fatalf("processed=%d projector calls=%d", processed, projector.calls)
	}
	if projector.last.UserID != "user-1" ||
		projector.last.ProfileVersion != 3 ||
		projector.last.TaxonomyReleaseID != "taxonomy-release-1" ||
		len(projector.last.TagRefs) != 1 {
		t.Fatalf("unexpected projection: %#v", projector.last)
	}
	if len(transport.acked) != 1 || transport.acked[0] != "100-1" {
		t.Fatalf("projection was not acknowledged: %#v", transport.acked)
	}
}

func TestUserProfileTagConsumerQuarantinesMalformedEventWithoutRawPayload(
	t *testing.T,
) {
	transport := &profileTagTransportFake{
		fresh: []runtimemessaging.StreamDelivery{{
			ID: "100-2",
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: "malformed-event-id"},
				{Name: "eventName", Value: "UserProfileTagsChanged"},
				{Name: "accountId", Value: "user-1"},
				{Name: "accountVersion", Value: "3"},
				{Name: "payload", Value: "{"},
			},
		}},
	}
	consumer, err := projectionmessaging.NewUserProfileTagConsumer(
		transport,
		&profileTagProjectorFake{},
		"tag-consumer-test",
		nil,
	)
	if err != nil {
		t.Fatalf("construct consumer: %v", err)
	}
	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("quarantine malformed projection: %v", err)
	}
	if processed != 1 || len(transport.acked) != 1 ||
		len(transport.deadLetters) != 1 {
		t.Fatalf(
			"processed=%d acked=%#v deadLetters=%#v",
			processed,
			transport.acked,
			transport.deadLetters,
		)
	}
	for _, field := range transport.deadLetters[0].Fields {
		if field.Name == "payload" || field.Value == "{" ||
			field.Value == "malformed-event-id" {
			t.Fatalf("DLQ leaked raw event data: %#v", transport.deadLetters[0])
		}
	}
	if transport.retention != 30*24*time.Hour {
		t.Fatalf("DLQ retention=%s", transport.retention)
	}
}

func TestUserProfileTagConsumerLeavesTransientProjectionFailurePending(
	t *testing.T,
) {
	payload, err := json.Marshal(map[string]any{
		"userId":            "user-1",
		"tagRefs":           []string{"Audience/用户/兴趣偏好/科技/AI"},
		"taxonomyReleaseId": "taxonomy-release-1",
		"profileVersion":    3,
		"occurredAt":        "2026-07-24T10:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	transport := &profileTagTransportFake{
		fresh: []runtimemessaging.StreamDelivery{{
			ID: "100-3",
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: "profile-tags-event-3"},
				{Name: "eventName", Value: "UserProfileTagsChanged"},
				{Name: "accountId", Value: "user-1"},
				{Name: "accountVersion", Value: "3"},
				{Name: "payload", Value: string(payload)},
			},
		}},
	}
	consumer, err := projectionmessaging.NewUserProfileTagConsumer(
		transport,
		&profileTagProjectorFake{err: errors.New("mongo unavailable")},
		"tag-consumer-test",
		nil,
	)
	if err != nil {
		t.Fatalf("construct consumer: %v", err)
	}
	processed, err := consumer.ProcessOnce(context.Background())
	if err == nil || processed != 0 {
		t.Fatalf("processed=%d err=%v, want retryable failure", processed, err)
	}
	if len(transport.acked) != 0 || len(transport.deadLetters) != 0 {
		t.Fatalf(
			"transient failure was acknowledged or quarantined: acked=%#v dlq=%#v",
			transport.acked,
			transport.deadLetters,
		)
	}
}

type profileTagTransportFake struct {
	fresh       []runtimemessaging.StreamDelivery
	acked       []string
	deadLetters []runtimemessaging.DeadLetterMessage
	retention   time.Duration
}

func (*profileTagTransportFake) PublishEphemeral(
	context.Context,
	runtimemessaging.EphemeralMessage,
) error {
	return nil
}

func (*profileTagTransportFake) SubscribeEphemeral(
	context.Context,
	...string,
) (runtimemessaging.EphemeralSubscription, error) {
	return nil, nil
}

func (*profileTagTransportFake) AppendDurable(
	context.Context,
	runtimemessaging.DurableMessage,
) (string, error) {
	return "1-0", nil
}

func (*profileTagTransportFake) EnsureDurableConsumerGroup(
	context.Context,
	string,
	string,
	string,
) error {
	return nil
}

func (transport *profileTagTransportFake) ReadDurable(
	context.Context,
	runtimemessaging.StreamReadRequest,
) ([]runtimemessaging.StreamDelivery, error) {
	fresh := transport.fresh
	transport.fresh = nil
	return fresh, nil
}

func (transport *profileTagTransportFake) AckDurable(
	_ context.Context,
	_ string,
	_ string,
	ids ...string,
) error {
	transport.acked = append(transport.acked, ids...)
	return nil
}

func (*profileTagTransportFake) ReclaimDurable(
	context.Context,
	string,
	string,
	string,
	time.Duration,
	string,
	int64,
) ([]runtimemessaging.StreamDelivery, string, error) {
	return nil, "0-0", nil
}

func (transport *profileTagTransportFake) PublishDeadLetter(
	_ context.Context,
	message runtimemessaging.DeadLetterMessage,
) (string, error) {
	transport.deadLetters = append(transport.deadLetters, message)
	return "2-0", nil
}

func (*profileTagTransportFake) ClaimDurableDelivery(
	context.Context,
	string,
	string,
	time.Duration,
) (bool, error) {
	return true, nil
}

func (*profileTagTransportFake) ReleaseDurableDelivery(
	context.Context,
	string,
) error {
	return nil
}

func (transport *profileTagTransportFake) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	transport.retention = retention
	return nil
}

type profileTagProjectorFake struct {
	calls int
	last  ports.UserProfileTagProjection
	err   error
}

func (projector *profileTagProjectorFake) ApplyUserProfileTagProjection(
	_ context.Context,
	projection ports.UserProfileTagProjection,
) (bool, error) {
	projector.calls++
	projector.last = projection
	return projector.err == nil, projector.err
}
