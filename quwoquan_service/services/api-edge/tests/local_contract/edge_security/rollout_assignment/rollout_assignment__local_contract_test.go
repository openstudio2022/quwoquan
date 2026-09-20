// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
// readiness_case: production-rollout-decision-local
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
)

var testAllocationKey = []byte("0123456789abcdef0123456789abcdef")

func TestPlatformStratifiedDistributionAndMonotonicThresholds(t *testing.T) {
	for _, platform := range []string{"android", "ios", "web"} {
		counts := map[string]int{}
		sets := map[string]map[string]struct{}{}
		for _, stage := range []string{"5", "20", "50"} {
			policy := rolloutPolicy(stage)
			selected := map[string]struct{}{}
			for index := 0; index < 100000; index++ {
				deviceID := fmt.Sprintf("%s-install-%06d", platform, index)
				bucket, err := domain.Bucket(testAllocationKey, policy, platform, deviceID)
				if err != nil {
					t.Fatal(err)
				}
				if bucket < policy.Stages[stage].BasisPoints {
					selected[deviceID] = struct{}{}
				}
			}
			counts[stage] = len(selected)
			sets[stage] = selected
		}
		assertRange(t, platform+" 5", counts["5"], 4500, 5500)
		assertRange(t, platform+" 20", counts["20"], 19000, 21000)
		assertRange(t, platform+" 50", counts["50"], 49000, 51000)
		assertSubset(t, sets["5"], sets["20"])
		assertSubset(t, sets["20"], sets["50"])
	}
}

