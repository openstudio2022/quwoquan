// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-004.t3
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/design.md#dec-005
package intersection_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"

	generated "quwoquan_service/services/content-service/generated/content/post"
)

// 交集策略身份（cohort）单一真相源：生成表常量 = 注册表 canonical 字节的 sha256，
// 水合出口把它盖章到每条下发 reason 上；端只回传、不展示。
func TestIntersectionPolicyDigestIsRegistryDigestAndStampedAsCohort(t *testing.T) {
	registryPath := filepath.Join(
		"..", "..", "..", "..", "..", "..", "..", "..",
		"services", "recommendation-service", "contracts", "recommendation",
		"recommendation_model_release", "intersection_kind_registry.yaml",
	)
	raw, err := os.ReadFile(registryPath)
	if err != nil {
		t.Fatalf("read intersection kind registry: %v", err)
	}
	sum := sha256.Sum256(raw)
	want := "sha256:" + hex.EncodeToString(sum[:])
	if generated.IntersectionPolicyDigest != want {
		t.Fatalf("generated IntersectionPolicyDigest %q must equal registry sha256 %q; rerun make codegen-rec-intersection",
			generated.IntersectionPolicyDigest, want)
	}
	if !strings.HasPrefix(generated.IntersectionPolicyDigest, "sha256:") {
		t.Fatalf("policy digest must be sha256-prefixed, got %q", generated.IntersectionPolicyDigest)
	}

	now := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	src := stubSource{facts: []IntersectionReasonView{
		displayReadyFactReason("ix_cohort", "identity", "sharedFollowees", "u1", "person", "陆衡", 2, 0.9),
	}}
	svc := NewIntersectionService(newTestRouter(t), WithIntersectionSource(src))
	fixedNow(svc, now)
	feed, err := svc.Feed(context.Background(), "viewer1", "recommend", 10)
	if err != nil {
		t.Fatalf("feed: %v", err)
	}
	if len(feed) != 1 {
		t.Fatalf("want 1 reason, got %d", len(feed))
	}
	if feed[0].Cohort != generated.IntersectionPolicyDigest {
		t.Fatalf("served reason must carry the policy cohort, got %q", feed[0].Cohort)
	}
}
