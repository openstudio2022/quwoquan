// spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-003
// readiness_case: production-rollout-decision-local
package local_contract

import (
	"context"
	"errors"
	"fmt"
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
