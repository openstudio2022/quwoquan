package sharedtags_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/sharedtags"
)

// 这组契约守住 content-service → tag-service 共享标签防腐层的行为：
// 路径来自 generated descriptor、必须带服务凭据、空交集是合法答复、
// 上游异常映射成结构化失败而不是静默空结果。

type stubCredentials struct {
	header string
	err    error
	calls  atomic.Int64
}

func (c *stubCredentials) AuthorizationHeader(context.Context) (string, error) {
	c.calls.Add(1)
	if c.err != nil {
		return "", c.err
	}
	return c.header, nil
}

type recordedRequest struct {
	path          string
	query         map[string]string
	authorization string
	internalTag   string
}

func newSharedTagServer(
	t *testing.T,
	status int,
	body string,
	recorder *[]recordedRequest,
) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			query := map[string]string{}
			for key, values := range r.URL.Query() {
				query[key] = values[0]
			}
			if recorder != nil {
				*recorder = append(*recorder, recordedRequest{
					path:          r.URL.Path,
					query:         query,
					authorization: r.Header.Get("Authorization"),
					internalTag:   r.Header.Get("X-Internal-Service"),
				})
			}
			w.WriteHeader(status)
			_, _ = w.Write([]byte(body))
		},
	))
	t.Cleanup(server.Close)
	return server
}

func newReader(
	t *testing.T,
	server *httptest.Server,
	credentials *stubCredentials,
	options ...sharedtags.HTTPSharedTagReaderOption,
) *sharedtags.HTTPSharedTagReader {
	t.Helper()
	reader, err := sharedtags.NewHTTPSharedTagReader(
		server.URL,
		time.Second,
		credentials,
		options...,
	)
	if err != nil {
		t.Fatalf("reader construction failed: %v", err)
	}
	return reader
}

var (
	viewer = sharedtags.ObjectRef{ID: "persona-viewer", Type: "user"}
	other  = sharedtags.ObjectRef{ID: "persona-other", Type: "user"}
)

func TestSharedTagsUsesGeneratedRouteWithServiceCredential(t *testing.T) {
	var requests []recordedRequest
	server := newSharedTagServer(
		t,
		http.StatusOK,
		`[{"tagRef":"Audience/用户/职业/互联网/程序员","label":"程序员","strength":1,"source":"tagRef"}]`,
		&requests,
	)
	credentials := &stubCredentials{header: "Bearer service-token"}
	reader := newReader(t, server, credentials)

	tags, err := reader.SharedTags(context.Background(), viewer, other, 5)
	if err != nil {
		t.Fatal(err)
	}

	if len(tags) != 1 ||
		tags[0].TagRef != "Audience/用户/职业/互联网/程序员" ||
		tags[0].Label != "程序员" ||
		tags[0].Source != "tagRef" {
		t.Fatalf("shared tag decoding drifted from the contract: %+v", tags)
	}
	if len(requests) != 1 {
		t.Fatalf("expected exactly one upstream call, got %d", len(requests))
	}
	request := requests[0]
	if request.path != "/internal/tag/shared-tags" {
		t.Fatalf("route must come from the generated descriptor, got %s", request.path)
	}
	if request.query["objectAId"] != viewer.ID ||
		request.query["objectAType"] != viewer.Type ||
		request.query["objectBId"] != other.ID ||
		request.query["objectBType"] != other.Type ||
		request.query["limit"] != "5" {
		t.Fatalf("query params drifted from the contract: %+v", request.query)
	}
	if request.authorization != "Bearer service-token" {
		t.Fatalf(
			"principal=service operation requires a bearer credential, got %q",
			request.authorization,
		)
	}
	if request.internalTag != "content-service" {
		t.Fatalf("caller identity header missing, got %q", request.internalTag)
	}
	if credentials.calls.Load() != 1 {
		t.Fatalf("credentials must be minted per request, got %d", credentials.calls.Load())
	}
}

func TestSharedTagsTreatsEmptyIntersectionAsFact(t *testing.T) {
	server := newSharedTagServer(t, http.StatusOK, `[]`, nil)
	reader := newReader(t, server, &stubCredentials{header: "Bearer token"})

	tags, err := reader.SharedTags(context.Background(), viewer, other, 0)
	if err != nil {
		t.Fatalf("empty intersection must not be an error: %v", err)
	}
	if len(tags) != 0 {
		t.Fatalf("empty upstream response must stay empty, got %+v", tags)
	}
}

func TestSharedTagsCachesSymmetricPairWithinTTL(t *testing.T) {
	var requests []recordedRequest
	server := newSharedTagServer(
		t,
		http.StatusOK,
		`[{"tagRef":"Audience/用户/兴趣偏好/旅行摄影/旅行","label":"旅行","strength":1,"source":"tagRef"}]`,
		&requests,
	)
	clock := time.Date(2026, time.July, 1, 0, 0, 0, 0, time.UTC)
	reader := newReader(
		t,
		server,
		&stubCredentials{header: "Bearer token"},
		sharedtags.WithCacheTTL(30*time.Second),
		sharedtags.WithClock(func() time.Time { return clock }),
	)

	if _, err := reader.SharedTags(context.Background(), viewer, other, 3); err != nil {
		t.Fatal(err)
	}
	// 共享标签是对称关系：交换两端必须命中同一条缓存。
	if _, err := reader.SharedTags(context.Background(), other, viewer, 3); err != nil {
		t.Fatal(err)
	}
	if len(requests) != 1 {
		t.Fatalf("symmetric pair must reuse one cache entry, got %d calls", len(requests))
	}

	clock = clock.Add(31 * time.Second)
	if _, err := reader.SharedTags(context.Background(), viewer, other, 3); err != nil {
		t.Fatal(err)
	}
	if len(requests) != 2 {
		t.Fatalf(
			"expired cache must re-read the mutable object_tag_index, got %d calls",
			len(requests),
		)
	}
}

