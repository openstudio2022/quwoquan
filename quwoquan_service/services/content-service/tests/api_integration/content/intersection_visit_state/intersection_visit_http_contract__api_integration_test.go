// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
// readiness_case: get-my-intersection-summary-api
// readiness_case: list-my-intersections-api
// readiness_case: get-object-intersections-api
package intersection_visit_state_test

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	intersectionvisithttp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/adapters/inbound/http"
	intersectionvisitapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	intersectionvisitpersistence "quwoquan_service/services/content-service/internal/content/intersection_visit_state/infrastructure/persistence"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
)

type apiIntersectionSource struct {
	reasons []intersectionapp.IntersectionReasonView
}

func (source apiIntersectionSource) FactReasons(
	context.Context,
	string,
	string,
) ([]intersectionapp.IntersectionReasonView, error) {
	return append([]intersectionapp.IntersectionReasonView(nil), source.reasons...), nil
}

func (apiIntersectionSource) AffinityReasons(
	context.Context,
	string,
	string,
) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}

func (source apiIntersectionSource) ObjectReasons(
	context.Context,
	string,
	string,
	string,
) ([]intersectionapp.IntersectionReasonView, error) {
	return append([]intersectionapp.IntersectionReasonView(nil), source.reasons...), nil
}

// TestIntersectionVisitHTTPContract 覆盖 content/content/intersection_visit_state 契约
// （tests/contract.yaml#mark_visited_monotonic_watermark）：
// POST /content/intersections/visit 经 generated 路由可达、水位 $max 单调推进、
// 全维度/单维度推进、无效维度 400、重放收敛。
func TestIntersectionVisitHTTPContract(t *testing.T) {
	ctx := t.Context()
	runtime, err := testinfra.StartRealMongo(ctx, "intersection_visit_state_contract")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if closeErr := runtime.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	db := runtime.Database
	coll := db.Collection("rm_intersection_watermark")
	const viewer = "visit-http-viewer"
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": viewer})
	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_, _ = coll.DeleteMany(cleanupCtx, bson.M{"_id": viewer})
	})

	store := intersectionvisitpersistence.NewMongoWatermarkStore(db, slog.Default())
	reason := intersectionapp.IntersectionReasonView{
		IntersectionID:            "intersection-http-reason",
		IntersectionClass:         "fact",
		Kind:                      "sharedFollowees",
		Dimension:                 "relationship",
		ObjectKind:                "person",
		ActionTargetID:            "persona-related",
		DisplayName:               "林清越",
		Strength:                  0.9,
		FreshAt:                   time.Now().UTC().Add(-time.Minute).Format(time.RFC3339),
		ActorEvidenceTotalCount:   1,
		ActorEvidenceCompleteness: "complete",
		ActorEvidence: []intersectionapp.IntersectionActorEvidenceView{{
			ActorID:       "persona-related",
			DisplayName:   "林清越",
			RelationLabel: "你关注的人",
			SourceRef:     "sharedFollowees",
			PrivacyState:  "visible",
		}},
		IntersectionPoints: []intersectionapp.IntersectionPointView{{
			PointID:     "point-shared-followee",
			PointClass:  "fact",
			Dimension:   "relationship",
			SourceRef:   "sharedFollowees",
			Label:       "共同关注的人",
			DisplayText: "共同关注的人",
			Visibility:  "public",
			Count:       1,
		}},
	}
	service := intersectionapp.NewIntersectionService(
		nil,
		intersectionapp.WithIntersectionWatermarkStore(store),
		intersectionapp.WithIntersectionSource(apiIntersectionSource{reasons: []intersectionapp.IntersectionReasonView{reason}}),
	)
	handler := contenhttp.NewContentHandler(
		nil, nil, nil, nil, nil, nil, nil,
		contenhttp.WithIntersectionVisitStateHandler(
			intersectionvisithttp.NewHandler(
				intersectionvisitapp.NewCommands(service),
				service,
			),
		),
	).Routes()

	visit := func(body string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/intersections/visit",
			strings.NewReader(body),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", viewer)
		request.Header.Set("X-Client-Persona-Id", viewer)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{AccountID: viewer, PersonaID: viewer},
		}))
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		return recorder
	}

	// 单维度推进。
	single := visit(`{"dimension":"relationship"}`)
	if single.Code != http.StatusOK {
		t.Fatalf("single dimension visit status=%d body=%s", single.Code, single.Body.String())
	}
	var singleAck struct {
		Dimensions []string `json:"dimensions"`
		Status     string   `json:"status"`
	}
	if err := json.Unmarshal(single.Body.Bytes(), &singleAck); err != nil {
		t.Fatalf("decode visit ack: %v", err)
	}
	if singleAck.Status != "visited" ||
		len(singleAck.Dimensions) != 1 ||
		singleAck.Dimensions[0] != "relationship" {
		t.Fatalf("unexpected single visit ack: %+v", singleAck)
	}
	afterSingle, err := store.LoadWatermarks(ctx, viewer)
	if err != nil || afterSingle["relationship"] == 0 {
		t.Fatalf("relationship watermark must advance: %v err=%v", afterSingle, err)
	}
	relationshipWatermark := afterSingle["relationship"]

	// 空维度推进全部五个维度。
	all := visit(`{}`)
	if all.Code != http.StatusOK {
		t.Fatalf("all dimension visit status=%d body=%s", all.Code, all.Body.String())
	}
	var allAck struct {
		Dimensions []string `json:"dimensions"`
	}
	if err := json.Unmarshal(all.Body.Bytes(), &allAck); err != nil {
		t.Fatalf("decode all visit ack: %v", err)
	}
	if len(allAck.Dimensions) != 5 {
		t.Fatalf("empty dimension must advance all five dimensions: %+v", allAck)
	}
	afterAll, err := store.LoadWatermarks(ctx, viewer)
	if err != nil || len(afterAll) != 5 {
		t.Fatalf("all watermarks must exist: %v err=%v", afterAll, err)
	}
	if afterAll["relationship"] < relationshipWatermark {
		t.Fatalf(
			"watermark must be monotonic: before=%d after=%d",
			relationshipWatermark,
			afterAll["relationship"],
		)
	}

	// 重放（同维度再推进）语义收敛：状态仍 visited、水位不回退。
	replay := visit(`{"dimension":"relationship"}`)
	if replay.Code != http.StatusOK {
		t.Fatalf("replayed visit status=%d body=%s", replay.Code, replay.Body.String())
	}
	afterReplay, err := store.LoadWatermarks(ctx, viewer)
	if err != nil || afterReplay["relationship"] < afterAll["relationship"] {
		t.Fatalf("replay must not regress watermark: %v err=%v", afterReplay, err)
	}

	// 无效维度 fail closed。
	invalid := visit(`{"dimension":"unknown_dimension"}`)
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid dimension status=%d body=%s", invalid.Code, invalid.Body.String())
	}

	// 未认证 fail closed。
	anonymous := httptest.NewRequest(
		http.MethodPost,
		"/content/intersections/visit",
		strings.NewReader(`{"dimension":"content"}`),
	)
	anonymous.Header.Set("Content-Type", "application/json")
	anonymousRecorder := httptest.NewRecorder()
	handler.ServeHTTP(anonymousRecorder, anonymous)
	if anonymousRecorder.Code == http.StatusOK {
		t.Fatalf("anonymous visit must not succeed: %s", anonymousRecorder.Body.String())
	}

	query := func(path string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: "account-" + viewer,
				PersonaID: viewer,
			},
		}))
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		return recorder
	}

	summary := query("/content/intersections/summary")
	if summary.Code != http.StatusOK {
		t.Fatalf("GetMyIntersectionSummary status=%d body=%s", summary.Code, summary.Body.String())
	}
	var summaryBody struct {
		TotalCount int `json:"totalCount"`
	}
	if err := json.Unmarshal(summary.Body.Bytes(), &summaryBody); err != nil {
		t.Fatal(err)
	}
	if summaryBody.TotalCount != 1 {
		t.Fatalf("GetMyIntersectionSummary body=%s", summary.Body.String())
	}

	listed := query("/content/intersections?dimension=relationship&limit=10")
	if listed.Code != http.StatusOK {
		t.Fatalf("ListMyIntersections status=%d body=%s", listed.Code, listed.Body.String())
	}
	var listBody struct {
		Items []intersectionapp.IntersectionReasonView `json:"items"`
	}
	if err := json.Unmarshal(listed.Body.Bytes(), &listBody); err != nil {
		t.Fatal(err)
	}
	if len(listBody.Items) != 1 || listBody.Items[0].IntersectionID != reason.IntersectionID {
		t.Fatalf("ListMyIntersections body=%s", listed.Body.String())
	}

	object := query("/content/intersections/object?objectId=persona-related&objectType=user&limit=8")
	if object.Code != http.StatusOK {
		t.Fatalf("GetObjectIntersections status=%d body=%s", object.Code, object.Body.String())
	}
	var objectBody struct {
		Items []intersectionapp.IntersectionReasonView `json:"items"`
	}
	if err := json.Unmarshal(object.Body.Bytes(), &objectBody); err != nil {
		t.Fatal(err)
	}
	if len(objectBody.Items) != 1 || objectBody.Items[0].IntersectionID != reason.IntersectionID {
		t.Fatalf("GetObjectIntersections body=%s", object.Body.String())
	}
}
