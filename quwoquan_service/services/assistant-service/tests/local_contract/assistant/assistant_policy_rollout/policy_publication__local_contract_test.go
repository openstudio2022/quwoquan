// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
package assistant_policy_rollout_test

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	releaseresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/resource"
	rolloutmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	rolloutresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/resource"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

func TestPolicyPublisherRejectsAlphaAndMissingResourceRoot(t *testing.T) {
	serviceRoot := policyPublicationServiceRoot()
	resourceRoot := filepath.Join(serviceRoot, "resources", "policies")
	testCases := []struct {
		name         string
		environment  string
		resourceRoot string
		want         string
	}{
		{
			name:         "alpha cannot publish production policy",
			environment:  "alpha",
			resourceRoot: resourceRoot,
			want:         "alpha uses the contract mock",
		},
		{
			name:         "resource root is mandatory",
			environment:  "gamma",
			resourceRoot: "",
			want:         "policy resource root",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			command := exec.Command(
				"go",
				"run",
				"./cmd/policy-publish",
				"--env",
				testCase.environment,
				"--config-root",
				"/etc/qwq/config",
				"--resource-root",
				testCase.resourceRoot,
			)
			command.Dir = serviceRoot
			output, err := command.CombinedOutput()
			if err == nil {
				t.Fatalf("policy publisher unexpectedly accepted invalid options: %s", output)
			}
			if !strings.Contains(string(output), testCase.want) {
				t.Fatalf("policy publisher error=%q want substring %q", output, testCase.want)
			}
		})
	}
}

func TestPolicyArtifactPathFailsClosedOutsideResourceRoot(t *testing.T) {
	t.Parallel()
	resourceRoot := t.TempDir()
	_, err := releaseresource.ResolveArtifactPath(
		resourceRoot,
		filepath.Join(resourceRoot, "rollout.json"),
	)
	if !errors.Is(err, releaseresource.ErrInvalidArtifact) {
		t.Fatalf("expected invalid policy artifact path, got %v", err)
	}
}

func TestPolicyArtifactLoadersRejectVersionedSchemaAliases(t *testing.T) {
	t.Parallel()
	resourceRoot := t.TempDir()
	releasePath := filepath.Join(resourceRoot, "release.json")
	if err := os.WriteFile(
		releasePath,
		[]byte(`{"schema":"assistant.policy_release.v1","commandId":"","release":{}}`),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"release.json",
	); !errors.Is(err, releaseresource.ErrInvalidArtifact) {
		t.Fatalf("versioned release schema alias must be rejected, got %v", err)
	}

	rollout := strings.NewReader(`{
		"schema":"assistant.policy_rollout.v1",
		"commandId":"policy-rollout:assistant-default:test",
		"policyId":"assistant-default",
		"expectedRevision":0,
		"activatedBy":"test",
		"bucketDefinitions":[{"cohort":"stable","weightBasisPoints":10000}],
		"assignments":[{"cohort":"stable","releaseDigest":"0000000000000000000000000000000000000000000000000000000000000000"}]
	}`)
	if _, err := rolloutresource.DecodeRolloutArtifact(
		rollout,
	); !errors.Is(err, rolloutresource.ErrInvalidArtifact) {
		t.Fatalf("versioned rollout schema alias must be rejected, got %v", err)
	}
}

func TestDefaultPolicyArtifactsAreImmutableAndPairConsistently(t *testing.T) {
	t.Parallel()
	resourceRoot := filepath.Join(policyPublicationServiceRoot(), "resources", "policies")
	release, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"assistant/assistant-default/releases/e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := loadRolloutArtifact(
		resourceRoot,
		"assistant/assistant-default/rollouts/revision-1.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if release.Release.PolicyID != rollout.PolicyID ||
		len(rollout.Assignments) != 1 ||
		rollout.Assignments[0].ReleaseDigest != release.Release.ReleaseDigest {
		t.Fatalf("release=%+v rollout=%+v", release, rollout)
	}
}

