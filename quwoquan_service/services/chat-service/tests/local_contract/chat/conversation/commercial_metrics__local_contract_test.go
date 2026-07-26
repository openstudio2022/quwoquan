package local_contract

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	_ "quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func TestChatCommercialMetricsAreRegistered(t *testing.T) {
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather chat metrics: %v", err)
	}
	required := map[string]bool{
		"chat_mention_command_total":              false,
		"chat_inbox_projection_event_lag_seconds": false,
	}
	for _, family := range families {
		if _, tracked := required[family.GetName()]; tracked {
			required[family.GetName()] = true
		}
	}
	for name, found := range required {
		if !found {
			t.Fatalf("commercial metric %q is not registered", name)
		}
	}
}
