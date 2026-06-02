package projection

import (
	"testing"
)

const sampleInterestEnvelope = `{
  "meta": {"topic": "events.content.UserInterestRecomputed", "src": "UserProfile/u1"},
  "payload": {
    "type": "UserInterestRecomputed",
    "aggregateType": "UserProfile",
    "aggregateId": "u1",
    "data": {
      "userId": "u1",
      "interestProfile": {
        "topInterests": [
          {"tagRef": "旅行", "dimension": "topic", "score": 1.0, "level": 5},
          {"tagRef": "图文", "dimension": "format", "score": 0.5, "level": 3}
        ],
        "dimensionTops": {"topic": ["旅行"], "format": ["图文"]},
        "lifecycleStage": "active",
        "freshnessDays": 0,
        "decayHalfLifeDays": 30,
        "recomputedAt": "2026-06-01T00:00:00Z"
      },
      "segments": ["travel_enthusiast", "visual_content_lover"]
    },
    "occurredAt": "2026-06-01T00:00:00Z"
  }
}`

func TestParseInterestEvent_Full(t *testing.T) {
	userID, profile, segments, err := ParseInterestEvent(sampleInterestEnvelope)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if userID != "u1" {
		t.Fatalf("userID = %q, want u1", userID)
	}
	if len(profile.TopInterests) != 2 {
		t.Fatalf("topInterests len = %d, want 2", len(profile.TopInterests))
	}
	if profile.TopInterests[0].TagRef != "旅行" || profile.TopInterests[0].Level != 5 {
		t.Fatalf("first interest = %+v", profile.TopInterests[0])
	}
	if got := profile.DimensionTops["topic"]; len(got) != 1 || got[0] != "旅行" {
		t.Fatalf("dimensionTops[topic] = %v", got)
	}
	if profile.LifecycleStage != "active" || profile.DecayHalfLifeDays != 30 {
		t.Fatalf("stage/halflife = %s/%d", profile.LifecycleStage, profile.DecayHalfLifeDays)
	}
	if profile.RecomputedAt.IsZero() {
		t.Fatal("recomputedAt should parse from RFC3339")
	}
	if len(segments) != 2 || segments[0] != "travel_enthusiast" || segments[1] != "visual_content_lover" {
		t.Fatalf("segments = %v, want [travel_enthusiast visual_content_lover]", segments)
	}
}

func TestParseInterestEvent_AggregateIdFallback(t *testing.T) {
	raw := `{"payload":{"type":"UserInterestRecomputed","aggregateId":"u9","data":{"interestProfile":{"lifecycleStage":"new"}}}}`
	userID, profile, segments, err := ParseInterestEvent(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if userID != "u9" {
		t.Fatalf("userID = %q, want u9 (aggregateId fallback)", userID)
	}
	if profile.LifecycleStage != "new" {
		t.Fatalf("lifecycleStage = %q", profile.LifecycleStage)
	}
	if len(segments) != 0 {
		t.Fatalf("segments = %v, want empty", segments)
	}
}

func TestParseInterestEvent_BadJSON(t *testing.T) {
	if _, _, _, err := ParseInterestEvent("not-json"); err == nil {
		t.Fatal("expected error for malformed envelope")
	}
}

func TestParseInterestEvent_EmptyProfile(t *testing.T) {
	raw := `{"payload":{"data":{"userId":"u2"}}}`
	userID, profile, segments, err := ParseInterestEvent(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if userID != "u2" {
		t.Fatalf("userID = %q, want u2", userID)
	}
	if len(profile.TopInterests) != 0 {
		t.Fatalf("expected empty topInterests, got %v", profile.TopInterests)
	}
	if len(segments) != 0 {
		t.Fatalf("segments = %v, want empty", segments)
	}
}
