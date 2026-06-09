package application

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

// TestSignalWireType_MatchesEventsYAML asserts that the domain-event -> wire-type
// map stays in lockstep with contracts/metadata/rtc/call_session/events.yaml.
//
// This guards SIT5 / media-infrastructure GWT1: events.yaml is the single source
// of truth for the WS wire protocol, and the rtc-service push must emit the same
// `client_ws_type` strings the Dart client (parseRtcWsPayload) switches on.
func TestSignalWireType_MatchesEventsYAML(t *testing.T) {
	path := locateEventsYAML(t)

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read events.yaml: %v", err)
	}

	var parsed struct {
		Events []struct {
			Name         string `yaml:"name"`
			ClientWsType string `yaml:"client_ws_type"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(raw, &parsed); err != nil {
		t.Fatalf("parse events.yaml: %v", err)
	}

	if len(parsed.Events) == 0 {
		t.Fatal("events.yaml declared no events")
	}

	seen := make(map[string]bool, len(parsed.Events))
	for _, e := range parsed.Events {
		if e.ClientWsType == "" {
			t.Errorf("event %q missing client_ws_type in events.yaml", e.Name)
			continue
		}
		seen[e.Name] = true
		got := signalWireType(e.Name)
		if got != e.ClientWsType {
			t.Errorf("signalWireType(%q) = %q, want %q (events.yaml client_ws_type)",
				e.Name, got, e.ClientWsType)
		}
	}

	// Every entry in the map must correspond to a real event in events.yaml,
	// so the table cannot drift ahead of the contract.
	for domainEvent := range signalWireTypeByDomainEvent {
		if !seen[domainEvent] {
			t.Errorf("signalWireTypeByDomainEvent has %q not present in events.yaml", domainEvent)
		}
	}
}

func locateEventsYAML(t *testing.T) string {
	t.Helper()
	// Walk up from the package dir to the repo root and resolve the contract path.
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for i := 0; i < 8; i++ {
		candidate := filepath.Join(dir, "contracts", "metadata", "rtc", "call_session", "events.yaml")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
		dir = filepath.Dir(dir)
	}
	t.Fatal("could not locate contracts/metadata/rtc/call_session/events.yaml")
	return ""
}
