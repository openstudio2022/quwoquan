package api_integration

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	postdomain "quwoquan_service/services/content-service/internal/domain/post"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func TestProfileShareInteractionDurableHTTPContract(t *testing.T) {
	ctx := context.Background()
	created := submitPublishedPostWithAuthor(t, "api-owner-persona", `{
		"contentType":"article",
		"title":"高原路线",
		"body":"一条用于转发互动 API 契约的高原路线。",
		"articleMarkdown":"# 高原路线\n\n一条用于转发互动 API 契约的高原路线。",
		"markdownDialect":"qwq-rich-md",
		"articleAssetManifest":{"assets":[]},
		"articleRenderProfile":{"template":"journal","fontPreset":"clean"},
		"visibility":"public"
	}`)
	postID := asTestString(created["postId"])
	if err := persistence.NewMongoShareInteractionStore(mongoDB, slog.Default()).Save(
		ctx,
		postdomain.ShareInteractionOccurrence{
			InteractionID: "outbound-share-api", ActorSubAccountID: "api-actor-persona",
			TargetSubAccountID: "api-owner-persona", TargetContentID: postID,
			TargetContentType: "article", TargetKind: "record", TargetAvailability: "active",
			OccurredAt: time.Now().UTC(),
		},
	); err != nil {
		t.Fatalf("seed outbound share projection: %v", err)
	}

	request := authedProfileShareRequest(
		t,
		http.MethodGet,
		"/content/sub-accounts/api-owner-persona/interactions/received?type=share&limit=20",
		"api-owner-persona",
	)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page struct {
		Items []struct {
			ActivityID         string `json:"activityId"`
			ActivityType       string `json:"activityType"`
			Direction          string `json:"direction"`
			TargetContentID    string `json:"targetContentId"`
			TargetKind         string `json:"targetKind"`
			TargetAvailability string `json:"targetAvailability"`
		} `json:"items"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode page: %v", err)
	}
	if len(page.Items) == 0 ||
		page.Items[0].ActivityType != "share" ||
		page.Items[0].Direction != "received" ||
		page.Items[0].TargetContentID != postID ||
		page.Items[0].TargetKind != "record" ||
		page.Items[0].TargetAvailability != "active" {
		t.Fatalf("share page mismatch: %#v", page.Items)
	}

	stateRequest := authedProfileShareRequest(
		t,
		http.MethodPatch,
		"/content/sub-accounts/api-owner-persona/interactions/"+
			url.PathEscape(page.Items[0].ActivityID)+
			"/state?state=read",
		"api-owner-persona",
	)
	stateRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(stateRecorder, stateRequest)
	if stateRecorder.Code != http.StatusNoContent {
		t.Fatalf("mark read status=%d body=%s", stateRecorder.Code, stateRecorder.Body.String())
	}

	restarted := postapp.NewPostService(
		postapp.BindDataPorts(
			persistence.NewMongoPostStore(requireMongoDB(t).Collection("posts")),
		),
		postapp.WithShareInteractionStore(
			persistence.NewMongoShareInteractionStore(
				requireMongoDB(t),
				slog.Default(),
			),
		),
	)
	items, _, _, err := restarted.ListProfileShareInteractions(
		ctx,
		"api-owner-persona",
		"received",
		"",
		20,
	)
	if err != nil || len(items) == 0 || items[0].ReadAt.IsZero() {
		t.Fatalf("restart durability mismatch items=%#v err=%v", items, err)
	}

	badCursor := authedProfileShareRequest(
		t,
		http.MethodGet,
		"/content/sub-accounts/api-owner-persona/interactions/received?type=share&cursor=bad",
		"api-owner-persona",
	)
	badCursorRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(badCursorRecorder, badCursor)
	if badCursorRecorder.Code != http.StatusBadRequest {
		t.Fatalf("bad cursor status=%d body=%s", badCursorRecorder.Code, badCursorRecorder.Body.String())
	}
}

func authedProfileShareRequest(
	t *testing.T,
	method string,
	path string,
	persona string,
) *http.Request {
	t.Helper()
	request := httptest.NewRequest(method, path, nil)
	return request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{
				Subject: "api-owner-user",
				Persona: persona,
			},
			Actor: rtoperation.ActorContext{
				AccountID: "api-owner-user",
				PersonaID: persona,
			},
		},
	))
}
