// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-001
// L2 契约测试：Post 业务对象 — 共同经历回流（gatheringRef 发布校验 + 聚合区读面）
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// gatheringParticipationProviderState 是 Circle owner 参与断言的
// provider-state 桩：按 (gatheringId, personaId) 登记状态；未登记时返回
// 空状态（诚实缺席），供 fail-closed 负例使用。
type gatheringParticipationProviderState struct {
	mu     sync.Mutex
	states map[string]postports.GatheringParticipationStatus
}

func newGatheringParticipationProviderState() *gatheringParticipationProviderState {
	return &gatheringParticipationProviderState{
		states: map[string]postports.GatheringParticipationStatus{},
	}
}

func (s *gatheringParticipationProviderState) set(
	status postports.GatheringParticipationStatus,
) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.states[status.GatheringID+"\x00"+status.PersonaID] = status
}

func (s *gatheringParticipationProviderState) clear() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.states = map[string]postports.GatheringParticipationStatus{}
}

func (s *gatheringParticipationProviderState) GetParticipationStatus(
	_ context.Context,
	gatheringID string,
	personaID string,
) (postports.GatheringParticipationStatus, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if status, ok := s.states[gatheringID+"\x00"+personaID]; ok {
		return status, nil
	}
	return postports.GatheringParticipationStatus{
		GatheringID: gatheringID,
		PersonaID:   personaID,
	}, nil
}

var testGatheringParticipations = newGatheringParticipationProviderState()

func listGatheringPostsForTest(t *testing.T, gatheringID string) []any {
	t.Helper()
	req := httptest.NewRequest(
		http.MethodGet,
		"/content/gatherings/"+gatheringID+"/posts?limit=20",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("ListPostsByGathering expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode gathering posts page: %v", err)
	}
	items, _ := resp["items"].([]any)
	return items
}

// SIT-008 正例：双方各自以 active Participation 发布公开回顾后，
// 行动详情聚合区经真实 HTTP + Mongo 读面同时看到两条内容。
func TestGatheringRecapFlywheelPositive(t *testing.T) {
	t.Cleanup(func() {
		cleanPosts(t)
		testGatheringParticipations.clear()
	})
	const gatheringID = "gathering_recap_positive"

	for _, author := range []string{"recap_author_a", "recap_author_b"} {
		testGatheringParticipations.set(postports.GatheringParticipationStatus{
			GatheringID:        gatheringID,
			PersonaID:          author,
			LifecycleStatus:    "completed",
			ParticipationState: "active",
		})
		submitPublishedPostWithAuthor(
			t,
			author,
			fmt.Sprintf(
				`{"contentType":"image","title":"recap by %s","gatheringRef":%q}`,
				author,
				gatheringID,
			),
		)
	}
	// 干扰项：其他行动的回顾不得串台。
	testGatheringParticipations.set(postports.GatheringParticipationStatus{
		GatheringID:        "gathering_recap_other",
		PersonaID:          "recap_author_c",
		LifecycleStatus:    "completed",
		ParticipationState: "active",
	})
	submitPublishedPostWithAuthor(
		t,
		"recap_author_c",
		`{"contentType":"image","title":"other recap","gatheringRef":"gathering_recap_other"}`,
	)

	items := listGatheringPostsForTest(t, gatheringID)
	if len(items) != 2 {
		t.Fatalf("expected 2 recap posts in aggregation, got %d", len(items))
	}
	authors := map[string]bool{}
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		authors[asTestString(item["authorId"])] = true
	}
	if !authors["recap_author_a"] || !authors["recap_author_b"] {
		t.Fatalf("aggregation must include both authors, got %v", authors)
	}
}

// SIT-008 负例：无 active Participation 的作者发布带 gatheringRef 的内容
// 必须被 fail-closed 拒绝，不产生半持久化 Post。
func TestGatheringRecapRejectsNonParticipant(t *testing.T) {
	t.Cleanup(func() {
		cleanPosts(t)
		testGatheringParticipations.clear()
	})
	const gatheringID = "gathering_recap_reject"
	authorID := "recap_outsider"

	payload := completePublicationFixturePrerequisites(
		t,
		authorID,
		fmt.Sprintf(
			`{"contentType":"image","title":"outsider recap","gatheringRef":%q}`,
			gatheringID,
		),
	)
	req := newPostPublicationRequestForTest(t, authorID, payload)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code < 400 || rec.Code >= 500 {
		t.Fatalf(
			"non-participant recap publication must be rejected with 4xx, got %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
	if items := listGatheringPostsForTest(t, gatheringID); len(items) != 0 {
		t.Fatalf("rejected recap must not appear in aggregation, got %d items", len(items))
	}
}

// SIT-008 负例：私密发布即使携带合法 gatheringRef，也不得进入公开聚合区。
func TestGatheringRecapExcludesPrivatePosts(t *testing.T) {
	t.Cleanup(func() {
		cleanPosts(t)
		testGatheringParticipations.clear()
	})
	const gatheringID = "gathering_recap_private"
	authorID := "recap_private_author"
	testGatheringParticipations.set(postports.GatheringParticipationStatus{
		GatheringID:        gatheringID,
		PersonaID:          authorID,
		LifecycleStatus:    "completed",
		ParticipationState: "active",
	})

	submitPublishedPostWithAuthor(
		t,
		authorID,
		fmt.Sprintf(
			`{"contentType":"image","title":"private recap","visibility":"private","gatheringRef":%q}`,
			gatheringID,
		),
	)

	if items := listGatheringPostsForTest(t, gatheringID); len(items) != 0 {
		t.Fatalf("private recap must not enter public aggregation, got %d items", len(items))
	}
}