func TestAutonomousWebPolicyCandidateIsImmutableAndPairConsistent(t *testing.T) {
	t.Parallel()
	resourceRoot := filepath.Join(policyPublicationServiceRoot(), "resources", "policies")
	release, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"assistant/assistant-default/releases/af1a08bf19d3a7bc5dca987e1da4c976e310aaccb482c38e980b7803c9ac4a34.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := loadRolloutArtifact(
		resourceRoot,
		"assistant/assistant-default/rollouts/revision-3.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if rollout.ExpectedRevision != 2 ||
		release.Release.PolicyID != rollout.PolicyID ||
		len(rollout.Assignments) != 1 ||
		rollout.Assignments[0].ReleaseDigest != release.Release.ReleaseDigest {
		t.Fatalf("release=%+v rollout=%+v", release, rollout)
	}
	for _, template := range release.Release.Templates {
		allowed := make(map[string]bool, len(template.AllowedTools))
		for _, toolName := range template.AllowedTools {
			allowed[toolName] = true
		}
		for _, required := range []string{"web_search", "web_open", "web_find"} {
			if !allowed[required] {
				t.Fatalf(
					"candidate template %q must allow autonomous exploration tool %q: %v",
					template.TemplateID,
					required,
					template.AllowedTools,
				)
			}
		}
	}
}

func TestTravelCompanionPolicyCandidateIsImmutableAndRollbackSafe(t *testing.T) {
	t.Parallel()
	resourceRoot := filepath.Join(policyPublicationServiceRoot(), "resources", "policies")
	const currentDigest = "6579402860644c0273747b33c23962cff013caec0839407afbe7dffdcc50f8e7"
	current, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"assistant/assistant-default/releases/"+currentDigest+".json",
	)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := loadRolloutArtifact(
		resourceRoot,
		"assistant/assistant-default/rollouts/revision-4.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	previousRollout, err := loadRolloutArtifact(
		resourceRoot,
		"assistant/assistant-default/rollouts/revision-3.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if rollout.ExpectedRevision != 3 ||
		len(rollout.Assignments) != 1 ||
		rollout.Assignments[0].ReleaseDigest != current.Release.ReleaseDigest {
		t.Fatalf("release=%+v rollout=%+v", current, rollout)
	}
	if len(previousRollout.Assignments) != 1 {
		t.Fatalf("previous rollout=%+v", previousRollout)
	}
	previousDigest := previousRollout.Assignments[0].ReleaseDigest
	if _, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"assistant/assistant-default/releases/"+previousDigest+".json",
	); err != nil {
		t.Fatalf("previous rollback release must remain a valid immutable artifact: %v", err)
	}

	previous := rolloutmodel.Rollout{
		PolicyID:          previousRollout.PolicyID,
		Revision:          3,
		Status:            "active",
		BucketDefinitions: previousRollout.BucketDefinitions,
		Assignments:       previousRollout.Assignments,
	}
	activated, err := rolloutmodel.Activate(
		&previous,
		rollout.PolicyID,
		rollout.ExpectedRevision,
		rollout.BucketDefinitions,
		rollout.Assignments,
		rollout.ActivatedBy,
		time.Unix(1, 0),
	)
	if err != nil {
		t.Fatal(err)
	}
	rolledBack, err := rolloutmodel.Rollback(
		activated,
		4,
		"service:assistant-policy-publisher",
		time.Unix(2, 0),
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(rolledBack.Assignments) != 1 ||
		rolledBack.Assignments[0].ReleaseDigest != previousDigest {
		t.Fatalf("rollback=%+v want previous release %s", rolledBack, previousDigest)
	}
}

