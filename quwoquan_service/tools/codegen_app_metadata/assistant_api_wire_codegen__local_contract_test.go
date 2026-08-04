package main

import (
	"reflect"
	"strings"
	"testing"
)

func TestAssistantWireNullDerivedBooleanFailsClosed(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"SkillConsent": {
			Fields: []fieldDef{
				{
					Name:        "revokedAt",
					Source:      "revokedAt",
					Type:        "timestamp",
					Constraints: []string{"NULLABLE"},
				},
				{
					Name:        "granted",
					Source:      "revokedAt IS NULL",
					Type:        "bool",
					Constraints: []string{"NOT_NULL"},
				},
			},
		},
	}}

	generated := renderAssistantCloudApiWireDart(
		fields,
		[]string{"SkillConsent"},
		nil,
	)
	for _, marker := range []string{
		"final granted = json['granted'];",
		"if (granted is! bool)",
		"final revokedAt = json['revokedAt'];",
		"if (revokedAt != null && granted)",
		"if (revokedAt == null && !granted)",
		"granted: granted && revokedAt == null",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("generated SkillConsent decoder missing %q:\n%s", marker, generated)
		}
	}
	if strings.Contains(generated, "granted: json['granted'] == true") {
		t.Fatalf("derived consent projection must not use permissive bool coercion:\n%s", generated)
	}
}

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

func TestAssistantWireEnumListsRemainStrongAndFailClosed(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"AssistantResponse": {
			Fields: []fieldDef{
				{
					Name:        "requiredScopes",
					Type:        "[]enum",
					EnumRef:     "AssistantPreferenceScope",
					Constraints: []string{"NOT_NULL"},
				},
				{
					Name:        "optionalScopes",
					Type:        "[]enum",
					EnumRef:     "AssistantPreferenceScope",
					Constraints: []string{"NULLABLE"},
				},
			},
		},
	}}
	catalog := &assistantEnumCatalog{Enums: []assistantEnumDef{
		{
			Name: "AssistantPreferenceScope",
			Values: []assistantEnumValueDef{
				{Name: "session", Wire: "session"},
				{Name: "longTerm", Wire: "long_term"},
			},
		},
	}}

	generated := renderAssistantCloudApiWireDart(
		fields,
		[]string{"AssistantResponse"},
		catalog,
	)
	for _, marker := range []string{
		"required this.requiredScopes,",
		"this.optionalScopes,",
		"final List<AssistantPreferenceScope> requiredScopes;",
		"final List<AssistantPreferenceScope>? optionalScopes;",
		"item is! String",
		"(json['requiredScopes'] as List).asMap().entries.map((entry)",
		"json['optionalScopes'] == null\n          ? null\n          : (json['optionalScopes'] as List).asMap().entries.map((entry)",
		"parseAssistantPreferenceScopeStrict(wireValue)",
		"AssistantResponse.requiredScopes[${entry.key}] has an invalid enum wire value",
		"AssistantResponse.optionalScopes[${entry.key}] has an invalid enum wire value",
		"requiredScopes.map((item) => item.wireName).toList(growable: false)",
		"optionalScopes?.map((item) => item.wireName).toList(growable: false)",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("generated enum-list response missing %q:\n%s", marker, generated)
		}
	}
	for _, forbidden := range []string{
		"final List<dynamic> requiredScopes;",
		"final List<dynamic>? optionalScopes;",
		"((json['optionalScopes'] as List?) ?? const [])",
		".map((e) => e.toString())",
	} {
		if strings.Contains(generated, forbidden) {
			t.Fatalf("generated enum-list response contains permissive fallback %q:\n%s", forbidden, generated)
		}
	}
}
