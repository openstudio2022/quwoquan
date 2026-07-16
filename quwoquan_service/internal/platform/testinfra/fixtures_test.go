package testinfra

import "testing"

type roundTripSample struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

func TestRoundTripJSON(t *testing.T) {
	got := RoundTripJSON(t, roundTripSample{ID: "sample_1", Name: "fixture"})
	if got.ID != "sample_1" || got.Name != "fixture" {
		t.Fatalf("RoundTripJSON() = %#v", got)
	}
}
