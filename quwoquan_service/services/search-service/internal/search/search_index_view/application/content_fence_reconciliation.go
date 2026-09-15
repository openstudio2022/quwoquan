package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	msg "quwoquan_service/runtime/messaging"
	rt "quwoquan_service/runtime/search"
	wire "quwoquan_service/services/search-service/generated/search/search_index_view/commitreceipt"
	"reflect"
	"time"
)

type ContentFenceCommitReader interface {
	ReadCommit(context.Context, wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error)
}
type ContentFenceProofReader interface {
	VerifyFenceCandidate(context.Context, rt.ReleaseCandidateBinding) (string, error)
}
type ContentFenceReceipt struct {
	EventDigest         string    `bson:"eventDigest"`
	ScopeDigest         string    `bson:"scopeDigest"`
	Revision            int64     `bson:"revision"`
	PayloadDigest       string    `bson:"payloadDigest"`
	ProofEvidenceDigest string    `bson:"proofEvidenceDigest"`
	Outcome             string    `bson:"outcome"`
	ConsumedAt          time.Time `bson:"consumedAt"`
}
type ContentFenceReceiptStore interface {
	FindFenceReceipt(context.Context, string) (ContentFenceReceipt, bool, error)
	SaveFenceReceipt(context.Context, ContentFenceReceipt) error
}
type ContentFenceReconciler struct {
	store       ContentFenceReceiptStore
	commits     ContentFenceCommitReader
	current     ContentCreatorFenceReader
	proofs      ContentFenceProofReader
	environment string
}

func NewContentFenceReconciler(store ContentFenceReceiptStore, commits ContentFenceCommitReader, current ContentCreatorFenceReader, proofs ContentFenceProofReader, environment string) (*ContentFenceReconciler, error) {
	if store == nil || commits == nil || current == nil || proofs == nil || environment == "" {
		return nil, errors.New("Content fence reconciliation dependencies required")
	}
	return &ContentFenceReconciler{store, commits, current, proofs, environment}, nil
}
func fenceTransitionDigest(p wire.ContentReleaseFenceChangedPayload) string {
	raw, _ := json.Marshal(p)
	return postDigest(json.RawMessage(raw))
}
func validReconcileFence(f wire.ContentActiveReleaseFence) bool {
	if f.Environment == "" || f.SourceOwner != "qwq_data" {
		return false
	}
	if !f.Found {
		return f.ReleaseId == "" && f.ManifestDigest == "" && f.Revision == 0 && f.ProjectionVersion == 0 && f.ActivatedAt == nil
	}
	return (rt.ReleaseCandidateBinding{Environment: f.Environment, SourceOwner: f.SourceOwner, ReleaseID: f.ReleaseId, ManifestDigest: f.ManifestDigest}).Validate() == nil && f.Revision > 0 && f.ProjectionVersion > 0 && f.ActivatedAt != nil && !f.ActivatedAt.IsZero()
}
func (r *ContentFenceReconciler) ApplyContentPostDelivery(ctx context.Context, d msg.StreamDelivery) error {
	if d.Stream != "events.content.post_lifecycle" || d.ID == "" {
		return ErrContentPostConflict
	}
	fields := map[string]string{}
	for _, f := range d.Fields {
		if _, ok := fields[f.Name]; ok {
			return ErrContentPostConflict
		}
		fields[f.Name] = f.Value
	}
	if fields["eventType"] != "ContentReleaseFenceChanged" || fields["aggregateType"] != "Post" {
		return ErrContentPostConflict
	}
	var p wire.ContentReleaseFenceChangedPayload
	raw := []byte(fields["payload"])
	if err := strictPostPayload(raw, &p); err != nil {
		return err
	}
	var presence map[string]map[string]json.RawMessage
	if json.Unmarshal(raw, &presence) != nil {
		return ErrContentPostConflict
	}
	for _, key := range []string{"before", "after"} {
		if _, ok := presence[key]["activatedAt"]; !ok {
			return ErrContentPostConflict
		}
	}
	a, b := p.After, p.Before
	if !validReconcileFence(a) || !validReconcileFence(b) || !a.Found || a.Environment != r.environment || b.Environment != a.Environment || b.SourceOwner != a.SourceOwner || a.Revision != b.Revision+1 || fields["aggregateId"] != a.Environment+"/"+a.SourceOwner || fields["aggregateVersion"] != fmt.Sprint(a.Revision) {
		return ErrContentPostConflict
	}
	expectedID := "content-release-fence:" + postDigest([]any{a.Environment, a.SourceOwner, a.Revision})[7:]
	occurrence, err := time.Parse(time.RFC3339Nano, fields["occurredAt"])
	if err != nil || a.ActivatedAt == nil || !occurrence.Equal(*a.ActivatedAt) || fields["eventId"] != expectedID {
		return ErrContentPostConflict
	}
	digest := fenceTransitionDigest(p)
	eventDigest := postDigest(expectedID)
	prior, found, err := r.store.FindFenceReceipt(ctx, eventDigest)
	if err != nil {
		return err
	}
	if found {
		if prior.PayloadDigest != digest {
			return ErrContentPostConflict
		}
		return nil
	}
	current, err := r.current.Read(ctx)
	if err != nil {
		return err
	}
	currentWire := wire.ContentActiveReleaseFence{Found: current.Found, Environment: current.Environment, SourceOwner: current.SourceOwner, ReleaseId: current.ReleaseID, ManifestDigest: current.ManifestDigest, Revision: current.Revision, ProjectionVersion: current.ProjectionVersion, ActivatedAt: current.ActivatedAt}
	if !validReconcileFence(currentWire) || current.Environment != r.environment || current.SourceOwner != a.SourceOwner || current.Revision < a.Revision {
		return ErrContentPostConflict
	}
	q := wire.ReadContentReleaseCommitReceiptQuery{Release: wire.ReleaseCandidateBinding{Environment: a.Environment, SourceOwner: a.SourceOwner, ReleaseId: a.ReleaseId, ManifestDigest: a.ManifestDigest}, Expected: b}
	receipt, err := r.commits.ReadCommit(ctx, q)
	if err != nil {
		return err
	}
	if receipt.EventId != expectedID || receipt.PayloadDigest != digest || !reflect.DeepEqual(receipt.Transition, p) {
		return ErrContentPostConflict
	}
	proofDigest := receipt.PayloadDigest
	outcome := "superseded"
	if current.Revision == a.Revision {
		if !reflect.DeepEqual(currentWire, a) {
			return ErrContentPostConflict
		}
		proofDigest, err = r.proofs.VerifyFenceCandidate(ctx, rt.ReleaseCandidateBinding{Environment: a.Environment, SourceOwner: a.SourceOwner, ReleaseID: a.ReleaseId, ManifestDigest: a.ManifestDigest})
		if err != nil {
			return err
		}
		if proofDigest == "" {
			return ErrContentPostConflict
		}
		outcome = "reconciled"
	}
	return r.store.SaveFenceReceipt(ctx, ContentFenceReceipt{eventDigest, postDigest([]string{a.Environment, a.SourceOwner}), a.Revision, digest, proofDigest, outcome, time.Now().UTC()})
}
