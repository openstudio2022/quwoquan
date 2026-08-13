package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
)

type recommendationSignalEventsDocument struct {
	Events []struct {
		Name              string   `yaml:"name"`
		DeliverySemantics string   `yaml:"delivery_semantics"`
		Topic             string   `yaml:"topic"`
		PayloadEntity     string   `yaml:"payload_entity"`
		PayloadFields     []string `yaml:"payload_fields"`
	} `yaml:"events"`
}

func TestSearchRecommendationSignalEventContract(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(
		root,
		"contracts/search/recommendation_signal_fact/events.yaml",
	))
	if err != nil {
		t.Fatalf("read recommendation_signal_fact events.yaml: %v", err)
	}
	var document recommendationSignalEventsDocument
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("unmarshal events.yaml: %v", err)
	}
	for _, event := range document.Events {
		if event.Name != "SearchRecommendationSignalPublished" {
			continue
		}
		if event.DeliverySemantics != "durable_stream" {
			t.Fatalf("delivery_semantics=%q want durable_stream", event.DeliverySemantics)
		}
		if event.Topic != searchsignals.StreamName {
			t.Fatalf(
				"topic=%q drifted from publisher stream %q",
				event.Topic,
				searchsignals.StreamName,
			)
		}
		if event.PayloadEntity != "RecommendationSignalFact" {
			t.Fatalf("payload_entity=%q", event.PayloadEntity)
		}
		required := map[string]bool{
			"signalId": true, "signalType": true,
			"searchRequestId": true, "sessionId": true, "userId": true,
			"normalizedQuery": true, "relatedTerms": true, "engagedObjectIds": true,
			"experimentBucket": true, "resultCount": true, "createdAt": true,
		}
		for _, field := range event.PayloadFields {
			delete(required, field)
		}
		if len(required) > 0 {
			t.Fatalf("missing payload fields: %v", required)
		}
		return
	}
	t.Fatal("SearchRecommendationSignalPublished event missing")
}
