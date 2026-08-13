// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
package api_integration

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	postgraphql "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/graphql"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestInternalGraphQLRequiresVerifiedAPIEdgeCredentialAndReadsPostSlice(t *testing.T) {
	config := internalGraphQLTokenConfig()
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		"api-edge",
		[]string{postgraphql.RequiredServiceScope},
	)
	if err != nil {
		t.Fatal(err)
	}
	reader := &apiPostDetailReader{detail: postports.PostDetailSlice{
		PostID: "post-1", ContentType: "article", Title: "owner internal GraphQL",
		Status: "published", Visibility: "public", ModerationStatus: "approved",
		CreatedAt: time.Date(2026, 8, 11, 0, 0, 0, 0, time.UTC),
		UpdatedAt: time.Date(2026, 8, 11, 0, 1, 0, 0, time.UTC),
	}}
	facade := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{Detail: reader})
	handler, err := postgraphql.NewInternalPersistedHandler(
		facade,
		strings.Repeat("7", 64),
	)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(handler))
	defer server.Close()

	authorization, err := credentials.AuthorizationHeader(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(
		http.MethodPost,
		server.URL+postgraphql.InternalGraphQLPath,
		bytes.NewBufferString(basePersistedGraphQLRequest),
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", strings.Repeat("7", 64))
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusOK ||
		!bytes.Contains(body, []byte(`"title":"owner internal GraphQL"`)) {
		t.Fatalf("status=%d body=%s", response.StatusCode, body)
	}
	if reader.calls != 1 || reader.postID != "post-1" {
		t.Fatalf("owner reader calls=%d postId=%q", reader.calls, reader.postID)
	}

	forged, err := http.NewRequest(
		http.MethodPost,
		server.URL+postgraphql.InternalGraphQLPath,
		bytes.NewBufferString(basePersistedGraphQLRequest),
	)
	if err != nil {
		t.Fatal(err)
	}
	forged.Header.Set("Content-Type", "application/json")
	forged.Header.Set("X-Contract-Graph-SHA256", strings.Repeat("7", 64))
	forged.Header.Set("X-Client-Account-Id", "service:api-edge")
	forgedResponse, err := http.DefaultClient.Do(forged)
	if err != nil {
		t.Fatal(err)
	}
	defer forgedResponse.Body.Close()
	if forgedResponse.StatusCode != http.StatusUnauthorized {
		forgedBody, _ := io.ReadAll(forgedResponse.Body)
		t.Fatalf("forged identity status=%d body=%s", forgedResponse.StatusCode, forgedBody)
	}
	if reader.calls != 1 {
		t.Fatalf("forged identity reached owner reader; calls=%d", reader.calls)
	}
}

const basePersistedGraphQLRequest = `{"operationName":"ContentPostDetailBase","variables":{"postId":"post-1"},"extensions":{"persistedQuery":{"version":1,"sha256Hash":"3525412614f94647191c1fead96cc6da3bdc452bf0bec9edd92af4793aed3110"}}}`

type apiPostDetailReader struct {
	detail postports.PostDetailSlice
	calls  int
	postID postports.PostID
}

func (reader *apiPostDetailReader) FindPostDetail(
	_ context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	reader.calls++
	reader.postID = postID
	return reader.detail, true, nil
}

func internalGraphQLTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("0123456789abcdef0123456789abcdef"),
		Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1,
		TTL: time.Minute, ClockSkew: time.Second,
	}
}
