// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

func TestSkillManifestsUseOnlyImmutableProfileRefs(t *testing.T) {
	root := assistantSkillAssetRoot(t)
	paths, err := filepath.Glob(filepath.Join(root, "*", "manifest.json"))
	if err != nil || len(paths) == 0 {
		t.Fatalf("skill manifests unavailable: paths=%v err=%v", paths, err)
	}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var document map[string]any
		if err := json.Unmarshal(raw, &document); err != nil {
			t.Fatalf("decode %s: %v", path, err)
		}
		for _, forbidden := range []string{"activation", "slotSchema", "toolPolicy", "iconHint"} {
			if _, found := document[forbidden]; found {
				t.Fatalf("%s keeps retired inline field %q", path, forbidden)
			}
		}
		for _, required := range []string{
			"catalogProfileRef", "activationProfileRef", "inputProfileRef",
			"contextProfileRef", "capabilityProfileRef", "orchestrationProfileRef",
			"triggerProfileRef", "memoryProfileRef", "presentationProfileRef",
			"evaluationProfileRef", "replayAssetRef",
		} {
			if strings.TrimSpace(document[required].(string)) == "" {
				t.Fatalf("%s misses %s", path, required)
			}
		}
	}
	catalog, err := skillfixture.Load()
	if err != nil {
		t.Fatal(err)
	}
	for _, manifest := range catalog {
		if len(manifest.ResolvedAssetRefs) != 11 {
			t.Fatalf("skill %s resolved assets=%v", manifest.SkillID, manifest.ResolvedAssetRefs)
		}
		for kind, proof := range manifest.ResolvedAssetRefs {
			if proof.ProfileID == "" || !strings.HasPrefix(proof.AssetDigest, "sha256:") {
				t.Fatalf("skill %s %s proof=%+v", manifest.SkillID, kind, proof)
			}
		}
	}
}

func TestSkillProfileDigestTamperingFailsClosed(t *testing.T) {
	bundle, err := resourcebuilder.NewSourceBuilderAt(assistantSkillAssetRoot(t)).
		Compile(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	assets := bundle.Profiles
	assets.CapabilityProfiles[0].AssetDigest = "sha256:tampered"
	_, err = assets.ResolveManifest(skillpkg.Manifest{
		CatalogProfileRef:       assets.CatalogProfiles[0].ProfileID,
		ActivationProfileRef:    assets.ActivationProfiles[0].ProfileID,
		InputProfileRef:         assets.InputProfiles[0].ProfileID,
		ContextProfileRef:       assets.ContextProfiles[0].ProfileID,
		CapabilityProfileRef:    assets.CapabilityProfiles[0].ProfileID,
		OrchestrationProfileRef: assets.OrchestrationProfiles[0].ProfileID,
		TriggerProfileRef:       assets.TriggerProfiles[0].ProfileID,
		MemoryProfileRef:        assets.MemoryProfiles[0].ProfileID,
		PresentationProfileRef:  assets.PresentationProfiles[0].ProfileID,
		EvaluationProfileRef:    assets.EvaluationProfiles[0].ProfileID,
	})
	if err == nil || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("tampered profile error=%v", err)
	}
}

func assistantSkillAssetRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(file), "..", "..", "..", "..", "resources", "skills", "assistant", "assistant_session",
	))
}
