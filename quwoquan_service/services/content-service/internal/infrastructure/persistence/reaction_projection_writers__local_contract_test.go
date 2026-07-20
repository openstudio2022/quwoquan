package persistence

import (
	"reflect"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestDiscoveryFeedCountProjectionWaitsForPublicPublishedPostRow(t *testing.T) {
	t.Parallel()

	got := discoveryFeedEligiblePostFilter("post-public")
	want := bson.M{
		"_id":              "post-public",
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("eligible source filter mismatch: got=%#v want=%#v", got, want)
	}

	if _, inverted := got["visibility"].(bson.M); inverted {
		t.Fatal("public visibility must not use $ne: otherwise a missing public feed row is treated as converged")
	}
}
