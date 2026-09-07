// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/unified-entry-security/rate-limit-protection/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRateLimitBucketHasOneCanonicalNonHTTPRuntimeEntrypoint(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	data, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"contracts",
		"edge_security",
		"rate_limit_bucket",
		"operations.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		APIRoutes          []any `yaml:"api_routes"`
		RuntimeEntrypoints []struct {
			Name        string `yaml:"name"`
			RuntimeKind string `yaml:"kind"`
			Phase       string `yaml:"phase"`
			Application struct {
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				ObjectOwner string `yaml:"object_owner"`
			} `yaml:"application"`
			Consistency struct {
				Arbitration string `yaml:"arbitration"`
			} `yaml:"consistency"`
		} `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.APIRoutes) != 0 {
		t.Fatalf("rate-limit admission must not expose api_routes: %+v", document.APIRoutes)
	}
	if len(document.RuntimeEntrypoints) != 1 {
		t.Fatalf(
			"runtime_entrypoints=%d, want exactly one",
			len(document.RuntimeEntrypoints),
		)
	}
	entrypoint := document.RuntimeEntrypoints[0]
	if entrypoint.Name != "SharedAdmission" ||
		entrypoint.RuntimeKind != "middleware" ||
		entrypoint.Phase != "post_authorization_pre_owner_proxy" ||
		entrypoint.Application.Kind != "session" ||
		entrypoint.Application.Facet != "RateLimitAdmissionFacade" ||
		entrypoint.Application.Method != "admit" ||
		entrypoint.Application.ObjectOwner != "RateLimitBucket" ||
		entrypoint.Consistency.Arbitration != "conditional_admission" {
		t.Fatalf("runtime entrypoint drifted: %+v", entrypoint)
	}
}

func TestRateLimitBucketDeclaresEphemeralEvictionSemantics(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	data, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"contracts",
		"edge_security",
		"rate_limit_bucket",
		"storage.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		RedisCache []struct {
			Key                 string `yaml:"key"`
			KeyPrefix           string `yaml:"key_prefix"`
			Isolation           string `yaml:"isolation"`
			EvictionConsequence string `yaml:"eviction_consequence"`
			Durability          string `yaml:"durability"`
		} `yaml:"redis_cache"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.RedisCache) != 1 {
		t.Fatalf("redis_cache=%d, want exactly one admission key", len(document.RedisCache))
	}
	bucket := document.RedisCache[0]
	if bucket.Key != "edge:rate:{environment}:{subjectDigest}:{operationDigest}" ||
		bucket.KeyPrefix != "edge:rate:" ||
		bucket.Isolation != "single_key_lua" ||
		bucket.EvictionConsequence != "reconstruct" ||
		bucket.Durability != "ephemeral" {
		t.Fatalf("Redis admission storage drifted: %+v", bucket)
	}
}
