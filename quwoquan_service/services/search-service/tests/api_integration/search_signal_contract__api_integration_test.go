package api_integration

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type searchEventsMeta struct {
	Events []struct {
		Name          string   `yaml:"name"`
		Producer      string   `yaml:"producer"`
		Consumers     []string `yaml:"consumers"`
		Channel       string   `yaml:"channel"`
		Stream        string   `yaml:"stream"`
		PayloadFields []string `yaml:"payload_fields"`
	} `yaml:"events"`
}

func TestSearchRecommendationSignalEventContract(t *testing.T) {
	path := filepath.Join("..", "..", "..", "contracts", "metadata", "search", "query", "events.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read events.yaml: %v", err)
	}
	var meta searchEventsMeta
	if err := yaml.Unmarshal(raw, &meta); err != nil {
		t.Fatalf("unmarshal events.yaml: %v", err)
	}
	for _, ev := range meta.Events {
		if ev.Name != "SearchRecommendationSignalPublished" {
			continue
		}
		if ev.Producer != "search-service" || ev.Channel != "redis_stream" {
			t.Fatalf("producer/channel drift: %+v", ev)
		}
		if ev.Stream != "events.search.recommendation_signals" {
			t.Fatalf("stream=%q", ev.Stream)
		}
		if len(ev.Consumers) != 1 || ev.Consumers[0] != "content-service" {
			t.Fatalf("consumers=%v want [content-service]", ev.Consumers)
		}
		required := map[string]bool{
			"searchRequestId": true, "sessionId": true, "userId": true,
			"normalizedQuery": true, "relatedTerms": true, "topClickedObjectIds": true,
			"experimentBucket": true,
		}
		for _, field := range ev.PayloadFields {
			delete(required, field)
		}
		if len(required) > 0 {
			t.Fatalf("missing payload fields: %v", required)
		}
		return
	}
	t.Fatal("SearchRecommendationSignalPublished event missing")
}
