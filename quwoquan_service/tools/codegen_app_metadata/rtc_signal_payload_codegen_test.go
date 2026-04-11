package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRtcSignalPayloadGeneration_containsAllEventPayloadClasses(t *testing.T) {
	eventsPath := filepath.Join("..", "..", "contracts", "metadata", "rtc", "call_session", "events.yaml")
	fieldsPath := filepath.Join("..", "..", "contracts", "metadata", "rtc", "call_session", "fields.yaml")
	ff, err := readFields(fieldsPath)
	if err != nil {
		t.Fatal(err)
	}
	ev, err := readRtcEvents(eventsPath)
	if err != nil {
		t.Fatal(err)
	}
	out := renderRtcSignalPayloadsDart(eventsPath, ff, ev)
	for i := range ev.Events {
		name := ev.Events[i].Name
		wantPayload := "class Rtc" + name + "Payload"
		wantWs := "Rtc" + name + "WsPayload extends RtcWsPayload"
		if !strings.Contains(out, wantPayload) {
			t.Errorf("missing %s", wantPayload)
		}
		if !strings.Contains(out, wantWs) {
			t.Errorf("missing %s", wantWs)
		}
	}
	if !strings.Contains(out, "sealed class RtcWsPayload") {
		t.Error("missing sealed RtcWsPayload")
	}
	if !strings.Contains(out, "parseRtcWsPayload") {
		t.Error("missing parseRtcWsPayload")
	}
	if !strings.Contains(out, "RtcWsUnknownPayload") {
		t.Error("missing RtcWsUnknownPayload")
	}
}
