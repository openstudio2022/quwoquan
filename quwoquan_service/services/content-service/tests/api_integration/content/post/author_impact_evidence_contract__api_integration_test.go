// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// evidenceTargetResp mirrors IntersectionTargetView json shape.
type evidenceTargetResp struct {
	ObjectID   string `json:"objectId"`
	ObjectKind string `json:"objectKind"`
	RouteID    string `json:"routeId"`
}

// evidenceVisualResp mirrors IntersectionVisualView json shape.
type evidenceVisualResp struct {
	AssetKind   string              `json:"assetKind"`
	ImageURL    string              `json:"imageUrl"`
	DisplayName string              `json:"displayName"`
	Target      *evidenceTargetResp `json:"target"`
}

// evidenceItemResp mirrors AuthorImpactEvidenceItemView (projections/author_impact_evidence_item.yaml).
type evidenceItemResp struct {
	EvidenceID            string              `json:"evidenceId"`
	ImpactID              string              `json:"impactId"`
	HelpType              string              `json:"helpType"`
	Action                string              `json:"action"`
	IntersectionDimension string              `json:"intersectionDimension"`
	OccurredAt            string              `json:"occurredAt"`
	SummaryText           string              `json:"summaryText"`
	SampleVisual          *evidenceVisualResp `json:"sampleVisual"`
	ContentTarget         *evidenceTargetResp `json:"contentTarget"`
}

// evidencePageResp mirrors AuthorImpactEvidencePageView (projections/author_impact_evidence_page.yaml).
type evidencePageResp struct {
	ImpactID           string             `json:"impactId"`
	EvidenceSnapshotID string             `json:"evidenceSnapshotId"`
	TotalCount         int64              `json:"totalCount"`
	Items              []evidenceItemResp `json:"items"`
	NextCursor         string             `json:"nextCursor"`
	HasMore            bool               `json:"hasMore"`
}

func reportBehaviorRaw(t *testing.T, payload string) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("report behavior: expected 204, got %d: %s", rec.Code, rec.Body.String())
	}
}

// authorImpactSummaryItem is one rm_author_impact aggregation row (count + anchor).
type authorImpactSummaryItem struct {
	ImpactID string `json:"impactId"`
	Count    int64  `json:"count"`
}

