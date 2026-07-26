package api_integration

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func TestCircleImpactUsesPersistedOwnerEvidenceSnapshot(t *testing.T) {
	defer cleanCollections(t)
	seedCircleContractFixture(t, "circle_core")

	rec := doRequest(t, http.MethodGet, "/circles/fixture_circle_photo/impact", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var payload struct {
		Data struct {
			CircleID string `json:"circleId"`
			Items    []struct {
				PrimaryText        string `json:"primaryText"`
				EvidenceSnapshotID string `json:"evidenceSnapshotId"`
				PrimarySpans       []struct {
					Text   string         `json:"text"`
					Role   string         `json:"role"`
					Target map[string]any `json:"target"`
				} `json:"primarySpans"`
				RepresentativeActor *struct {
					ActorID       string         `json:"actorId"`
					DisplayName   string         `json:"displayName"`
					RelationLabel string         `json:"relationLabel"`
					Target        map[string]any `json:"target"`
				} `json:"representativeActor"`
			} `json:"items"`
		} `json:"data"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode impact response: %v", err)
	}
	if payload.Data.CircleID != "fixture_circle_photo" || len(payload.Data.Items) != 1 {
		t.Fatalf("unexpected impact payload: %+v", payload.Data)
	}
	item := payload.Data.Items[0]
	if item.RepresentativeActor == nil || item.RepresentativeActor.ActorID != "fixture_user_owner" || item.RepresentativeActor.DisplayName != "契约摄影社主理人" || item.RepresentativeActor.RelationLabel != "圈子主理人" {
		t.Fatalf("representative actor did not come from fixture snapshot: %+v", item.RepresentativeActor)
	}
	if item.RepresentativeActor.Target["objectType"] != "user" || item.EvidenceSnapshotID == "" {
		t.Fatalf("actor target/evidence snapshot incomplete: %+v", item)
	}
	var joined strings.Builder
	hasObjectTarget := false
	for _, span := range item.PrimarySpans {
		joined.WriteString(span.Text)
		if span.Role == "object" && span.Target["objectType"] == "circle" && span.Target["objectId"] == "fixture_circle_photo" {
			hasObjectTarget = true
		}
	}
	if joined.String() != item.PrimaryText || !hasObjectTarget {
		t.Fatalf("primary statement contract incomplete: text=%q spans=%+v", item.PrimaryText, item.PrimarySpans)
	}
}
