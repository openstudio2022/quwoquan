package registry

import (
	"os"
	"path/filepath"
	"testing"
)

func metadataDir(t *testing.T) string {
	t.Helper()
	dir := filepath.Join("..", "..", "contracts", "metadata")
	if _, err := os.Stat(dir); err != nil {
		t.Skipf("metadata dir not found at %s, skipping", dir)
	}
	return dir
}

func TestLoadFromDirectory(t *testing.T) {
	dir := metadataDir(t)

	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("LoadFromDirectory failed: %v", err)
	}

	stats := reg.Stats()
	if stats.AggregateCount < 12 {
		t.Errorf("expected >= 12 aggregates, got %d", stats.AggregateCount)
	}
	if stats.EnumCount < 20 {
		t.Errorf("expected >= 20 enums, got %d", stats.EnumCount)
	}
	t.Logf("loaded: %d aggregates, %d entities, %d fields, %d events, %d enums",
		stats.AggregateCount, stats.EntityCount, stats.FieldCount, stats.EventCount, stats.EnumCount)
}

func TestGetAggregate_Post(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	agg, err := reg.GetAggregate("Post")
	if err != nil {
		t.Fatalf("GetAggregate(Post): %v", err)
	}
	if agg.Spec.Domain != "content" {
		t.Errorf("Post domain: got %q, want %q", agg.Spec.Domain, "content")
	}
	if agg.Spec.StorageBackend != "mongodb" {
		t.Errorf("Post storage: got %q, want %q", agg.Spec.StorageBackend, "mongodb")
	}
}

func TestGetAggregate_UserProfile(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	agg, err := reg.GetAggregate("UserProfile")
	if err != nil {
		t.Fatalf("GetAggregate(UserProfile): %v", err)
	}
	if agg.Spec.StorageBackend != "postgres" {
		t.Errorf("UserProfile storage: got %q, want %q", agg.Spec.StorageBackend, "postgres")
	}
	if agg.Spec.CacheTTLSeconds != 600 {
		t.Errorf("UserProfile cache TTL: got %d, want %d", agg.Spec.CacheTTLSeconds, 600)
	}
}

func TestGetStorageBackend(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	cases := []struct {
		entity  string
		backend string
	}{
		{"Post", "mongodb"},
		{"Comment", "mongodb"},
		{"UserProfile", "postgres"},
		{"Persona", "postgres"},
		{"FollowEdge", "mongodb"},
	}

	for _, tc := range cases {
		backend, err := reg.GetStorageBackend(tc.entity)
		if err != nil {
			t.Errorf("GetStorageBackend(%s): %v", tc.entity, err)
			continue
		}
		if backend != tc.backend {
			t.Errorf("GetStorageBackend(%s): got %q, want %q", tc.entity, backend, tc.backend)
		}
	}
}

func TestGetCapabilities(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	caps, err := reg.GetCapabilities("Post")
	if err != nil {
		t.Fatalf("GetCapabilities(Post): %v", err)
	}

	want := map[string]bool{
		"queryable":        true,
		"searchable":       true,
		"aggregatable":     true,
		"vector_searchable": true,
	}
	for _, c := range caps {
		if !want[c] {
			t.Errorf("unexpected Post capability: %q", c)
		}
		delete(want, c)
	}
	for c := range want {
		t.Errorf("missing Post capability: %q", c)
	}
}

func TestGetField(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	field, err := reg.GetField("UserProfile", "phone")
	if err != nil {
		t.Fatalf("GetField(UserProfile, phone): %v", err)
	}
	if field.Classification != "PII" {
		t.Errorf("phone classification: got %q, want %q", field.Classification, "PII")
	}
	if field.APIExposure != "drop" {
		t.Errorf("phone api_exposure: got %q, want %q", field.APIExposure, "drop")
	}
	if field.LogPolicy != "mask" {
		t.Errorf("phone log_policy: got %q, want %q", field.LogPolicy, "mask")
	}
}

func TestGetCacheTTL(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	ttl, err := reg.GetCacheTTL("UserProfile")
	if err != nil {
		t.Fatalf("GetCacheTTL(UserProfile): %v", err)
	}
	if ttl != 600 {
		t.Errorf("UserProfile cache TTL: got %d, want %d", ttl, 600)
	}
}

func TestGetEnum(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	vals, err := reg.GetEnum("ContentType")
	if err != nil {
		t.Fatalf("GetEnum(ContentType): %v", err)
	}
	want := map[string]bool{"image": true, "video": true, "micro": true, "article": true}
	for _, v := range vals {
		if !want[v] {
			t.Errorf("unexpected ContentType value: %q", v)
		}
	}
}

func TestGetEntity_NotRegistered(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	_, err = reg.GetEntity("NonExistent")
	if err == nil {
		t.Errorf("expected error for unregistered entity, got nil")
	}
}

func TestGetEvents(t *testing.T) {
	dir := metadataDir(t)
	reg, err := LoadFromDirectory(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	events, err := reg.GetEvents("Post")
	if err != nil {
		t.Fatalf("GetEvents(Post): %v", err)
	}
	if len(events) < 5 {
		t.Errorf("Post events: expected >= 5, got %d", len(events))
	}

	found := false
	for _, e := range events {
		if e.Name == "PostCreated" {
			found = true
			if e.Producer != "content-service" {
				t.Errorf("PostCreated producer: got %q, want %q", e.Producer, "content-service")
			}
		}
	}
	if !found {
		t.Error("PostCreated event not found")
	}
}
