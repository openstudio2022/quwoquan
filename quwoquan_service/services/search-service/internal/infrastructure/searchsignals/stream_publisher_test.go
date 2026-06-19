package searchsignals

import (
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/services/search-service/internal/application"
)

func TestStreamValuesEncodeSearchRecommendationSignal(t *testing.T) {
	createdAt := time.Date(2026, 6, 16, 10, 0, 0, 0, time.UTC)
	values, err := StreamValues(application.SearchRecommendationSignal{
		SearchRequestID:     "req-1",
		SessionID:           "sess-1",
		UserID:              "user-1",
		Query:               " 成都 火锅 ",
		NormalizedQuery:     "成都 火锅",
		RelatedTerms:        []string{"火锅", "", "川菜"},
		TopClickedObjectIDs: []string{"post-1", "entity-2"},
		RankingVersion:      "search-v1",
		ExperimentBucket:    "term_heat",
		ResultCount:         12,
		CreatedAt:           createdAt,
	})
	if err != nil {
		t.Fatalf("StreamValues: %v", err)
	}
	if values["eventType"] != "SearchRecommendationSignalPublished" {
		t.Fatalf("eventType=%q", values["eventType"])
	}
	if values["searchRequestId"] != "req-1" || values["sessionId"] != "sess-1" {
		t.Fatalf("ids not encoded: %#v", values)
	}
	var related []string
	if err := json.Unmarshal([]byte(values["relatedTerms"]), &related); err != nil {
		t.Fatalf("relatedTerms json: %v", err)
	}
	if len(related) != 2 || related[0] != "火锅" || related[1] != "川菜" {
		t.Fatalf("relatedTerms=%v", related)
	}
	var objects []string
	if err := json.Unmarshal([]byte(values["topClickedObjectIds"]), &objects); err != nil {
		t.Fatalf("topClickedObjectIds json: %v", err)
	}
	if len(objects) != 2 || objects[0] != "post-1" || objects[1] != "entity-2" {
		t.Fatalf("topClickedObjectIds=%v", objects)
	}
	if values["createdAt"] != createdAt.Format(time.RFC3339Nano) {
		t.Fatalf("createdAt=%q", values["createdAt"])
	}
}
