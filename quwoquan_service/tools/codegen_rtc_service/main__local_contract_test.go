package main

import (
	"strings"
	"testing"
)

func TestRenderRealtimePayloadFieldsUsesClientEventMetadata(t *testing.T) {
	document := realtimeEventsFile{}
	document.Events = append(document.Events, struct {
		Name          string   `yaml:"name"`
		ClientWsType  string   `yaml:"client_ws_type"`
		PayloadFields []string `yaml:"payload_fields"`
	}{
		Name:          "CallAnswered",
		ClientWsType:  "call.answered",
		PayloadFields: []string{"callId", "userId"},
	})
	output, err := renderRealtimePayloadFields("rtc/rtc/call_session/events.yaml", document)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		`"call.answered": {`,
		`"callId"`,
		`"userId"`,
		"func ClientRealtimePayloadFieldNames",
	} {
		if !strings.Contains(output, expected) {
			t.Fatalf("generated RTC realtime field catalog missing %q", expected)
		}
	}
}

func TestRenderRealtimePayloadFieldsRejectsDuplicateWireType(t *testing.T) {
	document := realtimeEventsFile{}
	for _, name := range []string{"First", "Second"} {
		document.Events = append(document.Events, struct {
			Name          string   `yaml:"name"`
			ClientWsType  string   `yaml:"client_ws_type"`
			PayloadFields []string `yaml:"payload_fields"`
		}{Name: name, ClientWsType: "call.same", PayloadFields: []string{"callId"}})
	}
	if _, err := renderRealtimePayloadFields("events.yaml", document); err == nil {
		t.Fatal("duplicate RTC client wire type was accepted")
	}
}