func authorImpactSummary(t *testing.T, authorID string) []authorImpactSummaryItem {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/content/sub-accounts/"+authorID+"/author-impact", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("get author impact: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body struct {
		Items []authorImpactSummaryItem `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode author impact: %v", err)
	}
	return body.Items
}

// firstAuthorImpactID drills GET /author-impact and returns the (single) impactId
// that the app uses as the count-to-evidence drill-down anchor.
func firstAuthorImpactID(t *testing.T, authorID string) string {
	t.Helper()
	items := authorImpactSummary(t, authorID)
	if len(items) == 0 || strings.TrimSpace(items[0].ImpactID) == "" {
		t.Fatalf("author impact summary exposes no impactId drill-down anchor for %s", authorID)
	}
	return items[0].ImpactID
}

// authorImpactCountFor returns the summary count for one impactId (the number the
// app shows before drill-down). It must equal the evidence totalCount.
func authorImpactCountFor(t *testing.T, authorID, impactID string) int64 {
	t.Helper()
	for _, item := range authorImpactSummary(t, authorID) {
		if item.ImpactID == impactID {
			return item.Count
		}
	}
	t.Fatalf("author impact summary has no row for impactId %s", impactID)
	return 0
}

func getAuthorImpactEvidence(t *testing.T, authorID, impactID, cursor string, limit int) evidencePageResp {
	t.Helper()
	url := fmt.Sprintf("/content/sub-accounts/%s/author-impact/evidence?impactId=%s", authorID, impactID)
	if cursor != "" {
		url += "&cursor=" + cursor
	}
	if limit > 0 {
		url += fmt.Sprintf("&limit=%d", limit)
	}
	req := httptest.NewRequest(http.MethodGet, url, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("get author impact evidence: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var page evidencePageResp
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode evidence page: %v", err)
	}
	return page
}

func cleanAuthorImpact(t *testing.T, authorID string) {
	t.Helper()
	ctx := context.Background()
	_, _ = mongoDB.Collection("rm_author_impact").DeleteMany(ctx, bson.M{"authorId": authorID})
	_, _ = mongoDB.Collection("rm_author_impact_evidence").DeleteMany(ctx, bson.M{"authorId": authorID})
}

func postIDFrom(t *testing.T, created map[string]any) string {
	t.Helper()
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatalf("missing post id in response: %+v", created)
	}
	return postID
}

// TestAuthorImpactEvidenceDrilldownIsContentAnchoredAndPrivacySafe is the core
// R-ID03 contract (T3): a single impact-bearing behavior must materialize one
// content-anchored, privacy-safe evidence row that the app can drill into from
// the rm_author_impact count via a stable impactId. Replaying the same client
// event must not double-count (idempotency).
func TestAuthorImpactEvidenceDrilldownIsContentAnchoredAndPrivacySafe(t *testing.T) {
	authorID := "author_evidence_001"
	actorID := "viewer_evidence_001"
	forgedAuthorID := "forged_author_evidence_001"
	cleanAuthorImpact(t, authorID)
	t.Cleanup(func() {
		cleanPosts(t)
		cleanAuthorImpact(t, authorID)
		cleanAuthorImpact(t, forgedAuthorID)
	})

	created := submitPublishedPostWithAuthor(t, authorID,
		`{"contentType":"image","title":"城市漫步"}`)
	postID := postIDFrom(t, created)

	payload := fmt.Sprintf(`{
		"userId": %q,
		"events": [{
			"clientEventId": "evt-evidence-001",
			"occurredAt": %q,
			"contentId": %q,
			"contentType": "image",
			"action": "share",
			"authorId": %q,
			"intersectionDimension": "identity",
			"intersectionTagRefs": ["Audience/学生"]
		}]
	}`, actorID, time.Now().UTC().Format(time.RFC3339Nano), postID, forgedAuthorID)
	reportBehaviorRaw(t, payload)

	impactID := firstAuthorImpactID(t, authorID)

	page := getAuthorImpactEvidence(t, authorID, impactID, "", 0)
	if page.TotalCount != 1 {
		t.Fatalf("expected totalCount 1, got %d", page.TotalCount)
	}
	if len(page.Items) != 1 {
		t.Fatalf("expected 1 evidence item, got %d", len(page.Items))
	}
	if page.HasMore {
		t.Fatalf("single evidence must terminate (hasMore=false)")
	}
	if page.ImpactID != impactID {
		t.Fatalf("page impactId mismatch: want %s got %s", impactID, page.ImpactID)
	}

	item := page.Items[0]
	if item.ImpactID != impactID {
		t.Fatalf("evidence impactId must equal summary drill-down anchor: want %s got %s", impactID, item.ImpactID)
	}
	if item.HelpType != "spread" || item.Action != "share" {
		t.Fatalf("unexpected helpType/action: %+v", item)
	}
	if item.IntersectionDimension != "content" {
		t.Fatalf("unexpected intersectionDimension: %q", item.IntersectionDimension)
	}
	if forgedItems := authorImpactSummary(t, forgedAuthorID); len(forgedItems) != 0 {
		t.Fatalf("client-provided authorId must not create forged impact facts: %+v", forgedItems)
	}
	if strings.TrimSpace(item.OccurredAt) == "" {
		t.Fatalf("evidence must carry occurredAt")
	}

	// G2: cloud-side conclusion sentence rendered directly; privacy-safe ("有人"),
	// content-anchored (cites title), never names the actor.
	if strings.TrimSpace(item.SummaryText) == "" {
		t.Fatalf("summaryText must be a cloud-side conclusion (G2), got empty")
	}
	if strings.Contains(item.SummaryText, actorID) {
		t.Fatalf("summaryText leaks actor identity: %q", item.SummaryText)
	}
	if !strings.Contains(item.SummaryText, "城市漫步") {
		t.Fatalf("content-anchored summaryText should cite content title: %q", item.SummaryText)
	}
	if !strings.HasPrefix(item.SummaryText, "有人") {
		t.Fatalf("privacy-safe summaryText must start with 有人: %q", item.SummaryText)
	}

	// Content carrier: sample visual + drill-down target point at content detail.
	if item.SampleVisual == nil || item.SampleVisual.DisplayName != "城市漫步" {
		t.Fatalf("sampleVisual must carry hydrated content title: %+v", item.SampleVisual)
	}
	if item.SampleVisual.Target == nil || item.SampleVisual.Target.ObjectID != postID {
		t.Fatalf("sampleVisual target must point at content: %+v", item.SampleVisual)
	}
	if item.ContentTarget == nil ||
		item.ContentTarget.ObjectKind != "content" ||
		item.ContentTarget.RouteID != "contentDetail" ||
		item.ContentTarget.ObjectID != postID {
		t.Fatalf("contentTarget must drill to content detail: %+v", item.ContentTarget)
	}

	// Drill-down number integrity: the summary count the app shows must equal the
	// evidence totalCount it drills into.
	if cnt := authorImpactCountFor(t, authorID, impactID); cnt != page.TotalCount {
		t.Fatalf("summary count %d != evidence totalCount %d (drill-down numbers must match)", cnt, page.TotalCount)
	}

	// Idempotency: replaying the same clientEventId must not double-count, AND the
	// summary count must stay consistent with the deduped evidence count.
	reportBehaviorRaw(t, payload)
	replayed := getAuthorImpactEvidence(t, authorID, impactID, "", 0)
	if replayed.TotalCount != 1 {
		t.Fatalf("replaying same clientEventId must dedupe evidence, got totalCount %d", replayed.TotalCount)
	}
	if len(replayed.Items) != 1 {
		t.Fatalf("replay must keep a single evidence row, got %d", len(replayed.Items))
	}
	if cnt := authorImpactCountFor(t, authorID, impactID); cnt != replayed.TotalCount {
		t.Fatalf("after replay: summary count %d != evidence totalCount %d (idempotency must keep drill-down numbers aligned)", cnt, replayed.TotalCount)
	}
}

// TestAuthorImpactEvidencePaginationTerminates verifies cursor pagination over
// multiple evidence rows behind one impactId orders by occurredAt desc and
// terminates with hasMore=false at the tail (no fabricated extra rows).
func TestAuthorImpactEvidencePaginationTerminates(t *testing.T) {
	authorID := "author_evidence_page_001"
	cleanAuthorImpact(t, authorID)
	t.Cleanup(func() { cleanPosts(t); cleanAuthorImpact(t, authorID) })

	created := submitPublishedPostWithAuthor(t, authorID,
		`{"contentType":"image","title":"夜行电车"}`)
	postID := postIDFrom(t, created)

	for i := 0; i < 3; i++ {
		payload := fmt.Sprintf(`{"userId":%q,"events":[{"clientEventId":%q,"occurredAt":%q,"contentId":%q,"contentType":"image","action":"share","authorId":%q,"intersectionDimension":"identity","intersectionTagRefs":["Audience/学生"]}]}`,
			fmt.Sprintf("viewer_page_%03d", i), fmt.Sprintf("evt-page-%03d", i),
			time.Now().UTC().Add(-time.Duration(i)*time.Minute).Format(time.RFC3339Nano),
			postID, authorID)
		reportBehaviorRaw(t, payload)
	}

	impactID := firstAuthorImpactID(t, authorID)

	first := getAuthorImpactEvidence(t, authorID, impactID, "", 2)
	if first.TotalCount != 3 {
		t.Fatalf("expected totalCount 3, got %d", first.TotalCount)
	}
	if len(first.Items) != 2 || !first.HasMore || strings.TrimSpace(first.NextCursor) == "" {
		t.Fatalf("first page: items=%d hasMore=%v cursor=%q", len(first.Items), first.HasMore, first.NextCursor)
	}

	second := getAuthorImpactEvidence(t, authorID, impactID, first.NextCursor, 2)
	if len(second.Items) != 1 {
		t.Fatalf("second page should contain the tail item, got %d", len(second.Items))
	}
	if second.HasMore || strings.TrimSpace(second.NextCursor) != "" {
		t.Fatalf("second page must terminate: hasMore=%v cursor=%q", second.HasMore, second.NextCursor)
	}

	seen := map[string]bool{}
	for _, it := range append(append([]evidenceItemResp{}, first.Items...), second.Items...) {
		if strings.TrimSpace(it.EvidenceID) == "" {
			t.Fatalf("evidence row missing evidenceId: %+v", it)
		}
		if seen[it.EvidenceID] {
			t.Fatalf("duplicate evidence row across pages: %s", it.EvidenceID)
		}
		seen[it.EvidenceID] = true
		if it.ImpactID != impactID {
			t.Fatalf("paginated evidence impactId mismatch: %s", it.ImpactID)
		}
	}
	if len(seen) != 3 {
		t.Fatalf("expected 3 distinct evidence rows across pages, got %d", len(seen))
	}
}

// TestAuthorImpactEvidenceUnknownImpactReturnsEmpty verifies an impactId with no
// underlying facts returns an empty, terminated page rather than fabricating
// rows (R-ID03 closure: no full-set invention when evidence is absent).
func TestAuthorImpactEvidenceUnknownImpactReturnsEmpty(t *testing.T) {
	authorID := "author_evidence_empty_001"
	cleanAuthorImpact(t, authorID)
	t.Cleanup(func() { cleanAuthorImpact(t, authorID) })

	page := getAuthorImpactEvidence(t, authorID, "nonexistent-impact-id", "", 0)
	if page.TotalCount != 0 {
		t.Fatalf("unknown impact must report totalCount 0, got %d", page.TotalCount)
	}
	if len(page.Items) != 0 {
		t.Fatalf("unknown impact must return no fabricated items, got %d", len(page.Items))
	}
	if page.HasMore {
		t.Fatalf("unknown impact must terminate (hasMore=false)")
	}
}