func TestAssignmentSurvivesNetworkAndAccountChanges(t *testing.T) {
	store := newMemoryStore()
	policy := rolloutPolicy("5")
	policy.Stages["5"] = domain.Stage{
		BasisPoints: 500,
		AppVersions: domain.Selector{Mode: "supported"},
		Platforms:   domain.Selector{Mode: "include", Values: []string{"android", "ios", "web"}},
		Regions:     domain.Selector{Mode: "include", Values: []string{"440000"}},
		Carriers:    domain.Selector{Mode: "include", Values: []string{"chinatelecom"}},
	}
	policy.Stages["canary"] = policy.Stages["5"]
	canaryStage := policy.Stages["canary"]
	canaryStage.BasisPoints = 0
	policy.Stages["canary"] = canaryStage
	stage20 := policy.Stages["5"]
	stage20.BasisPoints = 2000
	policy.Stages["20"] = stage20
	stage50 := policy.Stages["5"]
	stage50.BasisPoints = 5000
	policy.Stages["50"] = stage50
	policy.Stages["100"] = terminalStage()
	policy.InternalCanary.DeviceActorIDs = []string{"device-1"}
	evaluator, err := application.NewEvaluator(policy, testAllocationKey, store, 30*24*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	first, err := evaluator.Decide(context.Background(), application.Subject{
		DeviceActorID: "device-1", AccountID: "account-1", Platform: "android",
		AppVersion: "1.9.0", Region: "440000", Carrier: "chinatelecom",
	})
	if err != nil {
		t.Fatal(err)
	}
	if first.Target != domain.TargetCandidate {
		t.Fatalf("first target=%s", first.Target)
	}
	second, err := evaluator.Decide(context.Background(), application.Subject{
		DeviceActorID: "device-1", AccountID: "account-2", Platform: "android",
		AppVersion: "1.9.0", Region: "110000", Carrier: "chinaunicom",
	})
	if err != nil {
		t.Fatal(err)
	}
	if second.Target != domain.TargetCandidate || second.Reason != "existing_assignment" {
		t.Fatalf("second decision=%+v", second)
	}
}

func TestMissingTrustedSubjectIsAlwaysStable(t *testing.T) {
	evaluator, err := application.NewEvaluator(
		rolloutPolicy("50"), testAllocationKey, newMemoryStore(), 30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}
	decision, err := evaluator.Decide(context.Background(), application.Subject{
		Platform: "android", AppVersion: "1.9.0",
	})
	if err != nil {
		t.Fatal(err)
	}
	if decision.Target != domain.TargetStable || decision.Reason != "missing_rollout_subject" {
		t.Fatalf("decision=%+v", decision)
	}
}

func TestAssignmentFailureIsCriticalAndNeverRebucketed(t *testing.T) {
	store := newMemoryStore()
	store.failure = errors.New("redis unavailable")
	evaluator, err := application.NewEvaluator(
		rolloutPolicy("50"), testAllocationKey, store, 30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = evaluator.Decide(context.Background(), application.Subject{
		DeviceActorID: "device-1", Platform: "android", AppVersion: "1.9.0",
	})
	if !errors.Is(err, application.ErrAssignmentStateUnavailable) {
		t.Fatalf("error=%v", err)
	}
}

func TestPolicyRejectsShrinkingPlatformAudience(t *testing.T) {
	policy := rolloutPolicy("20")
	stage := policy.Stages["20"]
	stage.Platforms.Values = []string{"android"}
	policy.Stages["20"] = stage
	if err := policy.Validate(); err == nil {
		t.Fatal("shrinking platform audience must fail")
	}
}

func TestValidationRingRequiresUserAndTrustedIPMatch(t *testing.T) {
	policy := rolloutPolicy("canary")
	policy.ValidationRing = domain.ValidationRing{
		Enabled:   true,
		RequireIP: true,
		Route: domain.RouteBinding{
			Target:              domain.TargetCandidate,
			DeploymentInstance:  "prevalidate",
			CandidateID:         policy.CandidateDigest,
			ArtifactDigest:      "sha256:" + strings.Repeat("a", 64),
			RuntimeConfigDigest: "sha256:" + strings.Repeat("c", 64),
		},
	}
	policy.AppVersions = []domain.AppVersion{{
		Platform: "ios", DisplayVersion: "1.9.0", BuildNumber: "19001",
		ArtifactDigest: "sha256:" + strings.Repeat("a", 64),
	}}
	policy.InternalCanary = domain.InternalCanary{
		AccountIDs:     []string{"account-1"},
		TrustedIPCidrs: []string{"203.0.113.0/24"},
	}
	evaluator, err := application.NewEvaluator(policy, testAllocationKey, newMemoryStore(), 30*24*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	base := application.Subject{
		DeviceActorID: "device-1", AccountID: "account-1", Platform: "ios",
		AppVersion: "1.9.0", AppBuild: "19001", ClientIP: "203.0.113.10",
	}
	allowed, err := evaluator.Decide(context.Background(), base)
	if err != nil || allowed.Target != domain.TargetCandidate {
		t.Fatalf("allowed decision=%+v err=%v", allowed, err)
	}
	// 连续复用同一 evaluator/store，撤销条件不得被旧 assignment 绕过。
	for name, subject := range map[string]application.Subject{
		"wrong user":  {DeviceActorID: "device-1", AccountID: "account-2", Platform: "ios", AppVersion: "1.9.0", AppBuild: "19001", ClientIP: "203.0.113.10"},
		"wrong ip":    {DeviceActorID: "device-1", AccountID: "account-1", Platform: "ios", AppVersion: "1.9.0", AppBuild: "19001", ClientIP: "198.51.100.10"},
		"wrong build": {DeviceActorID: "device-1", AccountID: "account-1", Platform: "ios", AppVersion: "1.9.0", AppBuild: "19002", ClientIP: "203.0.113.10"},
	} {
		decision, decisionErr := evaluator.Decide(context.Background(), subject)
		if decisionErr != nil || decision.Target != domain.TargetStable {
			t.Fatalf("%s decision=%+v err=%v", name, decision, decisionErr)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-002
func validationPolicy() domain.Policy {
	policy := rolloutPolicy("canary")
	policy.CandidateUpstream = "https://candidate.example.invalid"
	policy.AppVersions = []domain.AppVersion{{Platform: "ios", DisplayVersion: "1.9.0", BuildNumber: "19001", ArtifactDigest: "sha256:" + strings.Repeat("a", 64)}}
	policy.InternalCanary = domain.InternalCanary{AccountIDs: []string{"account-1"}, TrustedIPCidrs: []string{"203.0.113.0/24"}}
	policy.ValidationRing = domain.ValidationRing{Enabled: true, RequireIP: true, Route: domain.RouteBinding{
		Target: domain.TargetCandidate, DeploymentInstance: "prevalidate", CandidateID: policy.CandidateDigest,
		ArtifactDigest: policy.AppVersions[0].ArtifactDigest, RuntimeConfigDigest: "sha256:" + strings.Repeat("c", 64),
	}}
	return policy
}

func TestValidationRingRechecksRevocationWithoutTouchingStickyStore(t *testing.T) {
	base := application.Subject{DeviceActorID: "device-1", AccountID: "account-1", Platform: "ios", AppVersion: "1.9.0", AppBuild: "19001", ClientIP: "203.0.113.10"}
	store := newMemoryStore()
	digest, err := domain.SubjectDigest(testAllocationKey, validationPolicy().CampaignID, base.DeviceActorID)
	if err != nil {
		t.Fatal(err)
	}
	store.values[validationPolicy().CampaignID+":"+digest] = true
	// store 读写都会报错，证明验证环不消费正式 campaign assignment。
	store.failure = errors.New("validation ring must not use sticky store")
	for _, revoke := range []string{"none", "user", "ip", "both", "version"} {
		policy := validationPolicy()
		subject := base
		switch revoke {
		case "user":
			policy.InternalCanary.AccountIDs = []string{}
		case "ip":
			policy.InternalCanary.TrustedIPCidrs = []string{}
		case "both":
			policy.InternalCanary = domain.InternalCanary{}
		case "version":
			subject.AppBuild = "19002"
		}
		evaluator, err := application.NewEvaluator(policy, testAllocationKey, store, time.Hour)
		if err != nil {
			t.Fatalf("%s: %v", revoke, err)
		}
		decision, err := evaluator.Decide(context.Background(), subject)
		want := domain.TargetStable
		if revoke == "none" {
			want = domain.TargetCandidate
		}
		if err != nil || decision.Target != want {
			t.Fatalf("%s: %+v %v want=%s", revoke, decision, err, want)
		}
	}
}

func TestValidationRingOptionalWhitelistMatrix(t *testing.T) {
	base := application.Subject{DeviceActorID: "device-1", AccountID: "account-1", Platform: "ios", AppVersion: "1.9.0", AppBuild: "19001", ClientIP: "203.0.113.10"}
	for _, tc := range []struct {
		name        string
		users, ips  []string
		requireIP   bool
		ip, version string
		want        domain.Target
	}{
		{"user-only", []string{"account-1"}, nil, false, "", "1.9.0", domain.TargetCandidate},
		{"ip-only", nil, []string{"203.0.113.0/24"}, false, base.ClientIP, "1.9.0", domain.TargetCandidate},
		{"both", []string{"account-1"}, []string{"203.0.113.0/24"}, false, base.ClientIP, "1.9.0", domain.TargetCandidate},
		{"none", nil, nil, false, base.ClientIP, "1.9.0", domain.TargetStable},
		{"empty-users", []string{}, []string{"203.0.113.0/24"}, false, base.ClientIP, "1.9.0", domain.TargetStable},
		{"empty-ip", []string{"account-1"}, []string{}, false, base.ClientIP, "1.9.0", domain.TargetStable},
		{"required-ip", []string{"account-1"}, nil, true, base.ClientIP, "1.9.0", domain.TargetStable},
		{"missing-trusted-ip", nil, []string{"203.0.113.0/24"}, false, "", "1.9.0", domain.TargetStable},
		{"wrong-version", []string{"account-1"}, nil, false, "", "1.8.0", domain.TargetStable},
		{"wrong-user", []string{"other"}, nil, false, "", "1.9.0", domain.TargetStable},
		{"wrong-ip", []string{"account-1"}, []string{"198.51.100.0/24"}, false, base.ClientIP, "1.9.0", domain.TargetStable},
	} {
		t.Run(tc.name, func(t *testing.T) {
			policy := validationPolicy()
			policy.ValidationRing.RequireIP = tc.requireIP
			policy.InternalCanary = domain.InternalCanary{AccountIDs: tc.users, TrustedIPCidrs: tc.ips}
			evaluator, err := application.NewEvaluator(policy, testAllocationKey, newMemoryStore(), time.Hour)
			if err != nil {
				t.Fatal(err)
			}
			subject := base
			subject.ClientIP = tc.ip
			subject.AppVersion = tc.version
			decision, err := evaluator.Decide(context.Background(), subject)
			if err != nil || decision.Target != tc.want {
				t.Fatalf("%+v %v want=%s", decision, err, tc.want)
			}
		})
	}
	policy := validationPolicy()
	policy.Enabled = false
	evaluator, err := application.NewEvaluator(policy, nil, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	decision, err := evaluator.Decide(context.Background(), base)
	if err != nil || decision.Target != domain.TargetStable {
		t.Fatalf("disabled: %+v %v", decision, err)
	}
}

func TestValidationRingRejectsRouteDriftAndNonCanonicalVersion(t *testing.T) {
	for _, mutation := range []string{"candidate", "artifact", "exposure", "instance", "stage", "version", "cidr"} {
		policy := validationPolicy()
		switch mutation {
		case "candidate":
			policy.ValidationRing.Route.CandidateID = "sha256:" + strings.Repeat("b", 64)
		case "artifact":
			policy.AppVersions[0].ArtifactDigest = "sha256:" + strings.Repeat("b", 64)
		case "exposure":
			policy.ValidationRing.Route.PublicExposure = true
		case "instance":
			policy.ValidationRing.Route.DeploymentInstance = "stable"
		case "stage":
			policy.Stage = "5"
		case "version":
			policy.AppVersions[0].DisplayVersion = "1.9.0-rc.1"
		case "cidr":
			policy.InternalCanary.TrustedIPCidrs = []string{"not-an-ip"}
		}
		if err := policy.Validate(); err == nil {
			t.Errorf("%s drift accepted", mutation)
		}
	}
}

func TestPolicyRejectsNonCanonicalStageThresholdAndCandidateDigest(t *testing.T) {
	policy := rolloutPolicy("5")
	stage := policy.Stages["5"]
	stage.BasisPoints = 501
	policy.Stages["5"] = stage
	if err := policy.Validate(); err == nil {
		t.Fatal("non-canonical stage threshold must fail")
	}

	policy = rolloutPolicy("5")
	policy.CandidateDigest = "candidate-latest"
	if err := policy.Validate(); err == nil {
		t.Fatal("non-canonical candidate digest must fail")
	}
}

func rolloutPolicy(stage string) domain.Policy {
	stages := map[string]domain.Stage{
		"canary": defaultStage(0), "5": defaultStage(500), "20": defaultStage(2000),
		"50": defaultStage(5000), "100": terminalStage(),
	}
	return domain.Policy{
		Enabled: true, CampaignID: "release-2026-08-10-001",
		CandidateDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		AllocationKeyID: "rollout-key-2026-01", SubjectKind: domain.SubjectKindDeviceActor,
		Stage: stage, Status: "active", AssignmentTTLDaysAfterCampaign: 30,
		InternalCanary: domain.InternalCanary{AccountIDs: []string{"ops-release-canary"}},
		Stages:         stages,
	}
}

func defaultStage(basisPoints int) domain.Stage {
	return domain.Stage{
		BasisPoints: basisPoints, AppVersions: domain.Selector{Mode: "supported"},
		Platforms: domain.Selector{Mode: "include", Values: []string{"android", "ios", "web"}},
		Regions:   domain.Selector{Mode: "all"}, Carriers: domain.Selector{Mode: "all"},
	}
}

func terminalStage() domain.Stage { return defaultStage(10000) }

func assertRange(t *testing.T, label string, got, minimum, maximum int) {
	t.Helper()
	if got < minimum || got > maximum {
		t.Fatalf("%s count=%d not in %d..%d", label, got, minimum, maximum)
	}
}

func assertSubset(t *testing.T, left, right map[string]struct{}) {
	t.Helper()
	for value := range left {
		if _, ok := right[value]; !ok {
			t.Fatalf("%s is not retained", value)
		}
	}
}

type memoryStore struct {
	mu      sync.Mutex
	values  map[string]bool
	failure error
}

func newMemoryStore() *memoryStore { return &memoryStore{values: map[string]bool{}} }

func (store *memoryStore) IsCandidate(_ context.Context, campaignID, subjectDigest string) (bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.failure != nil {
		return false, store.failure
	}
	return store.values[campaignID+":"+subjectDigest], nil
}

func (store *memoryStore) AssignCandidate(_ context.Context, campaignID, subjectDigest string, _ time.Duration) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.failure != nil {
		return store.failure
	}
	store.values[campaignID+":"+subjectDigest] = true
	return nil
}

func (store *memoryStore) Ping(context.Context) error { return store.failure }
