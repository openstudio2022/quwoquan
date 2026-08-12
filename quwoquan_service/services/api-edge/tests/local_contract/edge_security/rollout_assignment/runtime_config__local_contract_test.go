// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
package local_contract

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutdomain "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"

	"gopkg.in/yaml.v3"
)

var rolloutRequiredUpstreams = []string{"content"}

func TestValidateAndLoadRolloutConfigFailsClosedInProd(t *testing.T) {
	disabled := rolloutapp.RuntimeConfig{}
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&disabled,
		"prod",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err == nil {
		t.Fatal("prod accepted disabled rollout")
	}

	policyPath, digest := writeRolloutPolicy(t)
	config := validEnabledRolloutConfig(policyPath, digest)
	delete(config.CandidateUpstreams, "content")
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config,
		"prod",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err == nil || !strings.Contains(err.Error(), "candidate upstream content") {
		t.Fatalf("missing candidate owner was not rejected: %v", err)
	}

	config = validEnabledRolloutConfig(policyPath, digest)
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config,
		"prod",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err != nil {
		t.Fatalf("valid rollout config: %v", err)
	}
	if config.Policy.CampaignID != "release-test-001" {
		t.Fatalf("loaded campaign=%q", config.Policy.CampaignID)
	}

	config = validEnabledRolloutConfig(
		policyPath,
		"sha256:"+strings.Repeat("0", 64),
	)
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config,
		"prod",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err == nil || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("policy digest mismatch was not rejected: %v", err)
	}
}

func TestDisabledNonProdRolloutRejectsCandidateRoutes(t *testing.T) {
	config := rolloutapp.RuntimeConfig{
		CandidateUpstreams: map[string]string{"content": "http://candidate:18080"},
	}
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config,
		"gamma",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err == nil {
		t.Fatal("disabled rollout accepted candidate routes")
	}
	config.CandidateUpstreams = nil
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config,
		"gamma",
		"/release/config.yaml",
		rolloutRequiredUpstreams,
	); err != nil {
		t.Fatalf("explicit disabled non-prod rollout: %v", err)
	}
}

func TestDirectedNetworkAudienceRequiresReleaseBoundCatalog(t *testing.T) {
	policy := runtimeTestRolloutPolicy()
	for _, name := range []string{"canary", "5", "20", "50"} {
		stage := policy.Stages[name]
		stage.Regions = rolloutdomain.Selector{Mode: "include", Values: []string{"gd"}}
		policy.Stages[name] = stage
	}
	policyPath, digest := writeRolloutPolicyDocument(t, policy)
	config := validEnabledRolloutConfig(policyPath, digest)
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config, "prod", "/release/config.yaml", rolloutRequiredUpstreams,
	); err == nil || !strings.Contains(err.Error(), "requires the network attribute catalog") {
		t.Fatalf("directed rollout without catalog was not rejected: %v", err)
	}

	config = validEnabledRolloutConfig(policyPath, digest)
	config.NetworkAttributeCatalog.Enabled = true
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config, "prod", "/release/config.yaml", rolloutRequiredUpstreams,
	); err == nil || !strings.Contains(err.Error(), "requires a file and canonical SHA-256") {
		t.Fatalf("catalog without immutable inputs was not rejected: %v", err)
	}

	config = validEnabledRolloutConfig(policyPath, digest)
	config.NetworkAttributeCatalog = rolloutapp.NetworkAttributeCatalogConfig{
		Enabled: true,
		File:    "catalog/network_attributes.yaml",
		SHA256:  "sha256:" + strings.Repeat("a", 64),
	}
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config, "prod", "/release/config.yaml", rolloutRequiredUpstreams,
	); err != nil {
		t.Fatalf("release-bound directed rollout config: %v", err)
	}
	if config.NetworkAttributeCatalog.File != "/release/catalog/network_attributes.yaml" {
		t.Fatalf("resolved catalog=%q", config.NetworkAttributeCatalog.File)
	}
}

func TestUnknownOnlyNetworkAudienceDoesNotRequireCatalog(t *testing.T) {
	policy := runtimeTestRolloutPolicy()
	for _, name := range []string{"canary", "5", "20", "50"} {
		stage := policy.Stages[name]
		stage.Regions = rolloutdomain.Selector{Mode: "include", Values: []string{"unknown"}}
		stage.Carriers = rolloutdomain.Selector{Mode: "include", Values: []string{"unknown"}}
		policy.Stages[name] = stage
	}
	policyPath, digest := writeRolloutPolicyDocument(t, policy)
	config := validEnabledRolloutConfig(policyPath, digest)
	if err := rolloutapp.ValidateAndLoadRuntimeConfig(
		&config, "prod", "/release/config.yaml", rolloutRequiredUpstreams,
	); err != nil {
		t.Fatalf("unknown-only rollout must work without catalog: %v", err)
	}
}

func TestRolloutAllocationKeyComesOnlyFromRequiredSecret(t *testing.T) {
	if key, err := rolloutapp.AllocationKey(false, nil); err != nil || key != nil {
		t.Fatalf("disabled rollout allocation key=(%q,%v)", key, err)
	}
	if _, err := rolloutapp.AllocationKey(
		true,
		func(string) (string, bool) { return "", false },
	); err == nil {
		t.Fatal("enabled rollout accepted missing allocation key")
	}
	secret := strings.Repeat("k", 32)
	key, err := rolloutapp.AllocationKey(true, func(name string) (string, bool) {
		if name != "API_EDGE_ROLLOUT_ALLOCATION_KEY" {
			t.Fatalf("unexpected secret name %q", name)
		}
		return secret, true
	})
	if err != nil || string(key) != secret {
		t.Fatalf("allocation key=(%q,%v)", key, err)
	}
}

