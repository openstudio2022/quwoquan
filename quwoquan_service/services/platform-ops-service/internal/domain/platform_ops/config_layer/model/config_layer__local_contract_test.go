package model

import (
	"testing"
	"time"
)

func TestConfigLayerOwnsTypedEntriesAndEnforcesScope(t *testing.T) {
	now := time.Date(2026, 7, 14, 12, 0, 0, 0, time.UTC)
	layer, err := NewConfigLayer(Scope{
		Level: "service", ID: "content-service", Environment: "gamma",
		Cluster: "gamma-user-a", Service: "content-service",
	}, now)
	if err != nil {
		t.Fatalf("new config layer: %v", err)
	}
	value := int64(120)
	updated, err := layer.SetValue(
		"sys.content.mongo.max_pool_size",
		ConfigValue{Kind: ValueKindInt, IntValue: &value},
		ValueKindInt,
		"service",
		now.Add(time.Minute),
	)
	if err != nil {
		t.Fatalf("set typed config value: %v", err)
	}
	if updated.Version != 1 || len(updated.Entries) != 1 || updated.Entries[0].Key == "" {
		t.Fatalf("unexpected updated layer: %+v", updated)
	}
	if _, err := updated.SetValue(
		"sys.content.mongo.max_pool_size",
		ConfigValue{Kind: ValueKindString, StringValue: stringPointer("120")},
		ValueKindInt,
		"service",
		now,
	); err == nil {
		t.Fatal("mismatched catalog value kind must fail")
	}
	if _, err := updated.SetValue(
		"sys.content.mongo.max_pool_size",
		ConfigValue{Kind: ValueKindInt, IntValue: &value},
		ValueKindInt,
		"environment",
		now,
	); err == nil {
		t.Fatal("cross-scope config write must fail")
	}
}

func TestConfigScopeRejectsAmbiguousHierarchy(t *testing.T) {
	invalid := []Scope{
		{Level: "global", ID: "prod"},
		{Level: "environment", ID: "prod", Environment: "gamma"},
		{Level: "cluster", ID: "gamma-a", Cluster: "gamma-a"},
		{Level: "service", ID: "content-service", Environment: "gamma", Service: "content-service"},
	}
	for _, scope := range invalid {
		if err := scope.Validate(); err == nil {
			t.Fatalf("ambiguous scope must fail: %+v", scope)
		}
	}
}

func stringPointer(value string) *string { return &value }
