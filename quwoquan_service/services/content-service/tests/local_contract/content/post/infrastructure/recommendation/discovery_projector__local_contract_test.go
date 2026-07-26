package recommendation_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestDiscoveryFeedViewCountWaitsForEligibleSourceRow(t *testing.T) {
	t.Parallel()

	got := DiscoveryFeedEligibleSourceFilter("post-public")
	want := bson.M{
		"_id":              "post-public",
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("eligible source filter mismatch: got=%#v want=%#v", got, want)
	}
}

func TestBehaviorViewCountDeltaUsesQualifiedImpression(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		event map[string]any
		want  int64
	}{
		{
			name:  "qualified impressed increments",
			event: map[string]any{"action": "impression", "state": "impressed"},
			want:  1,
		},
		{
			name:  "visible does not inflate views",
			event: map[string]any{"action": "impression", "state": "visible"},
			want:  0,
		},
		{
			name:  "missing state does not inflate views",
			event: map[string]any{"action": "impression"},
			want:  0,
		},
		{
			name:  "click does not double count",
			event: map[string]any{"action": "click", "state": "click"},
			want:  0,
		},
	}
	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := BehaviorViewCountDelta(tt.event); got != tt.want {
				t.Fatalf("BehaviorViewCountDelta()=%d want=%d event=%v", got, tt.want, tt.event)
			}
		})
	}
}
