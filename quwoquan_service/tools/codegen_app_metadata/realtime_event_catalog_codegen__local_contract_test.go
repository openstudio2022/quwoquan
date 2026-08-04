package main

import (
	"strings"
	"testing"
)

func TestRealtimeEventCatalogOwnsEveryClientWireType(t *testing.T) {
	initializeTestContractGraph(t)
	catalog, err := loadRealtimeEventCatalog()
	if err != nil {
		t.Fatal(err)
	}
	if err := validateRealtimeEventCatalog(catalog); err != nil {
		t.Fatal(err)
	}
	out, err := renderRealtimeEventCatalogDart(catalog)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"export 'chat_realtime_events.g.dart';",
		"export 'feed_realtime_patch.g.dart';",
		"export 'rtc_signal_payloads.g.dart';",
		"export 'shared_realtime_event_enums.g.dart';",
		"sealed class RealtimeEventEnvelope",
		"final class ChatRealtimeEventEnvelope",
		"final class RtcRealtimeEventEnvelope",
		"factory RealtimeEventEnvelope.fromWire",
		"decodeRealtimeEventEnvelope",
		"$path.payload must be an object",
		"Map<String, Object?> toWire()",
		"'MessageSent': 'chat.message'",
		"'call.ringing': 'rtc.call_session'",
		"'feed.patch': 'content.post'",
		"'sync_hint': 'user.user_account'",
		"throw FormatException('Unsupported realtime event type: $wireType')",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("generated realtime catalog missing %q", want)
		}
	}
}

func TestRealtimeEventCatalogRejectsDuplicateWireType(t *testing.T) {
	initializeTestContractGraph(t)
	catalog, err := loadRealtimeEventCatalog()
	if err != nil {
		t.Fatal(err)
	}
	catalog.Events = append(catalog.Events, catalog.Events[0])
	if err := validateRealtimeEventCatalog(catalog); err == nil || !strings.Contains(err.Error(), "multiple owners") {
		t.Fatalf("duplicate wire type error = %v", err)
	}
}