func TestEveryNonAlphaEnvironmentReferencesValidPolicyArtifacts(t *testing.T) {
	t.Parallel()
	type environmentConfig struct {
		Overrides map[string]string `yaml:"overrides"`
	}
	serviceRoot := policyPublicationServiceRoot()
	resourceRoot := filepath.Join(serviceRoot, "resources", "policies")
	const currentDigest = "6579402860644c0273747b33c23962cff013caec0839407afbe7dffdcc50f8e7"
	manifests, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load active Skill package fixture: %v", err)
	}
	activeSkillIDs := make(map[string]bool, len(manifests))
	for _, manifest := range manifests {
		activeSkillIDs[manifest.SkillID] = true
	}
	for _, environment := range []string{"beta", "gamma", "prod"} {
		contents, err := os.ReadFile(filepath.Join(
			serviceRoot,
			"environments",
			environment,
			"config.yaml",
		))
		if err != nil {
			t.Fatalf("read %s policy config: %v", environment, err)
		}
		var config environmentConfig
		if err := yaml.Unmarshal(contents, &config); err != nil {
			t.Fatalf("decode %s policy config: %v", environment, err)
		}
		releaseRef := config.Overrides["sys.assistant-service.policy_publication.release_artifact_ref"]
		rolloutRef := config.Overrides["sys.assistant-service.policy_publication.rollout_artifact_ref"]
		release, err := releaseresource.LoadReleaseArtifact(resourceRoot, releaseRef)
		if err != nil {
			t.Fatalf("%s release artifact: %v", environment, err)
		}
		rollout, err := loadRolloutArtifact(resourceRoot, rolloutRef)
		if err != nil {
			t.Fatalf("%s rollout artifact: %v", environment, err)
		}
		if release.Release.ReleaseDigest != currentDigest ||
			rollout.PolicyID != release.Release.PolicyID ||
			rollout.ExpectedRevision != 3 ||
			len(rollout.Assignments) != 1 ||
			rollout.Assignments[0].ReleaseDigest != release.Release.ReleaseDigest {
			t.Fatalf("%s active artifact pair mismatch: release=%+v rollout=%+v", environment, release, rollout)
		}
		travelTemplates := 0
		for _, template := range release.Release.Templates {
			if !activeSkillIDs[template.SkillID] {
				t.Fatalf("%s policy template %q references skill %q absent from active package", environment, template.TemplateID, template.SkillID)
			}
			if template.SkillID == "travel_planning" || template.SkillID == "travel_transport" {
				t.Fatalf("%s active policy retains retired travel skill %q", environment, template.SkillID)
			}
			if template.DomainID == "travel" {
				travelTemplates++
				if template.SkillID != "travel_companion" || template.TemplateID != "travel-companion" {
					t.Fatalf("%s travel template=%+v want canonical travel_companion", environment, template)
				}
			}
		}
		if travelTemplates != 1 {
			t.Fatalf("%s travel template count=%d want 1", environment, travelTemplates)
		}
		job, err := os.ReadFile(filepath.Join(
			serviceRoot,
			"environments",
			environment,
			"deploy",
			"policy-publish-job.yaml",
		))
		if err != nil {
			t.Fatalf("read %s policy publish Job: %v", environment, err)
		}
		if !strings.Contains(string(job), "assistant-default/"+currentDigest) ||
			!strings.Contains(string(job), "assistant-policy-publish-202608041") {
			t.Fatalf("%s policy publish Job is not bound to the current immutable candidate", environment)
		}
	}
}

func TestTravelEvaluationReplayUsesCanonicalSkillIdentity(t *testing.T) {
	t.Parallel()
	raw, err := os.ReadFile(filepath.Join(
		policyPublicationServiceRoot(),
		"tests",
		"support",
		"contract_fixtures",
		"scenarios",
		"assistant_skill_eval_scenarios.json",
	))
	if err != nil {
		t.Fatal(err)
	}
	var replay struct {
		Scenarios []struct {
			ID                 string `json:"id"`
			SkillID            string `json:"skillId"`
			DomainID           string `json:"domainId"`
			QualityStandardRef string `json:"qualityStandardRef"`
		} `json:"scenarios"`
		QualityStandards map[string]json.RawMessage `json:"qualityStandards"`
	}
	if err := json.Unmarshal(raw, &replay); err != nil {
		t.Fatal(err)
	}
	travelCases := 0
	for _, scenario := range replay.Scenarios {
		if scenario.SkillID == "travel_planning" || scenario.SkillID == "travel_transport" {
			t.Fatalf("replay %q retains retired travel skill %q", scenario.ID, scenario.SkillID)
		}
		if scenario.DomainID != "travel" {
			continue
		}
		travelCases++
		if scenario.SkillID != "travel_companion" ||
			scenario.QualityStandardRef != "travel_companion" {
			t.Fatalf("travel replay=%+v want canonical travel_companion identity", scenario)
		}
		if _, ok := replay.QualityStandards[scenario.QualityStandardRef]; !ok {
			t.Fatalf("travel replay %q references missing quality standard %q", scenario.ID, scenario.QualityStandardRef)
		}
	}
	if travelCases < 2 {
		t.Fatalf("travel replay cases=%d want planning and transport coverage", travelCases)
	}
	for _, retired := range []string{"travel_planning", "travel_transport"} {
		if _, ok := replay.QualityStandards[retired]; ok {
			t.Fatalf("retired quality standard %q remains active", retired)
		}
	}
}

func loadRolloutArtifact(
	resourceRoot string,
	reference string,
) (rolloutresource.RolloutArtifact, error) {
	path, err := releaseresource.ResolveArtifactPath(resourceRoot, reference)
	if err != nil {
		return rolloutresource.RolloutArtifact{}, err
	}
	file, err := os.Open(path)
	if err != nil {
		return rolloutresource.RolloutArtifact{}, err
	}
	defer file.Close()
	return rolloutresource.DecodeRolloutArtifact(file)
}

func policyPublicationServiceRoot() string {
	return filepath.Clean(filepath.Join("..", "..", "..", ".."))
}