func TestSharedTagsRejectsInvalidObjectPairs(t *testing.T) {
	server := newSharedTagServer(t, http.StatusOK, `[]`, nil)
	reader := newReader(t, server, &stubCredentials{header: "Bearer token"})

	for _, testCase := range []struct {
		name   string
		first  sharedtags.ObjectRef
		second sharedtags.ObjectRef
		limit  int
	}{
		{
			name:   "missing id",
			first:  sharedtags.ObjectRef{ID: " ", Type: "user"},
			second: other,
		},
		{
			name:   "missing type",
			first:  sharedtags.ObjectRef{ID: "persona-viewer"},
			second: other,
		},
		{
			name:   "same object on both ends",
			first:  viewer,
			second: viewer,
		},
		{
			name:   "negative limit",
			first:  viewer,
			second: other,
			limit:  -1,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			_, err := reader.SharedTags(
				context.Background(),
				testCase.first,
				testCase.second,
				testCase.limit,
			)
			requireErrorCode(t, err, "CONTENT.USER.invalid_argument")
		})
	}
}

func TestSharedTagsMapsUpstreamFailuresToStructuredErrors(t *testing.T) {
	for _, testCase := range []struct {
		name         string
		status       int
		body         string
		expectedCode string
	}{
		{
			name:         "bad request stays a caller error",
			status:       http.StatusBadRequest,
			body:         `{"code":"TAG.USER.invalid_argument"}`,
			expectedCode: "CONTENT.USER.invalid_argument",
		},
		{
			name:         "gateway timeout is an upstream timeout",
			status:       http.StatusGatewayTimeout,
			body:         ``,
			expectedCode: "CONTENT.MIDDLEWARE.upstream_timeout",
		},
		{
			name:         "storage read failure is a dependency outage",
			status:       http.StatusInternalServerError,
			body:         `{"code":"TAG.SYSTEM.storage_read_failed"}`,
			expectedCode: "CONTENT.SYSTEM.required_dependency_unavailable",
		},
		{
			name:         "unauthorized is a dependency outage, never an empty intersection",
			status:       http.StatusUnauthorized,
			body:         ``,
			expectedCode: "CONTENT.SYSTEM.required_dependency_unavailable",
		},
		{
			name:         "malformed body must not degrade into no intersection",
			status:       http.StatusOK,
			body:         `{"tagRef":"not-an-array"}`,
			expectedCode: "CONTENT.SYSTEM.required_dependency_unavailable",
		},
		{
			name:         "duplicate tagRef breaks the projection contract",
			status:       http.StatusOK,
			body:         `[{"tagRef":"Audience/用户/职业/学生/大学生"},{"tagRef":"Audience/用户/职业/学生/大学生"}]`,
			expectedCode: "CONTENT.SYSTEM.required_dependency_unavailable",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			server := newSharedTagServer(t, testCase.status, testCase.body, nil)
			reader := newReader(t, server, &stubCredentials{header: "Bearer token"})

			tags, err := reader.SharedTags(context.Background(), viewer, other, 0)

			requireErrorCode(t, err, testCase.expectedCode)
			if tags != nil {
				t.Fatalf("failed reads must not return partial tags: %+v", tags)
			}
		})
	}
}

func TestSharedTagsFailsWhenCredentialsAreUnavailable(t *testing.T) {
	var requests []recordedRequest
	server := newSharedTagServer(t, http.StatusOK, `[]`, &requests)
	reader := newReader(
		t,
		server,
		&stubCredentials{err: context.DeadlineExceeded},
	)

	_, err := reader.SharedTags(context.Background(), viewer, other, 0)

	requireErrorCode(t, err, "CONTENT.SYSTEM.required_dependency_unavailable")
	if len(requests) != 0 {
		t.Fatalf("unsigned request must never reach tag-service, got %d calls", len(requests))
	}
}

func TestNewHTTPSharedTagReaderRejectsIncompleteWiring(t *testing.T) {
	credentials := &stubCredentials{header: "Bearer token"}
	for _, testCase := range []struct {
		name        string
		baseURL     string
		timeout     time.Duration
		credentials rtauth.ServiceAuthorizationProvider
	}{
		{name: "empty endpoint", timeout: time.Second, credentials: credentials},
		{
			name:        "endpoint without scheme",
			baseURL:     "tag-service:8080",
			timeout:     time.Second,
			credentials: credentials,
		},
		{
			name:        "non positive timeout",
			baseURL:     "http://tag-service:8080",
			credentials: credentials,
		},
		{
			name:    "missing credentials",
			baseURL: "http://tag-service:8080",
			timeout: time.Second,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			reader, err := sharedtags.NewHTTPSharedTagReader(
				testCase.baseURL,
				testCase.timeout,
				testCase.credentials,
			)
			if err == nil || reader != nil {
				t.Fatalf("incomplete wiring must fail fast, got reader=%v err=%v", reader, err)
			}
			requireErrorCode(
				t,
				err,
				"CONTENT.SYSTEM.required_dependency_unavailable",
			)
		})
	}
}

func requireErrorCode(t *testing.T, err error, expected string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected error code %s", expected)
	}
	if !strings.Contains(err.Error(), expected) {
		t.Fatalf("expected error code %s, got %v", expected, err)
	}
}
