package local_contract

import (
	"encoding/json"
	"testing"
	"time"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
)

func TestSearchSignalStreamValuesSeparateQueryFromRealClick(t *testing.T) {
	createdAt := time.Date(2026, time.July, 26, 10, 0, 0, 0, time.UTC)
	queryValues, err := searchsignals.StreamValues(signalapplication.Signal{
		SignalID:         "query:req-1",
		SignalType:       "query",
		SearchRequestID:  "req-1",
		SessionID:        "sess-1",
		UserID:           "user-1",
		NormalizedQuery:  "成都 火锅",
		RelatedTerms:     []string{"火锅", "", "川菜"},
		RankingVersion:   "search-v1",
		ExperimentBucket: "term_heat",
		ResultCount:      12,
		CreatedAt:        createdAt,
	})
	if err != nil {
		t.Fatalf("encode query signal: %v", err)
	}
	if queryValues["signalId"] != "query:req-1" ||
		queryValues["signalType"] != "query" ||
		queryValues["normalizedQuery"] != "成都 火锅" {
		t.Fatalf("query coordinates not encoded: %#v", queryValues)
	}
	assertJSONStringList(t, queryValues["relatedTerms"], []string{"火锅", "川菜"})
	assertJSONStringList(t, queryValues["engagedObjectIds"], []string{})

	clickValues, err := searchsignals.StreamValues(signalapplication.Signal{
		SignalID:        "feedback:digest-1",
		SignalType:      "click",
		SearchRequestID: "req-1",
		SessionID:       "sess-1",
		UserID:          "user-1",
		EngagedObjectIDs: []string{
			"post-1",
		},
		CreatedAt: createdAt,
	})
	if err != nil {
		t.Fatalf("encode click signal: %v", err)
	}
	if clickValues["signalType"] != "click" || clickValues["normalizedQuery"] != "" {
		t.Fatalf("click signal leaked query semantics: %#v", clickValues)
	}
	assertJSONStringList(t, clickValues["engagedObjectIds"], []string{"post-1"})
	for _, retiredField := range []string{"query", "topClickedObjectIds"} {
		if _, exists := clickValues[retiredField]; exists {
			t.Fatalf("retired signal field %q returned: %#v", retiredField, clickValues)
		}
	}
	if clickValues["createdAt"] != createdAt.Format(time.RFC3339Nano) {
		t.Fatalf("createdAt=%q", clickValues["createdAt"])
	}
}

func TestSearchSignalStreamValuesRejectFabricatedEngagement(t *testing.T) {
	for name, signal := range map[string]signalapplication.Signal{
		"query carrying exposure objects": {
			SignalID:         "query:req-1",
			SignalType:       "query",
			SearchRequestID:  "req-1",
			NormalizedQuery:  "火锅",
			EngagedObjectIDs: []string{"post-not-clicked"},
		},
		"click carrying query": {
			SignalID:         "feedback:digest-1",
			SignalType:       "click",
			SearchRequestID:  "req-1",
			NormalizedQuery:  "火锅",
			EngagedObjectIDs: []string{"post-1"},
		},
		"click without object": {
			SignalID:        "feedback:digest-1",
			SignalType:      "click",
			SearchRequestID: "req-1",
		},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := searchsignals.StreamValues(signal); err == nil {
				t.Fatalf("invalid signal was accepted: %+v", signal)
			}
		})
	}
}

func assertJSONStringList(t *testing.T, raw string, want []string) {
	t.Helper()
	var got []string
	if err := json.Unmarshal([]byte(raw), &got); err != nil {
		t.Fatalf("decode JSON list %q: %v", raw, err)
	}
	if len(got) != len(want) {
		t.Fatalf("list=%v want=%v", got, want)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("list=%v want=%v", got, want)
		}
	}
}
