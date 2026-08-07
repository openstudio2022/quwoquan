// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
package local_contract

import (
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	circleapp "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

// Circle is the owner object of the `circle.circle` search registration, so its
// eligibility predicate and its Document projector are contract facts declared in
// object.yaml.search_policy. These tests are the projector evidence that
// registration requires.

func TestCircleSearchEligibleAdmitsOnlyActivePublicCircles(t *testing.T) {
	eligible := searchableCircle("circle-1")
	if !circleapp.CircleSearchEligible(eligible) {
		t.Fatal("active + public circle must be search eligible")
	}

	private := searchableCircle("circle-private")
	private.Visibility = model.CircleVisibilityPrivate
	if circleapp.CircleSearchEligible(private) {
		t.Fatal("private circle must never enter the shared index")
	}

	archived := searchableCircle("circle-archived")
	archived.Status = model.CircleStatusArchived
	if circleapp.CircleSearchEligible(archived) {
		t.Fatal("archived circle must never enter the shared index")
	}
}

func TestProjectCircleToSearchDocumentCarriesCanonicalAnchors(t *testing.T) {
	circle := searchableCircle("circle-1")
	document := circleapp.ProjectCircleToSearchDocument(circle)

	if document.ObjectType != rtsearch.ObjectTypeCircle {
		t.Fatalf("objectType=%q want=%q", document.ObjectType, rtsearch.ObjectTypeCircle)
	}
	if document.ObjectID != circle.ID || document.Title != circle.Name {
		t.Fatalf("identity diverged: document=%+v circle=%+v", document, circle)
	}
	if document.Visibility != string(model.CircleVisibilityPublic) {
		t.Fatalf("visibility=%q must round-trip the aggregate value", document.Visibility)
	}
	if got := document.Popularity; got != float64(circle.MemberCount+circle.PostCount) {
		t.Fatalf("popularity=%v must combine member and post counts", got)
	}
	for key, want := range map[string]string{
		"circleId":            circle.ID,
		"circleName":          circle.Name,
		"domainId":            circle.DomainID,
		"linkedHomepageId":    circle.LinkedHomepageID,
		"linkedHomepageTitle": circle.LinkedHomepageTitle,
	} {
		if document.Fields[key] != want {
			t.Fatalf("Fields[%q]=%q want=%q", key, document.Fields[key], want)
		}
	}
	// categoryId falls back through category -> domainId -> "all" so the native
	// facets and the index agree on one bucket.
	if document.Fields["categoryId"] != circle.Category {
		t.Fatalf("categoryId=%q want=%q", document.Fields["categoryId"], circle.Category)
	}
	uncategorised := searchableCircle("circle-2")
	uncategorised.Category = ""
	uncategorised.DomainID = ""
	if got := circleapp.ProjectCircleToSearchDocument(uncategorised).Fields["categoryId"]; got != "all" {
		t.Fatalf("uncategorised categoryId=%q want=all", got)
	}
}

func TestProjectCircleToSearchDocumentKeepsIndexedFieldsMapped(t *testing.T) {
	// Only anchor fields are promoted to indexed top-level ES properties; the rest
	// stay inside the non-indexed payload. A projector key that silently expects
	// to be searchable would be invisible without this assertion.
	indexed := es.DocumentToIndex(circleapp.ProjectCircleToSearchDocument(searchableCircle("circle-1")))
	if _, mapped := indexed["circleId"]; mapped {
		t.Fatal("circleId is payload-only and must not become a top-level ES field")
	}
	payload, ok := indexed["payload"].(map[string]any)
	if !ok {
		t.Fatalf("payload missing from indexed document: %+v", indexed)
	}
	if payload["circleId"] != "circle-1" {
		t.Fatalf("payload circleId=%v want=circle-1", payload["circleId"])
	}
	if indexed["objectType"] != rtsearch.ObjectTypeCircle {
		t.Fatalf("objectType=%v want=%q", indexed["objectType"], rtsearch.ObjectTypeCircle)
	}
}

func searchableCircle(id string) model.Circle {
	return model.Circle{
		ID:                  id,
		Name:                "骑行圈",
		Description:         "路线与装备",
		CoverUrl:            "https://cdn.example.com/cover.png",
		Category:            "sports",
		SubCategory:         "cycling",
		DomainID:            "outdoor",
		Tags:                []string{"骑行"},
		MemberCount:         12,
		PostCount:           7,
		Status:              model.CircleStatusActive,
		Visibility:          model.CircleVisibilityPublic,
		Kind:                model.CircleKindInterest,
		LinkedHomepageID:    "homepage-1",
		LinkedHomepageTitle: "西湖",
		UpdatedAt:           time.Date(2026, 8, 7, 0, 0, 0, 0, time.UTC),
	}
}
