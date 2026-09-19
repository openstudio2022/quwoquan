// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package feed_delivery_page_test

import (
	"math"
	"strings"
	"testing"
	"time"

	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

func TestPageValidationEnforcesFixedLifetimeAndFieldBudgets(t *testing.T) {
	now := time.Date(2026, 7, 29, 8, 0, 0, 0, time.UTC)
	page := validPageForTest(t, now)
	if err := page.Validate(now); err != nil {
		t.Fatalf("valid page rejected: %v", err)
	}

	tests := []struct {
		name   string
		mutate func(*deliverymodel.Page)
	}{
		{name: "non fixed ttl", mutate: func(page *deliverymodel.Page) { page.ExpiresAt = page.ExpiresAt.Add(-time.Second) }},
		{name: "unbounded post id", mutate: func(page *deliverymodel.Page) {
			page.Items[0].PostID = strings.Repeat("p", deliverymodel.MaximumPostIDBytes+1)
		}},
		{name: "non finite score", mutate: func(page *deliverymodel.Page) { page.Items[0].QualityScore = math.Inf(1) }},
		{name: "unbounded cursor", mutate: func(page *deliverymodel.Page) {
			page.OutboundCursor = strings.Repeat("c", deliverymodel.MaximumCursorBytes+1)
		}},
		{name: "depth without previous", mutate: func(page *deliverymodel.Page) { page.Depth = 1 }},
		{name: "too many items", mutate: func(page *deliverymodel.Page) {
			page.Items = make([]deliverymodel.PostReference, deliverymodel.MaximumItems+1)
			for index := range page.Items {
				page.Items[index].PostID = strings.Repeat("p", index+1)
			}
		}},
		{name: "duplicate post", mutate: func(page *deliverymodel.Page) {
			page.Items = append(page.Items, page.Items[0])
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			candidate := page
			candidate.Items = append([]deliverymodel.PostReference(nil), page.Items...)
			test.mutate(&candidate)
			if err := candidate.Validate(now); err == nil {
				t.Fatal("invalid page passed validation")
			}
		})
	}
}

func TestScopeCapacityMatchesMaximumCursorDepth(t *testing.T) {
	if deliverymodel.MaximumActivePerScope != 8*deliverymodel.MaximumDepth {
		t.Fatalf("active page quota=%d, want eight windows x cursor depth=%d", deliverymodel.MaximumActivePerScope, deliverymodel.MaximumDepth)
	}
}

func TestTerminalPageAllowsAnEmptyOutboundCursor(t *testing.T) {
	now := time.Date(2026, 7, 29, 8, 0, 0, 0, time.UTC)
	page := validPageForTest(t, now)
	page.OutboundCursor = ""
	if err := page.Validate(now); err != nil {
		t.Fatalf("terminal delivery page rejected: %v", err)
	}
}

func validPageForTest(t *testing.T, now time.Time) deliverymodel.Page {
	t.Helper()
	pageID, err := deliverymodel.NewID()
	if err != nil {
		t.Fatalf("new page id: %v", err)
	}
	return deliverymodel.Page{
		DeliveryPageID: pageID,
		ScopeHash:      deliverymodel.ScopeHash("actor/session/route/20"),
		FeedRequestID:  "frq_local_contract",
		PageSize:       20,
		Items: []deliverymodel.PostReference{{
			PostID:       "post-1",
			QualityScore: 0.9,
			RecallPath:   "premium_pool",
		}},
		OutboundCursor: "fc.local-contract",
		CreatedAt:      now,
		ExpiresAt:      now.Add(deliverymodel.TTL),
	}
}
