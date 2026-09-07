// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestDataReleaseStorageDeclaresVerifiedOnlyActivation(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/content/post/storage.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Collections map[string]struct {
			Role        string `yaml:"role"`
			Description string `yaml:"description"`
			Indexes     []struct {
				Name   string         `yaml:"name"`
				Keys   map[string]any `yaml:"keys"`
				Unique bool           `yaml:"unique"`
			} `yaml:"indexes"`
		} `yaml:"collections"`
		Transaction struct {
			Scope      []string `yaml:"scope"`
			Isolation  string   `yaml:"isolation"`
			Guarantees []string `yaml:"guarantees"`
			Mechanism  string   `yaml:"mechanism"`
		} `yaml:"transaction"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	state, ok := document.Collections["data_release_state"]
	if !ok || state.Role != "authoritative" {
		t.Fatalf("data_release_state must be authoritative staged state: %+v", state)
	}
	for _, token := range []string{
		"prepared -> imported -> projected -> verified -> active",
		"verified",
		"previous active",
		"expectedRevision",
		"revision=0",
		"stale release",
		"fail closed",
	} {
		if !strings.Contains(state.Description, token) {
			t.Fatalf("data_release_state description missing %q: %q", token, state.Description)
		}
	}
	uniqueFound := false
	readerIndexFound := false
	for _, index := range state.Indexes {
		switch index.Name {
		case "uq_data_release_state_environment_source_owner":
			uniqueFound = index.Unique && len(index.Keys) == 2 &&
				index.Keys["environment"] == 1 && index.Keys["sourceOwner"] == 1
		case "idx_data_release_state_active_pointer":
			readerIndexFound = len(index.Keys) == 4 &&
				index.Keys["environment"] == 1 && index.Keys["sourceOwner"] == 1 &&
				index.Keys["status"] == 1 && index.Keys["activatedAt"] == -1
		}
	}
	if !uniqueFound {
		t.Fatalf("data_release_state must declare unique environment+sourceOwner index: %+v", state.Indexes)
	}
	if !readerIndexFound {
		t.Fatalf("data_release_state reader index must include sourceOwner: %+v", state.Indexes)
	}
	if document.Transaction.Isolation != "mongo_transaction" ||
		document.Transaction.Mechanism != "version_cas" {
		t.Fatalf("release import transaction must use Mongo version CAS: %+v", document.Transaction)
	}
	wantScope := map[string]bool{
		"posts": true, "content_outbox": true, "content_outbox_sequences": true,
		"data_release_state": true, "data_release_stage_receipts": true,
	}
	for _, collection := range document.Transaction.Scope {
		delete(wantScope, collection)
	}
	if len(wantScope) != 0 {
		t.Fatalf("release import transaction scope is incomplete: missing=%v", wantScope)
	}
	wantGuarantee := map[string]bool{
		"verified_candidate_posts_outbox_active_pointer_atomic_commit": true,
		"active_pointer_environment_source_owner_unique_winner":        true,
		"active_pointer_revision_cas":                                  true,
		"same_release_digest_idempotent_replay":                        true,
		"stale_release_conflict_fail_closed":                           true,
	}
	for _, guarantee := range document.Transaction.Guarantees {
		delete(wantGuarantee, guarantee)
	}
	if len(wantGuarantee) != 0 {
		t.Fatalf("release import transaction guarantees are incomplete: missing=%v", wantGuarantee)
	}
	receipts, ok := document.Collections["data_release_stage_receipts"]
	if !ok || receipts.Role != "append_only" {
		t.Fatalf("data_release_stage_receipts must be append-only: %+v", receipts)
	}
	for _, token := range []string{"duration", "count", "checkpoint", "first typed blocker"} {
		if !strings.Contains(receipts.Description, token) {
			t.Fatalf("stage receipt description missing %q: %q", token, receipts.Description)
		}
	}
}
