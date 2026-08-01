package main

import "testing"

func TestBuildPostSnapshotFieldByteLimitsUsesCanonicalFields(t *testing.T) {
	limits := buildPostSnapshotFieldByteLimits(
		[]fieldDef{
			{Name: "authorId", Source: "authorId", MaxUTF8Bytes: 128},
			{Name: "title", Source: "title", MaxUTF8Bytes: 320},
			{Name: "body", Source: "body"},
		},
		[]projectionFieldDef{
			{Name: "authorId", Source: "authorId"},
			{Name: "title", Source: "title"},
			{Name: "body", Source: "body"},
		},
	)

	if len(limits) != 2 || limits["authorId"] != 128 || limits["title"] != 320 {
		t.Fatalf("unexpected snapshot field limits: %#v", limits)
	}
	if _, exists := limits["body"]; exists {
		t.Fatal("fields without canonical max_utf8_bytes must not invent a client limit")
	}
}
