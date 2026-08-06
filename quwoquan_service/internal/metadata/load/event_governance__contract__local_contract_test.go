package load

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestEventGovernanceLoadsCanonicalIdentityInputsWithoutProducerConsumers(t *testing.T) {
	metadataDir := t.TempDir()
	objectDir := filepath.Join(metadataDir, "rtc", "rtc", "call_session")
	if err := os.MkdirAll(objectDir, 0o755); err != nil {
		t.Fatal(err)
	}
	const document = `events:
- name: CallRinging
  delivery_semantics: transactional_outbox
  topic: events.rtc.call_ringing
  payload_entity: CallEventPayload
  payload_shape: exact
  payload_fields: [eventId, callId, callType]
  client_ws_type: call.ringing
  client_payload_defaults:
    callType: audio
  no_consumer_reason: awaiting a canonical runtime consumer edge
`
	if err := os.WriteFile(filepath.Join(objectDir, "events.yaml"), []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}

	events, err := loadEventsGovernance(
		metadataDir,
		objectDir,
		ast.Object{ID: "rtc.call_session"},
	)
	if err != nil {
		t.Fatalf("load events governance: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("loaded %d events, want 1", len(events))
	}
	got := events[0]
	if got.ObjectID != "rtc.call_session" || got.Name != "CallRinging" ||
		got.DeliverySemantics != "transactional_outbox" ||
		got.Topic != "events.rtc.call_ringing" ||
		got.PayloadEntity != "CallEventPayload" || got.PayloadShape != "exact" ||
		got.ClientWSType != "call.ringing" ||
		got.NoConsumerReason != "awaiting a canonical runtime consumer edge" {
		t.Fatalf("unexpected canonical event view: %+v", got)
	}
	if !reflect.DeepEqual(got.PayloadFields, []string{"eventId", "callId", "callType"}) {
		t.Fatalf("payload fields = %#v", got.PayloadFields)
	}
	if !reflect.DeepEqual(got.ClientPayloadDefaults, map[string]string{"callType": "audio"}) {
		t.Fatalf("client payload defaults = %#v", got.ClientPayloadDefaults)
	}
	if got.SourcePath != "rtc/rtc/call_session/events.yaml" {
		t.Fatalf("source path = %q", got.SourcePath)
	}
}
