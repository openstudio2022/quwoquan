// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-032
package http_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rtredis "quwoquan_service/runtime/redis"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const researchFeedManifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

type researchFeedActiveSupplyReader struct{}

func (researchFeedActiveSupplyReader) ActiveSupplySnapshot(context.Context) (feedapp.ActiveSupplySnapshot, error) {
	return feedapp.ActiveSupplySnapshot{
		Environment:     "local_contract",
		SourceOwner:     "qwq_data",
		Status:          "active",
		ActiveReleaseID: "rel_research_local_contract",
		ManifestDigest:  researchFeedManifestDigest,
		ReleaseClass:    "research",
		ReadbackStatus:  "passed",
		Posts:           1,
		PlayableVideos:  1,
	}, nil
}

type researchFeedAllowAllBlockReader struct{}

func (researchFeedAllowAllBlockReader) ListBlockedPersonaIDs(context.Context, string) ([]string, error) {
	return nil, nil
}

type researchFeedPostReader struct{}

func (researchFeedPostReader) FindPublishedFeedPost(context.Context, postports.PostID) (postports.PostFeedItemSlice, bool, error) {
	return postports.PostFeedItemSlice{}, false, nil
}

func (researchFeedPostReader) FindPublishedFeedPosts(context.Context, postports.PostFeedHydrationRequest) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	return map[postports.PostID]postports.PostFeedItemSlice{}, nil
}

func (researchFeedPostReader) ListPublishedFeedPosts(_ context.Context, request postports.PostFeedReadRequest) (postports.PostFeedSlice, error) {
	if request.Identity() != postports.ContentIdentity("work") {
		return postports.PostFeedSlice{}, nil
	}
	return postports.PostFeedSlice{Items: []postports.PostFeedItemSlice{{
		PostID:          postports.NewPostID("post-research-http-boundary"),
		AuthorPersonaID: postports.NewPersonaID("persona-research-author"),
		ContentType:     postports.ContentType("image"),
		ContentIdentity: postports.ContentIdentity("work"),
		Title:           "research content",
		CreatedAt:       time.Date(2026, time.September, 1, 0, 0, 0, 0, time.UTC),
		SourceOwner:     "qwq_data",
		ReleaseID:       "rel_research_local_contract",
		ManifestDigest:  researchFeedManifestDigest,
		LifecycleStatus: "active",
	}}}, nil
}

func researchFeedHTTPHandler() http.Handler {
	feedService := feedapp.NewFeedService(
		researchFeedPostReader{},
		feedapp.WithFeedViewerBlockReader(researchFeedAllowAllBlockReader{}),
		feedapp.WithActiveSupplyReader(researchFeedActiveSupplyReader{}),
		feedapp.WithFeedDeliveryPageStore(
			deliveryredis.NewStore(rtredis.NewMemoryClient()),
		),
	)
	return httpadapter.NewContentHandler(
		feedService,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
	).Routes()
}

func TestGetFeedDerivesResearchPrincipalOnlyFromVerifiedPrincipal(t *testing.T) {
	handler := researchFeedHTTPHandler()
	for name, principal := range map[string]*rtauth.Principal{
		"anonymous": nil,
		"authenticated non-research": {
			Claims: rtauth.Claims{Roles: []string{"member"}},
		},
	} {
		t.Run(name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodGet,
				"/content/feed?identity=work&sort=recommend&limit=1",
				nil,
			)
			if principal != nil {
				request = request.WithContext(
					rtauth.WithPrincipal(request.Context(), *principal),
				)
			}
			recorder := httptest.NewRecorder()

			handler.ServeHTTP(recorder, request)

			if recorder.Code != http.StatusOK {
				t.Fatalf("GetFeed status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			var response map[string]any
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
				t.Fatalf("decode GetFeed response: %v", err)
			}
			if response["outcome"] != "empty" || response["emptyReason"] != "no_active_release" {
				t.Fatalf("non-research principal must converge to no_active_release: %#v", response)
			}
			if items, ok := response["items"].([]any); !ok || len(items) != 0 {
				t.Fatalf("converged response must have an empty items array: %#v", response)
			}
			for _, forbidden := range []string{"releaseId", "manifestDigest"} {
				if _, exists := response[forbidden]; exists {
					t.Fatalf("converged response must omit %s: %#v", forbidden, response)
				}
			}
		})
	}

	request := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?identity=work&sort=recommend&limit=1",
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{Roles: []string{rtauth.RoleResearch}}},
	))
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("research GetFeed status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var response struct {
		Items []struct {
			PostID string `json:"postId"`
		} `json:"items"`
		Outcome string `json:"outcome"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode research GetFeed response: %v", err)
	}
	if response.Outcome != "content" || len(response.Items) != 1 ||
		response.Items[0].PostID != "post-research-http-boundary" {
		t.Fatalf("verified research principal must reach release content: %+v", response)
	}
}

type researchQueryDetailReader struct {
	calls   int
	request postports.PostDetailReadRequest
}

func (reader *researchQueryDetailReader) FindPostDetail(
	context.Context,
	postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	reader.calls++
	return postports.PostDetailSlice{}, false, nil
}

func (reader *researchQueryDetailReader) FindReleaseBoundPostDetail(
	_ context.Context,
	request postports.PostDetailReadRequest,
) (postports.PostDetailSlice, bool, error) {
	reader.calls++
	reader.request = request
	return postports.PostDetailSlice{
		PostID: "post-research-http-boundary", AuthorPersonaID: "persona-author",
		ContentType: "article", Title: "research detail",
		Status: "published", Visibility: "public", ModerationStatus: "approved",
	}, true, nil
}

func researchQueryHTTPHandler(reader *researchQueryDetailReader) http.Handler {
	return httpadapter.NewContentHandler(
		nil,
		nil,
		postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
			Detail: reader, ActiveSupply: researchFeedActiveSupplyReader{},
		}),
		nil,
		nil,
		nil,
		nil,
	).Routes()
}

func TestGetPostDerivesResearchRoleOnlyFromVerifiedPrincipal(t *testing.T) {
	reader := &researchQueryDetailReader{}
	handler := researchQueryHTTPHandler(reader)

	for _, request := range []*http.Request{
		httptest.NewRequest(http.MethodGet, "/content/posts/post-research-http-boundary", nil),
		func() *http.Request {
			r := httptest.NewRequest(http.MethodGet, "/content/posts/post-research-http-boundary", nil)
			r.Header.Set("X-Research-Role", "research")
			return r
		}(),
		func() *http.Request {
			r := httptest.NewRequest(http.MethodGet, "/content/posts/post-research-http-boundary", nil)
			return r.WithContext(rtauth.WithPrincipal(r.Context(), rtauth.Principal{
				Claims: rtauth.Claims{Roles: []string{"member"}},
			}))
		}(),
	} {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusNotFound {
			t.Fatalf("non-research GetPost status=%d body=%s", recorder.Code, recorder.Body.String())
		}
	}
	if reader.calls != 0 {
		t.Fatalf("non-research requests reached detail reader: calls=%d", reader.calls)
	}

	request := httptest.NewRequest(http.MethodGet, "/content/posts/post-research-http-boundary", nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Roles: []string{rtauth.RoleResearch}},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("research GetPost status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if reader.calls != 1 || reader.request.ActiveReleaseID() != "rel_research_local_contract" ||
		reader.request.ManifestDigest() != researchFeedManifestDigest {
		t.Fatalf("research detail request not exact-release-bound: calls=%d request=%+v", reader.calls, reader.request)
	}
}
