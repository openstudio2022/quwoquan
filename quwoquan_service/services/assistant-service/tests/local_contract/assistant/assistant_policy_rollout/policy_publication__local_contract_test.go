package assistant_policy_rollout_test

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"

	releaseresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/resource"
	rolloutresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/resource"
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

func TestDefaultPolicyArtifactsAreImmutableAndPairConsistently(t *testing.T) {
	t.Parallel()
	resourceRoot := filepath.Join(policyPublicationServiceRoot(), "resources", "policies")
	release, err := releaseresource.LoadReleaseArtifact(
		resourceRoot,
		"assistant/assistant-default/releases/2026-07-26.1.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	rollout, err := loadRolloutArtifact(
		resourceRoot,
		"assistant/assistant-default/rollouts/2026-07-26.1.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if release.Release.PolicyID != rollout.PolicyID ||
		len(rollout.Assignments) != 1 ||
		rollout.Assignments[0].ReleaseVersion != release.Release.ReleaseVersion {
		t.Fatalf("release=%+v rollout=%+v", release, rollout)
	}
}

func TestEveryNonAlphaEnvironmentReferencesValidPolicyArtifacts(t *testing.T) {
	t.Parallel()
	type environmentConfig struct {
		Overrides map[string]string `yaml:"overrides"`
	}
	serviceRoot := policyPublicationServiceRoot()
	resourceRoot := filepath.Join(serviceRoot, "resources", "policies")
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
		if rollout.PolicyID != release.Release.PolicyID {
			t.Fatalf("%s artifact policy mismatch", environment)
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
