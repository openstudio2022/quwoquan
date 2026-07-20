package api_integration

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	intersectionapp "quwoquan_service/services/content-service/internal/application/intersection"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// TestIntersectionVisitHTTPContract 覆盖 content/intersection_visit_state 契约
// （tests/contract.yaml#mark_visited_monotonic_watermark）：
// POST /content/intersections/visit 经 generated 路由可达、水位 $max 单调推进、
// 全维度/单维度推进、无效维度 400、重放收敛。
func TestIntersectionVisitHTTPContract(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	coll := db.Collection("rm_intersection_watermark")
	const viewer = "visit-http-viewer"
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": viewer})
	t.Cleanup(func() { _, _ = coll.DeleteMany(ctx, bson.M{"_id": viewer}) })

	store := recinfra.NewMongoWatermarkStore(db, slog.Default())
	service := intersectionapp.NewIntersectionService(
		nil,
		intersectionapp.WithIntersectionWatermarkStore(store),
	)
	handler := contenhttp.NewContentHandler(
		nil, nil, nil, nil, nil, nil, nil,
		contenhttp.WithIntersectionService(service),
	).Routes()

	visit := func(body string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/intersections/visit",
			strings.NewReader(body),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", viewer)
		request.Header.Set("X-Client-Sub-Account-Id", viewer)
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
}
