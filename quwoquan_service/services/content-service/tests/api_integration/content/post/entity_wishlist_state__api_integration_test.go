// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
// readiness_case: get-entity-wishlist-state-api
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

// TestEntityWishlistStateTracksBehaviorProjection 证明地点主页读取的「想去」状态
// 只来源于行为投影：添加与取消均经公开 HTTP 行为入口写入后，再从状态端点读取。
func TestEntityWishlistStateTracksBehaviorProjection(t *testing.T) {
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_wishlist_state_" + runID
	objectID := "homepage_wishlist_state_" + runID
	coll := mongoDB.Collection("entity_wishlist_events")
	t.Cleanup(func() {
		_, _ = coll.DeleteMany(context.Background(), bson.M{
			"userId":   userID,
			"entityId": objectID,
		})
	})

	report := func(action string) {
		t.Helper()
		payload := fmt.Sprintf(
			`{"events":[{"clientEventId":%q,"occurredAt":%q,"action":%q,"objectId":%q,"objectKind":"homepage","displayName":"状态读模型测试主页","sourceSurface":"homepageDetail","referralSource":"entity_page"}]}`,
			"event_"+action+"_"+runID,
			time.Now().UTC().Format(time.RFC3339Nano),
			action,
			objectID,
		)
		req := httptest.NewRequest(
			http.MethodPost,
			"/content/behaviors",
			strings.NewReader(payload),
		)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", userID)
		req.Header.Set("X-Client-Persona-Id", userID)
		req.Header.Set("X-Client-Session-Id", "session_"+runID)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s behavior status=%d body=%s", action, rec.Code, rec.Body.String())
		}
	}
	readState := func(wantWishlisted bool) {
		t.Helper()
		req := httptest.NewRequest(
			http.MethodGet,
			"/content/entity-wishlist-state?objectId="+objectID+"&objectKind=homepage",
			nil,
		)
		req.Header.Set("X-Client-User-Id", userID)
		req.Header.Set("X-Client-Persona-Id", userID)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf(
				"wishlist state status=%d body=%s",
				rec.Code,
				rec.Body.String(),
			)
		}
		var state struct {
			ObjectID   string `json:"objectId"`
			ObjectKind string `json:"objectKind"`
			Wishlisted bool   `json:"wishlisted"`
		}
		if err := json.NewDecoder(rec.Body).Decode(&state); err != nil {
			t.Fatalf("decode wishlist state: %v", err)
		}
		if state.ObjectID != objectID ||
			state.ObjectKind != "homepage" ||
			state.Wishlisted != wantWishlisted {
			t.Fatalf("unexpected wishlist state: %+v", state)
		}
	}

	report("wishlist_add")
	readState(true)
	report("wishlist_remove")
	readState(false)
}
