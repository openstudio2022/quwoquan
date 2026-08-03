package behavior_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

type contractIntersectionSource struct {
	facts []intersectionapp.IntersectionReasonView
}

func (s contractIntersectionSource) FactReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	out := make([]intersectionapp.IntersectionReasonView, len(s.facts))
	copy(out, s.facts)
	return out, nil
}

func (s contractIntersectionSource) AffinityReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}

func (s contractIntersectionSource) ObjectReasons(context.Context, string, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}

func newContractRouter(t *testing.T) *rtredis.Router {
	t.Helper()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	t.Cleanup(func() {
		_ = router.Close()
	})
	return router
}

func contractDisplayReadyReason(id, sourceRef, dimension, targetID, objectKind, displayName string, strength float64, freshAt string) intersectionapp.IntersectionReasonView {
	actorID := "actor_" + id
	return intersectionapp.IntersectionReasonView{
		IntersectionID:            id,
		IntersectionClass:         "fact",
		Kind:                      sourceRef,
		Dimension:                 dimension,
		ObjectKind:                objectKind,
		ActionTargetID:            targetID,
		DisplayName:               displayName,
		AvatarURL:                 "https://static.quwoquan.test/" + id + ".png",
		Strength:                  strength,
		FreshAt:                   freshAt,
		ActorEvidenceTotalCount:   1,
		ActorEvidenceCompleteness: "complete",
		ActorEvidence: []intersectionapp.IntersectionActorEvidenceView{
			{
				ActorID:       actorID,
				DisplayName:   "林清越",
				RelationLabel: "你关注的人",
				SourceRef:     sourceRef,
				PrivacyState:  "visible",
				Target: &intersectionapp.IntersectionTargetView{
					ObjectType: "user",
					ObjectID:   actorID,
					ObjectKind: "person",
					RouteID:    "userProfile",
				},
			},
		},
		IntersectionPoints: []intersectionapp.IntersectionPointView{
			{
				PointID:    "pt_" + id,
				PointClass: "fact",
				Dimension:  dimension,
				SourceRef:  sourceRef,
				Visibility: "public",
				Count:      1,
			},
		},
	}
}

// TestBehaviorBatchIntersectionFeedbackWritesCooldownAndFiltersFeed proves the
// F recommendation differentiation path across the HTTP behavior boundary:
// App/Remote posts intersection_feedback -> BehaviorService routes to
// IntersectionService -> rec:ineg cooldown filters the same subject from the
// next intersection feed. This guards the commercial v3 funnel from stopping at
// local tracker serialization.
func TestBehaviorBatchIntersectionFeedbackWritesCooldownAndFiltersFeed(t *testing.T) {
	ctx := context.Background()
	viewerID := "user_ix_feedback_http_001"
	now := time.Now().UTC()
	source := contractIntersectionSource{
		facts: []intersectionapp.IntersectionReasonView{
			contractDisplayReadyReason("ix_http_negative_subject", "sharedFollowees", "relationship", "subject_negative_001", "person", "陆衡", 0.9, now.Format(time.RFC3339)),
			contractDisplayReadyReason("ix_http_survivor_subject", "coCommented", "content", "subject_survivor_001", "content", "摄影路线", 0.8, now.Format(time.RFC3339)),
		},
	}
	router := newContractRouter(t)
	intersectionService := intersectionapp.NewIntersectionService(
		router,
		intersectionapp.WithIntersectionSource(source),
	)
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		persistence.NewPostStore(nil),
		behaviorapp.WithIntersectionFeedbackSink(intersectionService),
	)
	handler := contenhttp.NewContentHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		behaviorService,
		contenhttp.WithContentBehaviorHandler(behaviorhttp.NewHandler(behaviorService)),
	).Routes()

	before, err := intersectionService.Feed(ctx, viewerID, "recommend", 10)
	if err != nil {
		t.Fatalf("feed before feedback: %v", err)
	}
	if len(before) != 2 {
		t.Fatalf("want 2 candidates before feedback, got %+v", before)
	}

	req := httptest.NewRequest(
		http.MethodPost,
		"/content/behaviors",
		strings.NewReader(fmt.Sprintf(
			`{"events":[{"clientEventId":"evt-http-negative-001","occurredAt":%q,"action":"intersection_feedback","subjectId":"subject_negative_001","feedbackKind":"notInterested","intersectionId":"ix_http_negative_subject","intersectionDimension":"relationship","intersectionClass":"fact","intersectionSourceRef":"sharedFollowees"}]}`,
			time.Now().UTC().Format(time.RFC3339Nano),
		)),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", viewerID)
	req = req.WithContext(rtauth.WithPrincipal(req.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: viewerID, PersonaID: viewerID},
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("behavior feedback expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	after, err := intersectionService.Feed(ctx, viewerID, "recommend", 10)
	if err != nil {
		t.Fatalf("feed after feedback: %v", err)
	}
	if len(after) != 1 {
		data, _ := json.Marshal(after)
		t.Fatalf("want one survivor after negative feedback, got %s", data)
	}
	if after[0].ActionTargetID != "subject_survivor_001" {
		t.Fatalf("negative subject should be filtered, got %+v", after)
	}
}
