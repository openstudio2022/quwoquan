package main

import (
	"reflect"
	"testing"
)

func TestAssistantWireEntityOrderSortsDependenciesDeterministically(t *testing.T) {
	names := []string{"Aggregate", "Beta", "Gamma"}
	dependencies := map[string]map[string]bool{
		"Aggregate": {
			"Gamma": true,
			"Beta":  true,
		},
		"Beta":  {},
		"Gamma": {},
	}
	want := []string{"Beta", "Gamma", "Aggregate"}

	for attempt := 0; attempt < 100; attempt++ {
		got := assistantWireTopoEntityOrder(names, dependencies)
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("attempt %d order = %v, want %v", attempt, got, want)
		}
	}
}
