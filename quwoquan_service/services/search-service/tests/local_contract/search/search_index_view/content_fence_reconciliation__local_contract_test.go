package local_contract_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	msg "quwoquan_service/runtime/messaging"
	rt "quwoquan_service/runtime/search"
	wire "quwoquan_service/services/search-service/generated/search/search_index_view/commitreceipt"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"testing"
	"time"
)

type fenceReceiptFixture struct {
	receipt           *app.ContentFenceReceipt
	commit            wire.ContentReleaseCommitReceipt
	current           app.ContentCreatorFence
	reads, proofReads int
	missing           bool
}

func (f *fenceReceiptFixture) FindFenceReceipt(context.Context, string) (app.ContentFenceReceipt, bool, error) {
	if f.receipt == nil {
		return app.ContentFenceReceipt{}, false, nil
	}
	return *f.receipt, true, nil
}
func (f *fenceReceiptFixture) SaveFenceReceipt(_ context.Context, r app.ContentFenceReceipt) error {
	f.receipt = &r
	return nil
}
func (f *fenceReceiptFixture) ReadCommit(context.Context, wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error) {
	f.reads++
	if f.missing {
		return wire.ContentReleaseCommitReceipt{}, errors.New("missing exact old receipt")
	}
	return f.commit, nil
}
func (f *fenceReceiptFixture) Read(context.Context) (app.ContentCreatorFence, error) {
	return f.current, nil
}
func (f *fenceReceiptFixture) VerifyFenceCandidate(context.Context, rt.ReleaseCandidateBinding) (string, error) {
	f.proofReads++
	return "sha256:" + fmt.Sprintf("%064x", 1), nil
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 仅application调用纪律，独立Mongo/签名HTTP证据不能由此替代。
func TestFenceReconciliationRequiresExactCommitAndDoesNotReprepare(t *testing.T) {
	now := time.Date(2026, 9, 13, 0, 0, 0, 0, time.UTC)
	after := wire.ContentActiveReleaseFence{Found: true, Environment: "alpha", SourceOwner: "qwq_data", ReleaseId: "a", ManifestDigest: "sha256:" + fmt.Sprintf("%064x", 1), Revision: 1, ProjectionVersion: 2, ActivatedAt: &now}
	before := wire.ContentActiveReleaseFence{Environment: "alpha", SourceOwner: "qwq_data"}
	p := wire.ContentReleaseFenceChangedPayload{Before: before, After: after}
	raw, _ := json.Marshal(p)
	sum := sha256.Sum256(raw)
	identity, _ := json.Marshal([]any{"alpha", "qwq_data", int64(1)})
	idsum := sha256.Sum256(identity)
	eventID := "content-release-fence:" + hex.EncodeToString(idsum[:])
	f := &fenceReceiptFixture{commit: wire.ContentReleaseCommitReceipt{EventId: eventID, Transition: p, PayloadDigest: "sha256:" + hex.EncodeToString(sum[:])}, current: app.ContentCreatorFence{Found: true, Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "a", ManifestDigest: after.ManifestDigest, Revision: 1, ProjectionVersion: 2, ActivatedAt: &now}}
	r, err := app.NewContentFenceReconciler(f, f, f, f, "alpha")
	if err != nil {
		t.Fatal(err)
	}
	d := msg.StreamDelivery{Stream: "events.content.post_lifecycle", ID: "1-0", Fields: []msg.DurableField{{Name: "eventType", Value: "ContentReleaseFenceChanged"}, {Name: "aggregateType", Value: "Post"}, {Name: "aggregateId", Value: "alpha/qwq_data"}, {Name: "aggregateVersion", Value: "1"}, {Name: "occurredAt", Value: now.Format(time.RFC3339Nano)}, {Name: "eventId", Value: eventID}, {Name: "payload", Value: string(raw)}}}
	if err = r.ApplyContentPostDelivery(t.Context(), d); err != nil {
		t.Fatal(err)
	}
	if f.receipt.Outcome != "reconciled" || f.proofReads != 1 {
		t.Fatal(f)
	}
	if err = r.ApplyContentPostDelivery(t.Context(), d); err != nil || f.reads != 1 {
		t.Fatal("replay re-read", err, f.reads)
	}
	f.receipt = nil
	f.current.Revision = 3
	f.missing = true
	if err = r.ApplyContentPostDelivery(t.Context(), d); err == nil || f.receipt != nil {
		t.Fatal("old without exact receipt accepted")
	}
	f.missing = false
	if err = r.ApplyContentPostDelivery(t.Context(), d); err != nil || f.receipt.Outcome != "superseded" || f.proofReads != 1 {
		t.Fatal("late commit", err)
	}
	f.receipt = nil
	f.current.Revision = 0
	if err = r.ApplyContentPostDelivery(t.Context(), d); err == nil {
		t.Fatal("future accepted")
	}
}
