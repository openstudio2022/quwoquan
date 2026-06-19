package messaging

import (
	"context"
	"encoding/json"
	"testing"
)

type postCountStoreSpy struct {
	deltas map[string]int64
}

func (s *postCountStoreSpy) IncrementPostCount(_ context.Context, id string, delta int64) error {
	if s.deltas == nil {
		s.deltas = map[string]int64{}
	}
	s.deltas[id] += delta
	return nil
}

func TestContentPostConsumerIncrementsOnPublished(t *testing.T) {
	store := &postCountStoreSpy{}
	consumer := NewContentPostConsumer(nil, store, nil)

	if err := consumer.ProcessMessage(context.Background(), ContentPostPublishedChannel, envelope("PostPublished", []string{"circle_1", "circle_2"})); err != nil {
		t.Fatalf("ProcessMessage: %v", err)
	}
	if store.deltas["circle_1"] != 1 || store.deltas["circle_2"] != 1 {
		t.Fatalf("deltas=%#v", store.deltas)
	}
}

func TestContentPostConsumerDecrementsOnDeleted(t *testing.T) {
	store := &postCountStoreSpy{}
	consumer := NewContentPostConsumer(nil, store, nil)

	if err := consumer.ProcessMessage(context.Background(), ContentPostDeletedChannel, envelope("PostDeleted", []string{"circle_1"})); err != nil {
		t.Fatalf("ProcessMessage: %v", err)
	}
	if store.deltas["circle_1"] != -1 {
		t.Fatalf("deltas=%#v", store.deltas)
	}
}

func TestContentPostConsumerIgnoresBlankCircleIDs(t *testing.T) {
	store := &postCountStoreSpy{}
	consumer := NewContentPostConsumer(nil, store, nil)

	if err := consumer.ProcessMessage(context.Background(), ContentPostPublishedChannel, envelope("PostPublished", []string{"", "  "})); err != nil {
		t.Fatalf("ProcessMessage: %v", err)
	}
	if len(store.deltas) != 0 {
		t.Fatalf("blank ids should be ignored: %#v", store.deltas)
	}
}

func TestContentPostConsumerAppliesSettingsDelta(t *testing.T) {
	store := &postCountStoreSpy{}
	consumer := NewContentPostConsumer(nil, store, nil)

	if err := consumer.ProcessMessage(context.Background(), ContentPostSettingsChannel, settingsEnvelope([]string{"circle_add"}, []string{"circle_remove"})); err != nil {
		t.Fatalf("ProcessMessage: %v", err)
	}
	if store.deltas["circle_add"] != 1 || store.deltas["circle_remove"] != -1 {
		t.Fatalf("deltas=%#v", store.deltas)
	}
}

func TestContentPostConsumerIgnoresDraftSettingsDelta(t *testing.T) {
	store := &postCountStoreSpy{}
	consumer := NewContentPostConsumer(nil, store, nil)

	if err := consumer.ProcessMessage(context.Background(), ContentPostSettingsChannel, settingsEnvelopeWithStatus("draft", []string{"circle_add"}, nil)); err != nil {
		t.Fatalf("ProcessMessage: %v", err)
	}
	if len(store.deltas) != 0 {
		t.Fatalf("draft settings should not affect post count: %#v", store.deltas)
	}
}

func envelope(eventType string, circleIDs []string) string {
	data, _ := json.Marshal(map[string]any{
		"payload": map[string]any{
			"type": eventType,
			"data": map[string]any{"status": "published", "circleIds": circleIDs},
		},
	})
	return string(data)
}

func settingsEnvelope(added []string, removed []string) string {
	return settingsEnvelopeWithStatus("published", added, removed)
}

func settingsEnvelopeWithStatus(status string, added []string, removed []string) string {
	data, _ := json.Marshal(map[string]any{
		"payload": map[string]any{
			"type": "PostSettingsUpdated",
			"data": map[string]any{
				"status":           status,
				"addedCircleIds":   added,
				"removedCircleIds": removed,
			},
		},
	})
	return string(data)
}