func TestMinimumBuildAppliesToAppAndBypassesTrustedService(t *testing.T) {
	middleware, err := httpadapter.MinimumBuildMiddleware(
		rolloutapp.MinimumBuildPolicy{
			SourceDigest: "sha256:" + strings.Repeat("a", 64),
			Mode:         "enforce",
			Platforms:    map[string]uint64{"android": 10, "ios": 10, "web": 10},
		},
		map[string]struct{}{},
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	next := http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusNoContent)
	})
	handler := httpadapter.MinimumBuildForAuthenticatedClients(middleware, next)

	appRequest := httptest.NewRequest(http.MethodGet, "/content/posts", nil)
	appRequest.Header.Set("X-Client-Device-Platform", "android")
	appRequest.Header.Set("X-Client-App-Build", "9")
	appRequest = appRequest.WithContext(rtauth.WithPrincipal(
		appRequest.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"user"}},
			Actor:  operation.ActorContext{AccountID: "account-1"},
		},
	))
	appResponse := httptest.NewRecorder()
	handler.ServeHTTP(appResponse, appRequest)
	if appResponse.Code != http.StatusUpgradeRequired {
		t.Fatalf("app status=%d, want 426", appResponse.Code)
	}

	serviceRequest := httptest.NewRequest(http.MethodGet, "/content/posts", nil)
	serviceRequest = serviceRequest.WithContext(rtauth.WithPrincipal(
		context.Background(),
		rtauth.Principal{Actor: operation.ActorContext{AccountID: "service:api-integration"}},
	))
	serviceResponse := httptest.NewRecorder()
	handler.ServeHTTP(serviceResponse, serviceRequest)
	if serviceResponse.Code != http.StatusNoContent {
		t.Fatalf("trusted service status=%d, want 204", serviceResponse.Code)
	}

	serviceRoleRequest := httptest.NewRequest(http.MethodGet, "/content/posts", nil)
	serviceRoleRequest = serviceRoleRequest.WithContext(rtauth.WithPrincipal(
		context.Background(),
		rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "machine-account"},
		},
	))
	serviceRoleResponse := httptest.NewRecorder()
	handler.ServeHTTP(serviceRoleResponse, serviceRoleRequest)
	if serviceRoleResponse.Code != http.StatusNoContent {
		t.Fatalf("trusted service role status=%d, want 204", serviceRoleResponse.Code)
	}
}

func TestMinimumBuildMetricLabelsAreBounded(t *testing.T) {
	if got := rolloutapp.NormalizeBuildMetricValue("not-a-build"); got != "invalid" {
		t.Fatalf("invalid build label=%q", got)
	}
	if got := rolloutapp.NormalizeBuildMetricValue(""); got != "missing" {
		t.Fatalf("missing build label=%q", got)
	}
	if got := rolloutapp.NormalizeMetricValue(strings.Repeat("x", 1000), "unknown"); got != "unknown" {
		t.Fatalf("unbounded label=%q", got)
	}
}

type rolloutPolicyDocument struct {
	Policy rolloutdomain.Policy `yaml:"policy"`
}

func writeRolloutPolicy(t *testing.T) (string, string) {
	t.Helper()
	return writeRolloutPolicyDocument(t, runtimeTestRolloutPolicy())
}

func runtimeTestRolloutPolicy() rolloutdomain.Policy {
	policy := rolloutdomain.Policy{
		Enabled:                        true,
		CampaignID:                     "release-test-001",
		CandidateDigest:                "sha256:" + strings.Repeat("b", 64),
		AllocationKeyID:                "rollout-key-test",
		SubjectKind:                    rolloutdomain.SubjectKindDeviceActor,
		Stage:                          "canary",
		Status:                         "active",
		AssignmentTTLDaysAfterCampaign: 30,
		Stages:                         map[string]rolloutdomain.Stage{},
	}
	for stage, basisPoints := range map[string]int{
		"canary": 0,
		"5":      500,
		"20":     2000,
		"50":     5000,
		"100":    10000,
	} {
		policy.Stages[stage] = rolloutdomain.Stage{
			BasisPoints: basisPoints,
			AppVersions: rolloutdomain.Selector{Mode: "supported"},
			Platforms: rolloutdomain.Selector{
				Mode: "include", Values: []string{"android", "ios", "web"},
			},
			Regions:  rolloutdomain.Selector{Mode: "all"},
			Carriers: rolloutdomain.Selector{Mode: "all"},
		}
	}
	return policy
}

func writeRolloutPolicyDocument(
	t *testing.T,
	policy rolloutdomain.Policy,
) (string, string) {
	t.Helper()
	raw, err := yaml.Marshal(rolloutPolicyDocument{Policy: policy})
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "routing_policy.yaml")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	return path, fmt.Sprintf("sha256:%x", sha256.Sum256(raw))
}

func validEnabledRolloutConfig(policyPath, policyDigest string) rolloutapp.RuntimeConfig {
	return rolloutapp.RuntimeConfig{
		Enabled:      true,
		PolicyFile:   policyPath,
		PolicySHA256: policyDigest,
		CandidateUpstreams: map[string]string{
			"content": "http://candidate-content:18080",
		},
	}
}
