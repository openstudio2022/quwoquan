package main

import "testing"

func TestBuildPostSnapshotFieldByteLimitsUsesCanonicalFields(t *testing.T) {
	limits, err := buildPostSnapshotFieldByteLimits(
		[]fieldDef{
			{Name: "authorId", Source: "authorId", MaxUTF8Bytes: 128},
			{Name: "title", Source: "title", MaxUTF8Bytes: 320},
			{Name: "body", Source: "body"},
		},
		&projectionFile{
			ClientProjection: clientProjection{
				Fields: []projectionFieldDef{
					{Name: "authorId", Source: "authorId"},
					{Name: "title", Source: "title"},
					{Name: "body", Source: "body"},
				},
			},
			clientProjectionFieldsDeclared: true,
		},
	)
	if err != nil {
		t.Fatalf("derive snapshot field limits: %v", err)
	}

	if len(limits) != 2 || limits["authorId"] != 128 || limits["title"] != 320 {
		t.Fatalf("unexpected snapshot field limits: %#v", limits)
	}
	if _, exists := limits["body"]; exists {
		t.Fatal("fields without canonical max_utf8_bytes must not invent a client limit")
	}
}

// 现行 projection 契约已全部退役 client_projection 段，字段直接声明在顶层
// fields。限额派生必须消费该 canonical 字段集，否则逐字段 byte admission 会
// 退化成空表。
func TestBuildPostSnapshotFieldByteLimitsUsesCanonicalProjectionFields(t *testing.T) {
	limits, err := buildPostSnapshotFieldByteLimits(
		[]fieldDef{
			{Name: "authorId", Source: "authorId", MaxUTF8Bytes: 128},
			{Name: "title", Source: "title", MaxUTF8Bytes: 320},
			{Name: "behaviorProjectionLastId", Source: "behaviorProjectionLastId"},
		},
		&projectionFile{
			Fields: []projectionFieldDef{
				{Name: "postId", WireType: "ObjectId", MaxUTF8Bytes: 256},
				{Name: "authorId", WireType: "string"},
				{Name: "title", WireType: "string"},
				{Name: "behaviorProjectionLastId", WireType: "string"},
			},
		},
	)
	if err != nil {
		t.Fatalf("derive snapshot field limits: %v", err)
	}

	want := map[string]int{"postId": 256, "authorId": 128, "title": 320}
	if len(limits) != len(want) {
		t.Fatalf("unexpected snapshot field limits: %#v", limits)
	}
	for field, limit := range want {
		if limits[field] != limit {
			t.Fatalf(
				"snapshot field limit for %s is %d, want %d",
				field,
				limits[field],
				limit,
			)
		}
	}
	if _, exists := limits["behaviorProjectionLastId"]; exists {
		t.Fatal("projection-only field without canonical byte limit must stay absent")
	}
}

// 同一 wire key 不得同时从 projection 与聚合字段拿到两个不同限额。
func TestBuildPostSnapshotFieldByteLimitsRejectsConflictingLimits(t *testing.T) {
	if _, err := buildPostSnapshotFieldByteLimits(
		[]fieldDef{{Name: "title", Source: "title", MaxUTF8Bytes: 320}},
		&projectionFile{
			Fields: []projectionFieldDef{
				{Name: "title", WireType: "string", MaxUTF8Bytes: 640},
			},
		},
	); err == nil {
		t.Fatal("conflicting canonical max_utf8_bytes must fail closed")
	}
}
