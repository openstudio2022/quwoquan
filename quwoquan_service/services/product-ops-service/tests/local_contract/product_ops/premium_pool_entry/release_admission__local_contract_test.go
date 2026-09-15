package local_contract

import (
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/premium_pool_entry/contract/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestExactAdmissionsPreserveAAndBAndRevokeTogether(t *testing.T) {
	now := time.Now().UTC()
	source := generated.ReleaseCandidateObjectIdentity{Release: generated.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseId: "A", ManifestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, ObjectType: "content.post", ObjectId: "p", SourceVersion: 1, SourceDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
	input := model.UpsertInput{ContentID: "p", Scope: "global", QualityScore: .9, QualityAdmission: "approved", AuditID: "audit", SupplySource: "qwq_data", ExpiresAt: now.Add(time.Hour), ReleaseSource: &source}
	a, err := model.Upsert(nil, input, now)
	if err != nil {
		t.Fatal(err)
	}
	source.Release.ReleaseId = "B"
	b, err := model.Upsert(&a, input, now)
	if err != nil {
		t.Fatal(err)
	}
	if len(a.ReleaseAdmissions) != 1 || len(b.ReleaseAdmissions) != 2 {
		t.Fatal("candidate overwrite")
	}
	revoked, err := b.Takedown(now)
	if err != nil {
		t.Fatal(err)
	}
	for _, member := range revoked.ReleaseAdmissions {
		if member.Status != "takedown_ejected" || member.AdmissionDigest != model.AdmissionDigest(member) {
			t.Fatal("revocation incomplete")
		}
	}
	if b.ReleaseAdmissions[0].Status != "active" {
		t.Fatal("mutated previous state")
	}
}
