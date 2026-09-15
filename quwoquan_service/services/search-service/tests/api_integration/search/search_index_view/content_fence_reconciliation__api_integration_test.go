package api_integration

import (
	"context"
	"errors"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	store "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/contentfence"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 本用例仅验证真实Mongo独立fence凭据，不冒充candidate/proof或HTTP跨服务全链。
func TestContentFenceReceiptUniqueRevisionMongo(t *testing.T) {
	s := store.NewReconciliationStore(mongoDB)
	if err := s.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	// 摘要分别来自 UTF-8 seed event-a、scope、payload-a、proof 的真实 SHA256。
	r := app.ContentFenceReceipt{EventDigest: "sha256:2edb68c52e4b9cf2c91e5752b72821bb9c0f45373c9fe9143f85453a5c76bd90", ScopeDigest: "sha256:5f161c9149882e0e10124bc5dd5c11f0fbe8ec452edd52bcec76b01e9252cb33", Revision: 1, PayloadDigest: "sha256:d14eccd7caab56bb1b0042546d728172943278dedbb869603a0be39dd3b5d9e6", ProofEvidenceDigest: "sha256:c1cda26362828b69266512052b97cb3729e3b052e4ade47c0a1e3383defe73c7", Outcome: "reconciled", ConsumedAt: time.Now().UTC()}
	if err := s.SaveFenceReceipt(context.Background(), r); err != nil {
		t.Fatal(err)
	}
	if err := s.SaveFenceReceipt(context.Background(), r); err != nil {
		t.Fatal("replay", err)
	}
	r.PayloadDigest = "sha256:9d6f965ac832e40a5df6c06afe983e3b449c07b843ff51ce76204de05c690d11" // seed: different
	if err := s.SaveFenceReceipt(t.Context(), r); !errors.Is(err, app.ErrContentPostConflict) {
		t.Fatal("event mismatch", err)
	}
	r.EventDigest = "sha256:d39f0c068a401693da9a458bd96828cadc40559eb0441610a4a050532b6ae621" // seed: another-event
	if err := s.SaveFenceReceipt(t.Context(), r); !errors.Is(err, app.ErrContentPostConflict) {
		t.Fatal("same revision conflict", err)
	}
}
