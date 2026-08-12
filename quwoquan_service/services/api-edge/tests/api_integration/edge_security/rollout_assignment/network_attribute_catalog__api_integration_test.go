// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
// readiness_case: production-rollout-network-catalog-api
package api_integration

import (
	"context"
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/networkcatalog"
)

var networkCatalogAllocationKey = []byte("0123456789abcdef0123456789abcdef")

func TestCatalogMiddlewareUsesOnlyTrustedSourceAndKeepsUnknownStable(t *testing.T) {
	policy := networkCatalogPolicy()
	resolver := loadNetworkCatalog(t, policy)
	evaluator, err := application.NewEvaluator(
		policy,
		networkCatalogAllocationKey,
		&catalogAssignmentStore{values: map[string]bool{}},
		30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}

	type result struct {
		target  domain.Target
		region  string
		carrier string
	}
	results := make([]result, 0, 2)
	handler := httpadapter.Middleware(
		evaluator,
		resolver,
		"X-Edge-Client-IP",
		nil,
	)(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		results = append(results, result{
			target:  application.TargetFromContext(request.Context()),
			region:  request.Header.Get("X-Client-Region-Code"),
			carrier: request.Header.Get("X-Client-Carrier"),
		})
		response.WriteHeader(http.StatusNoContent)
	}))

	knownRequest := catalogRolloutRequest(t, policy, "known", "203.0.113.9")
	knownRequest.Header.Set("X-Client-Region-Code", "spoofed-region")
	knownRequest.Header.Set("X-Client-Carrier", "spoofed-carrier")
	knownResponse := httptest.NewRecorder()
	handler.ServeHTTP(knownResponse, knownRequest)
	if knownResponse.Code != http.StatusNoContent {
		t.Fatalf("known response=%d body=%s", knownResponse.Code, knownResponse.Body.String())
	}

	unknownRequest := catalogRolloutRequest(t, policy, "unknown", "198.51.100.9")
	unknownRequest.Header.Set("X-Client-Region-Code", "gd")
	unknownRequest.Header.Set("X-Client-Carrier", "chinatelecom")
	unknownResponse := httptest.NewRecorder()
	handler.ServeHTTP(unknownResponse, unknownRequest)
	if unknownResponse.Code != http.StatusNoContent {
		t.Fatalf("unknown response=%d body=%s", unknownResponse.Code, unknownResponse.Body.String())
	}

	if len(results) != 2 {
		t.Fatalf("results=%d", len(results))
	}
	if results[0] != (result{target: domain.TargetCandidate, region: "gd", carrier: "chinatelecom"}) {
		t.Fatalf("known result=%+v", results[0])
	}
	if results[1] != (result{target: domain.TargetStable, region: "unknown", carrier: "unknown"}) {
		t.Fatalf("unknown result=%+v", results[1])
	}
}

func catalogRolloutRequest(
	t *testing.T,
	policy domain.Policy,
	prefix string,
	trustedSource string,
) *http.Request {
	t.Helper()
	deviceActorID := ""
	for index := 0; index < 100000; index++ {
		candidate := fmt.Sprintf("%s-device-%d", prefix, index)
		bucket, err := domain.Bucket(networkCatalogAllocationKey, policy, "android", candidate)
		if err != nil {
			t.Fatal(err)
		}
		if bucket < 500 {
			deviceActorID = candidate
			break
		}
	}
	if deviceActorID == "" {
		t.Fatal("no deterministic 5 percent subject found")
	}
	request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
	request.Header.Set("X-Edge-Client-IP", trustedSource)
	request.Header.Set("X-Client-Device-Platform", "android")
	request.Header.Set("X-Client-App-Version", "1.9.0")
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{DeviceActorID: deviceActorID},
	}))
}

func loadNetworkCatalog(t *testing.T, policy domain.Policy) *networkcatalog.Resolver {
	t.Helper()
	raw := []byte(`schema: api-edge-network-attribute-catalog/v1
entries:
  - cidr: 203.0.113.0/24
    region: gd
    carrier: chinatelecom
`)
	path := filepath.Join(t.TempDir(), "network_attribute_catalog.yaml")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	resolver, err := networkcatalog.Load(application.NetworkAttributeCatalogConfig{
		Enabled: true,
		File:    path,
		SHA256:  fmt.Sprintf("sha256:%x", sha256.Sum256(raw)),
	}, policy)
	if err != nil {
		t.Fatal(err)
	}
	return resolver
}

func networkCatalogPolicy() domain.Policy {
	stages := make(map[string]domain.Stage)
	for name, basisPoints := range map[string]int{
		"canary": 0,
		"5":      500,
		"20":     2000,
		"50":     5000,
		"100":    10000,
	} {
		stage := domain.Stage{
			BasisPoints: basisPoints,
			AppVersions: domain.Selector{Mode: "supported"},
			Platforms: domain.Selector{
				Mode: "include", Values: []string{"android", "ios", "web"},
			},
			Regions:  domain.Selector{Mode: "include", Values: []string{"gd"}},
			Carriers: domain.Selector{Mode: "include", Values: []string{"chinatelecom"}},
		}
		if name == "100" {
			stage.Regions = domain.Selector{Mode: "all"}
			stage.Carriers = domain.Selector{Mode: "all"}
		}
		stages[name] = stage
	}
	return domain.Policy{
		Enabled: true, CampaignID: "network-catalog-test",
		CandidateDigest: "sha256:" + strings.Repeat("a", 64),
		AllocationKeyID: "network-catalog-key", SubjectKind: domain.SubjectKindDeviceActor,
		Stage: "5", Status: "active", AssignmentTTLDaysAfterCampaign: 30,
		Stages: stages,
	}
}

type catalogAssignmentStore struct {
	mu     sync.Mutex
	values map[string]bool
}

func (store *catalogAssignmentStore) IsCandidate(
	_ context.Context,
	campaignID string,
	subjectDigest string,
) (bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.values[campaignID+":"+subjectDigest], nil
}

func (store *catalogAssignmentStore) AssignCandidate(
	_ context.Context,
	campaignID string,
	subjectDigest string,
	_ time.Duration,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.values[campaignID+":"+subjectDigest] = true
	return nil
}

func (*catalogAssignmentStore) Ping(context.Context) error { return nil }
