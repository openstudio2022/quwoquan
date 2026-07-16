package http

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	postdomain "quwoquan_service/services/content-service/internal/domain/post"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func extractFirstInteractionID(t *testing.T, body []byte) string {
	t.Helper()
	var payload struct {
		Items []struct {
			InteractionID string `json:"activityId"`
		} `json:"items"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("decode list body: %v", err)
	}
	if len(payload.Items) == 0 || payload.Items[0].InteractionID == "" {
		t.Fatalf("missing interaction in body: %s", string(body))
	}
	return payload.Items[0].InteractionID
}

func newProfileShareHandler(t *testing.T) http.Handler {
	t.Helper()
	now := time.Date(2026, 7, 12, 8, 0, 0, 0, time.UTC)
	postStore := testsupport.NewPostStore([]postmodel.Post{{
		ID:                        "profile-share-target",
		AuthorId:                  "owner-persona",
		AuthorDisplayNameSnapshot: "主页作者",
		ContentType:               "article",
		Title:                     "川西路线",
		Status:                    "published",
		Visibility:                "public",
		CreatedAt:                 now,
		UpdatedAt:                 now,
		PublishedAt:               now,
	}})
	shareProjection := testsupport.NewShareInteractionStore()
	service := postapp.NewPostService(
		postapp.BindDataPorts(postStore),
		postapp.WithShareInteractionStore(shareProjection),
	)
	if err := shareProjection.Save(context.Background(), postdomain.ShareInteractionOccurrence{
		InteractionID: "outbound-share-http", ActorSubAccountID: "actor-persona",
		TargetSubAccountID: "owner-persona", TargetContentID: "profile-share-target",
		TargetContentType: "article", TargetKind: "record", TargetAvailability: "active",
		OccurredAt: now,
	}); err != nil {
		t.Fatalf("seed outbound share projection: %v", err)
	}
	return NewContentHandler(nil, postapp.BindFacades(service), nil, nil, nil, nil, nil).Routes()
}

func TestProfileShareHTTPRequiresActiveOwnerPersona(t *testing.T) {
	handler := newProfileShareHandler(t)
	path := "/v1/content/sub-accounts/owner-persona/interactions/received?type=share"

	unauthorized := httptest.NewRequest(http.MethodGet, path, nil)
	unauthorizedRec := httptest.NewRecorder()
	handler.ServeHTTP(unauthorizedRec, unauthorized)
	if unauthorizedRec.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized status=%d", unauthorizedRec.Code)
	}

	forbidden := httptest.NewRequest(http.MethodGet, path, nil)
	forbidden = forbidden.WithContext(rtauth.WithPrincipal(
		forbidden.Context(),
		verifiedPrincipal("owner-user", "other-persona"),
	))
	forbiddenRec := httptest.NewRecorder()
	handler.ServeHTTP(forbiddenRec, forbidden)
	if forbiddenRec.Code != http.StatusForbidden {
		t.Fatalf("forbidden status=%d body=%s", forbiddenRec.Code, forbiddenRec.Body.String())
	}

	missingPersona := httptest.NewRequest(http.MethodGet, path, nil)
	missingPersona = missingPersona.WithContext(rtauth.WithPrincipal(
		missingPersona.Context(),
		verifiedPrincipal("owner-persona", ""),
	))
	missingPersonaRec := httptest.NewRecorder()
	handler.ServeHTTP(missingPersonaRec, missingPersona)
	if missingPersonaRec.Code != http.StatusUnauthorized {
		t.Fatalf("missing persona status=%d body=%s", missingPersonaRec.Code, missingPersonaRec.Body.String())
	}

	authorized := httptest.NewRequest(http.MethodGet, path, nil)
	authorized = authorized.WithContext(rtauth.WithPrincipal(
		authorized.Context(),
		verifiedPrincipal("owner-user", "owner-persona"),
	))
	authorizedRec := httptest.NewRecorder()
	handler.ServeHTTP(authorizedRec, authorized)
	if authorizedRec.Code != http.StatusOK {
		t.Fatalf("authorized status=%d body=%s", authorizedRec.Code, authorizedRec.Body.String())
	}
}

func TestProfileShareHTTPStateWriteIsIdempotent(t *testing.T) {
	handler := newProfileShareHandler(t)
	list := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/sub-accounts/owner-persona/interactions/received?type=share",
		nil,
	)
	list = list.WithContext(rtauth.WithPrincipal(
		list.Context(),
		verifiedPrincipal("owner-user", "owner-persona"),
	))
	listRec := httptest.NewRecorder()
	handler.ServeHTTP(listRec, list)
	var interactionID string
	interactionID = extractFirstInteractionID(t, listRec.Body.Bytes())

	for index := 0; index < 2; index++ {
		request := httptest.NewRequest(
			http.MethodPatch,
			"/v1/content/sub-accounts/owner-persona/interactions/"+interactionID+"/state?state=read",
			nil,
		)
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			verifiedPrincipal("owner-user", "owner-persona"),
		))
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusNoContent {
			t.Fatalf("state write %d status=%d body=%s", index, recorder.Code, recorder.Body.String())
		}
	}
}
