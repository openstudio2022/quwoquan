package main

import (
	"strings"
	"testing"
)

func TestRenderStandaloneDtoHasExactlyOneTrailingNewline(t *testing.T) {
	projection := clientProjection{
		DartClass: "TimestampedDto",
		Fields: []projectionFieldDef{
			{
				Name:     "createdAt",
				Source:   "createdAt",
				DartType: "DateTime",
			},
		},
	}

	generated := renderStandaloneDtoDart(projection, "fixture.yaml")
	if !strings.HasSuffix(generated, "}\n") {
		t.Fatalf("generated DTO must end with one newline")
	}
	if strings.HasSuffix(generated, "\n\n") {
		t.Fatal("generated DTO must not contain a blank line at EOF")
	}
}

func TestRenderStandaloneDtoStrictProjectionRejectsUnknownAndInvalidWireValues(t *testing.T) {
	projection := clientProjection{
		DartClass: "StrictMessageDto",
		Strict:    true,
		Fields: []projectionFieldDef{
			{Name: "id", Source: "id", DartType: "String"},
			{Name: "mentions", Source: "mentions", DartType: "List<String>", Nullable: true},
			{Name: "timestamp", Source: "timestamp", DartType: "DateTime", Nullable: true},
		},
	}

	generated := renderStandaloneDtoDart(projection, "fixture.yaml")
	for _, expected := range []string{
		"_validateStrictMessageDtoWire(m);",
		"final unknown = m.keys.where((key) => !allowed.contains(key))",
		"!m.containsKey('id') || m['id'] == null || (m['id'] is! String)",
		"m.containsKey('mentions') && m['mentions'] != null && (m['mentions'] is! List || (m['mentions'] as List).any((value) => value is! String))",
		"DateTime.tryParse(m['timestamp'] as String) == null",
		"'timestamp': timestamp?.toIso8601String()",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("strict DTO missing %q:\n%s", expected, generated)
		}
	}
}

func TestRenderStandaloneDtoStrictNestedProjection(t *testing.T) {
	generated := renderStandaloneDtoDart(clientProjection{
		DartClass: "EnvelopeDto",
		Strict:    true,
		Fields: []projectionFieldDef{
			{
				Name:                  "card",
				DartType:              "CardDto",
				Nullable:              true,
				Source:                "card",
				MapFromStringKeyClass: "CardDto",
			},
			{
				Name:                 "items",
				DartType:             "List<ItemDto>",
				Source:               "items",
				ListElementDartClass: "ItemDto",
			},
		},
	}, "nested.yaml")

	for _, expected := range []string{
		"card: m['card'] == null ? null : CardDto.fromMap(_parseStringKeyMap(m['card'])!)",
		"'card': card?.toMap()",
		"'items': items.map((value) => value.toMap()).toList(growable: false)",
		"m.containsKey('card') && m['card'] != null && (m['card'] is! Map",
		"!m.containsKey('items') || m['items'] == null || (m['items'] is! List",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("strict nested DTO missing %q:\n%s", expected, generated)
		}
	}
}
