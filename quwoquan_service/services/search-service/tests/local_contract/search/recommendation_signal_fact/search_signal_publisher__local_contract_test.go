// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: append-recommendation-signal-local
package local_contract

import (
	"context"
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

func TestRecommendationSignalAppenderOwnsTheRuntimeEntrypoint(t *testing.T) {
	publisher := &readinessSignalPublisher{}
	appender, err := signalapplication.NewAppender(publisher)
	if err != nil {
		t.Fatalf("NewAppender() error = %v", err)
	}
	fact := signalapplication.Signal{
		SignalID:         "query:readiness-request",
		SignalType:       "query",
		SearchRequestID:  "readiness-request",
		NormalizedQuery:  "成都旅行",
		ExperimentBucket: "control",
		ResultCount:      2,
		CreatedAt:        time.Now().UTC(),
	}
	if err := appender.Append(t.Context(), fact); err != nil {
		t.Fatalf("Append() error = %v", err)
	}
	if len(publisher.facts) != 1 || publisher.facts[0].SignalID != fact.SignalID {
		t.Fatalf("published facts = %+v", publisher.facts)
	}
}

type readinessSignalPublisher struct {
	facts []signalapplication.Signal
}

func (publisher *readinessSignalPublisher) PublishSearchSignal(
	_ context.Context,
	fact signalapplication.Signal,
) error {
	publisher.facts = append(publisher.facts, fact)
	return nil
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
