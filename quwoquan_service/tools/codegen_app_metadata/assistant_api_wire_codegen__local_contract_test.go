package main

import (
	"reflect"
	"strings"
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

func TestAssistantWireDatetimeRemainsStronglyTyped(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{}}
	field := fieldDef{
		Name:        "capturedAt",
		Type:        "datetime",
		Constraints: []string{"NULLABLE"},
	}

	if got := assistantWireDartType(fields, nil, field, true); got != "DateTime?" {
		t.Fatalf("datetime Dart type = %q, want DateTime?", got)
	}
	if got := assistantWireFromJsonExpr(
		fields,
		nil,
		"AssistantContextSnapshot",
		field,
	); !strings.Contains(got, "DateTime.tryParse") {
		t.Fatalf("datetime parser = %q", got)
	}
	if got := assistantWireToJsonExpr(fields, nil, field); got !=
		"capturedAt?.toUtc().toIso8601String()" {
		t.Fatalf("datetime serializer = %q", got)
	}
}
