package public

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	"reflect"
)

type ContentReleaseCommitReceiptReader interface {
	ReadContentReleaseCommitReceipt(context.Context, wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error)
}
type ContentReleaseCommitReceiptQueryFacade struct {
	reader ContentReleaseCommitReceiptReader
}

func NewContentReleaseCommitReceiptQueryFacade(reader ContentReleaseCommitReceiptReader) *ContentReleaseCommitReceiptQueryFacade {
	return &ContentReleaseCommitReceiptQueryFacade{reader}
}
func ValidateReleaseWireFence(f wire.ContentActiveReleaseFence) error {
	var t ActiveReleaseFence
	t = ActiveReleaseFence{Found: f.Found, Environment: f.Environment, SourceOwner: f.SourceOwner, ReleaseID: f.ReleaseId, ManifestDigest: f.ManifestDigest, Revision: f.Revision, ProjectionVersion: f.ProjectionVersion}
	if f.ActivatedAt != nil {
		t.ActivatedAt = *f.ActivatedAt
	}
	if !f.Found && f.ActivatedAt != nil {
		return ErrReleaseQueryInvalid
	}
	return ValidateActiveReleaseFence(ActiveReleaseFenceQuery{Environment: f.Environment, SourceOwner: f.SourceOwner}, t)
}
func ReleaseFenceEventID(f wire.ContentActiveReleaseFence) string {
	raw, _ := json.Marshal([]any{f.Environment, f.SourceOwner, f.Revision})
	sum := sha256.Sum256(raw)
	return "content-release-fence:" + hex.EncodeToString(sum[:])
}
func ReleaseFencePayloadDigest(p wire.ContentReleaseFenceChangedPayload) string {
	raw, _ := json.Marshal(p)
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}
func ValidateReleaseCommitReceipt(q wire.ReadContentReleaseCommitReceiptQuery, r wire.ContentReleaseCommitReceipt) error {
	if ValidateReleaseWireFence(q.Expected) != nil || ValidateReleaseWireFence(r.Transition.Before) != nil || ValidateReleaseWireFence(r.Transition.After) != nil {
		return ErrReleaseQueryInvalid
	}
	a, b := r.Transition.After, r.Transition.Before
	if !a.Found || a.Environment != b.Environment || a.SourceOwner != b.SourceOwner || a.Revision != b.Revision+1 || !reflect.DeepEqual(b, q.Expected) || a.Environment != q.Release.Environment || a.SourceOwner != q.Release.SourceOwner || a.ReleaseId != q.Release.ReleaseId || a.ManifestDigest != q.Release.ManifestDigest || r.EventId != ReleaseFenceEventID(a) || r.PayloadDigest != ReleaseFencePayloadDigest(r.Transition) {
		return ErrReleaseQueryInvalid
	}
	return nil
}
func (f *ContentReleaseCommitReceiptQueryFacade) Read(ctx context.Context, q wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error) {
	if f == nil || f.reader == nil {
		return wire.ContentReleaseCommitReceipt{}, ErrReleaseQueryNotReady
	}
	if ValidateReleaseWireFence(q.Expected) != nil || q.Release.Environment != q.Expected.Environment || q.Release.SourceOwner != q.Expected.SourceOwner || q.Release.ReleaseId == "" || !canonicalManifestDigestPattern.MatchString(q.Release.ManifestDigest) {
		return wire.ContentReleaseCommitReceipt{}, ErrReleaseQueryInvalid
	}
	r, err := f.reader.ReadContentReleaseCommitReceipt(ctx, q)
	if err != nil {
		return r, err
	}
	if err = ValidateReleaseCommitReceipt(q, r); err != nil {
		return wire.ContentReleaseCommitReceipt{}, fmt.Errorf("%w: committed transition mismatch", err)
	}
	return r, nil
}
