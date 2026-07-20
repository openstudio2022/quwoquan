package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/application"
)

type handlerIntersectionReaderStub struct {
	query application.ObjectIntersectionQuery
}

func (s *handlerIntersectionReaderStub) ListObjectIntersections(
	_ context.Context,
	query application.ObjectIntersectionQuery,
) ([]application.ObjectIntersectionFact, error) {
	s.query = query
	return []application.ObjectIntersectionFact{{
		PrimaryText:       "你和林同学都评论过这篇内容",
		IntersectionID:    "intersection-post-1",
		Dimension:         "content",
		IntersectionClass: "fact",
		SourceRef:         "coCommented",
		SourceRefs:        []string{"coCommented"},
	}}, nil
}

func TestSearchHandlerAttachesVerifiedPersonaIntersectionFacts(t *testing.T) {
	backend := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:   rtsearch.ObjectTypeContentPost,
		ObjectID:     "post-1",
		Title:        "摄影评论现场",
		Summary:      "摄影爱好者共同讨论",
		ContentType:  "article",
		Visibility:   "public",
		SourceDomain: "content",
	}})
	searchService := application.NewSearchService(backend, nil)
	decorator := application.NewRankingDecorator(
		nil,
		application.NewExperiments(application.ExperimentConfig{}),
		0,
		nil,
	)
	reader := &handlerIntersectionReaderStub{}
	attacher := application.NewIntersectionAttacher(
		reader,
		application.IntersectionAttacherConfig{MaxHits: 1},
		nil,
		nil,
	)
	handler := NewHandlerWithConfig(
		searchService,
		decorator,
		nil,
		HandlerConfig{Intersections: attacher},
	)

	request := httptest.NewRequest(
		http.MethodPost,
		"/search",
		bytes.NewBufferString(`{
			"query":"摄影",
			"mode":"result",
			"objectTypes":["article"],
			"limit":1
		}`),
	)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-1",
			PersonaID: "persona-1",
		}},
	))
	response := httptest.NewRecorder()

	handler.Routes().ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if reader.query.ViewerPersonaID != "persona-1" ||
		reader.query.ObjectID != "post-1" ||
		reader.query.ObjectType != "post" {
		t.Fatalf("intersection query=%#v", reader.query)
	}
	var payload struct {
		Hits []struct {
			ConnectionState    string                          `json:"connectionState"`
			IntersectionReason *rtsearch.HitIntersectionReason `json:"intersectionReason"`
		} `json:"hits"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(payload.Hits) != 1 {
		t.Fatalf("hits=%#v", payload.Hits)
	}
	hit := payload.Hits[0]
	if hit.ConnectionState != application.ConnectionStateConnected {
		t.Fatalf("connectionState=%q", hit.ConnectionState)
	}
	if hit.IntersectionReason == nil ||
		hit.IntersectionReason.PrimaryText != "你和林同学都评论过这篇内容" {
		t.Fatalf("intersectionReason=%#v", hit.IntersectionReason)
	}
}
