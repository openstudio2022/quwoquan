// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
// readiness_case: get-author-impact-api
// readiness_case: list-author-impact-evidence-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	contenthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

type authorImpactAPICredentials string

func (credentials authorImpactAPICredentials) AuthorizationHeader(
	context.Context,
) (string, error) {
	return string(credentials), nil
}

func TestAuthorImpactHTTPUsesTheTypedRecommendationBoundary(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Header.Get("Authorization") != "Bearer author-impact-api" {
			t.Errorf("recommendation authorization=%q", request.Header.Get("Authorization"))
			http.Error(writer, "missing service authorization", http.StatusUnauthorized)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/internal/recommendation/authors/author-api/impact":
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"authorId": "author-api",
				"total":    1,
				"items": []map[string]any{{
					"impactId":  "impact-community",
					"helpType":  "community",
					"action":    "join_circle",
					"source":    "behavior",
					"count":     1,
					"updatedAt": "2026-08-06T10:00:00Z",
				}},
			})
		case "/internal/recommendation/authors/author-api/impact/impact-community/evidence":
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"impactId":   "impact-community",
				"totalCount": 1,
				"items": []map[string]any{{
					"evidenceId":  "evidence-community",
					"impactId":    "impact-community",
					"contentId":   "post-author-impact",
					"contentType": "post",
					"helpType":    "community",
					"action":      "join_circle",
					"occurredAt":  "2026-08-06T10:00:00Z",
				}},
				"hasMore": false,
			})
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(upstream.Close)
	reader, err := recommendation.NewAuthorImpactReaderClient(
		upstream.URL,
		authorImpactAPICredentials("Bearer author-impact-api"),
	)
	if err != nil {
		t.Fatalf("create author-impact reader: %v", err)
	}
	handler := contenthttp.NewContentHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		contenthttp.WithAuthorImpactProjectionReader(reader),
	).Routes()

	for _, target := range []struct {
		name string
		path string
	}{
		{name: "summary", path: "/content/personas/author-api/author-impact?limit=5"},
		{name: "evidence", path: "/content/personas/author-api/author-impact/evidence?impactId=impact-community&limit=5"},
	} {
		t.Run(target.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, target.path, nil)
			request.Header.Set("X-Client-User-Id", "author-api")
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			if !strings.Contains(recorder.Body.String(), "impact-community") {
				t.Fatalf("typed impact identity missing: %s", recorder.Body.String())
			}
		})
	}
}
