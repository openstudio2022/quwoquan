package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestCanonicalSearchProjectionFollowsReadModelIdentity(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	path, err := projectionPathByReadModel(metadataDir, "CanonicalSearchHit")
	if err != nil {
		t.Fatal(err)
	}
	relative, err := filepath.Rel(metadataDir, path)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := filepath.ToSlash(relative),
		"search/search/search_index_view/projections/canonical_search_hit.yaml"; got != want {
		t.Fatalf("projection path=%q want %q", got, want)
	}
}

func TestCanonicalSearchClientFieldsPreserveNestedTypesAndWireNames(t *testing.T) {
	fields, err := canonicalSearchEntityFields([]fieldDef{
		{
			Name:           "class",
			Type:           "string",
			ClientDartName: "intersectionClass",
			ClientWireName: "class",
			Constraints:    []string{"NULLABLE"},
		},
		{
			Name:        "contentType",
			Type:        "enum",
			EnumRef:     "ContentType",
			Constraints: []string{"NOT_NULL"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if fields[0].Name != "intersectionClass" || projectionWireKey(fields[0]) != "class" {
		t.Fatalf("reserved wire name drifted: %#v", fields[0])
	}
	if fields[1].DartType != "ContentType" || fields[1].EnumRef != "ContentType" {
		t.Fatalf("canonical enum degraded: %#v", fields[1])
	}

	hitField, err := canonicalSearchClientField(
		"evidence",
		"evidence",
		"[]CanonicalSearchEvidence",
		"",
		false,
	)
	if err != nil {
		t.Fatal(err)
	}
	if hitField.DartType != "List<CanonicalSearchEvidence>" ||
		hitField.ListElementDartClass != "CanonicalSearchEvidence" {
		t.Fatalf("nested list degraded: %#v", hitField)
	}
}

func TestCanonicalSearchGeneratedModelIsStrictAndUsesCanonicalNestedDecoder(t *testing.T) {
	content := renderStandaloneDtoDart(clientProjection{
		DartClass: "CanonicalSearchHit",
		Strict:    true,
		Fields: []projectionFieldDef{
			{Name: "target", WireName: "target", DartType: "String", WireType: "string"},
			{
				Name:                  "content",
				WireName:              "content",
				DartType:              "CanonicalSearchContentHit",
				WireType:              "CanonicalSearchContentHit",
				Nullable:              true,
				MapFromStringKeyClass: "CanonicalSearchContentHit",
			},
		},
	}, "canonical_search_hit.yaml")
	for _, expected := range []string{
		"_validateCanonicalSearchHitWire(m)",
		"CanonicalSearchContentHit.fromMap(_parseStringKeyMap(m['content'])!)",
		"'target': target",
		"'content': content?.toMap()",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated canonical Search model missing %q:\n%s", expected, content)
		}
	}
}

func TestContentContractEnumsUseSharedCanonicalValues(t *testing.T) {
	content, err := renderSharedContractEnumsDart(
		map[string][]string{
			"ContentType":     {"image", "video", "micro", "article"},
			"ContentIdentity": {"moment", "work"},
		},
		[]string{"ContentType", "ContentIdentity"},
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"enum ContentType",
		"micro(\"micro\")",
		"enum ContentIdentity",
		"static ContentIdentity fromWire(Object? raw)",
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated Content enum missing %q:\n%s", expected, content)
		}
	}
}
