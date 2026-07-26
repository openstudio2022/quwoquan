package taxonomyvalidation_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/taxonomyvalidation"
)

type validateRequest struct {
	ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
	TagRefs                   []string `json:"tagRefs"`
}

func assertTaxonomyRuntimeCode(t *testing.T, err error, want string) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error is not a runtime AppError: %T %v", err, err)
	}
	if got := appError.Code.String(); got != want {
		t.Fatalf("runtime code = %q, want %q", got, want)
	}
}

func TestHTTPActiveTaxonomyLeafValidatorUsesTypedTagContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost {
			t.Errorf("method = %s, want POST", request.Method)
		}
		if request.URL.Path != "/tag/validate" {
			t.Errorf("path = %q, want generated /tag/validate", request.URL.Path)
		}
		if got := request.Header.Get("X-Internal-Service"); got != "content-service" {
			t.Errorf("X-Internal-Service = %q", got)
		}
		var decoded validateRequest
		if err := json.NewDecoder(request.Body).Decode(&decoded); err != nil {
			t.Errorf("decode request: %v", err)
		}
		if decoded.ExpectedTaxonomyReleaseID != "tag-taxonomy-test-001" {
			t.Errorf("expectedTaxonomyReleaseId = %q", decoded.ExpectedTaxonomyReleaseID)
		}
		if len(decoded.TagRefs) != 2 || decoded.TagRefs[0] != "Topic/travel" || decoded.TagRefs[1] != "Audience/photo" {
			t.Errorf("tagRefs = %#v", decoded.TagRefs)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"taxonomyReleaseId":"tag-taxonomy-test-001",
			"valid":["Topic/travel","Audience/photo"],
			"invalid":[]
		}`))
	}))
	defer server.Close()

	validator, err := NewHTTPActiveTaxonomyLeafValidator(
		server.URL,
		time.Second,
		WithHTTPClient(server.Client()),
	)
	if err != nil {
		t.Fatalf("NewHTTPActiveTaxonomyLeafValidator() error = %v", err)
	}
	if err := validator.ValidateActiveTaxonomyLeaves(
		context.Background(),
		"tag-taxonomy-test-001",
		[]string{" Topic/travel ", "Audience/photo", "Topic/travel"},
	); err != nil {
		t.Fatalf("ValidateActiveTaxonomyLeaves() error = %v", err)
	}
}

func TestHTTPActiveTaxonomyLeafValidatorMapsTagFailureStatus(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		wantCode   string
	}{
		{name: "invalid_argument", statusCode: http.StatusBadRequest, wantCode: "CONTENT.USER.invalid_argument"},
		{name: "dependency_unavailable", statusCode: http.StatusServiceUnavailable, wantCode: "CONTENT.SYSTEM.required_dependency_unavailable"},
		{name: "timeout", statusCode: http.StatusGatewayTimeout, wantCode: "CONTENT.MIDDLEWARE.upstream_timeout"},
	}
	for _, testCase := range tests {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				http.Error(w, "upstream diagnostic must stay redacted", testCase.statusCode)
			}))
			defer server.Close()

			validator, err := NewHTTPActiveTaxonomyLeafValidator(
				server.URL,
				time.Second,
				WithHTTPClient(server.Client()),
			)
			if err != nil {
				t.Fatalf("NewHTTPActiveTaxonomyLeafValidator() error = %v", err)
			}
			err = validator.ValidateActiveTaxonomyLeaves(
				context.Background(),
				"tag-taxonomy-test-001",
				[]string{"Topic/travel"},
			)
			if err == nil {
				t.Fatal("ValidateActiveTaxonomyLeaves() accepted HTTP failure")
			}
			assertTaxonomyRuntimeCode(t, err, testCase.wantCode)
		})
	}
}

func TestHTTPActiveTaxonomyLeafValidatorFailsClosedForSnapshotOrLeafMismatch(t *testing.T) {
	tests := []struct {
		name string
		body string
		want string
	}{
		{
			name: "snapshot_mismatch",
			body: `{"taxonomyReleaseId":"tag-taxonomy-other","valid":["Topic/travel"],"invalid":[]}`,
			want: "CONTENT.SYSTEM.required_dependency_unavailable",
		},
		{
			name: "inactive_or_non_leaf",
			body: `{"taxonomyReleaseId":"tag-taxonomy-test-001","valid":[],"invalid":["Topic/travel"]}`,
			want: "CONTENT.USER.invalid_argument",
		},
	}
	for _, testCase := range tests {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(testCase.body))
			}))
			defer server.Close()

			validator, err := NewHTTPActiveTaxonomyLeafValidator(
				server.URL,
				time.Second,
				WithHTTPClient(server.Client()),
			)
			if err != nil {
				t.Fatalf("NewHTTPActiveTaxonomyLeafValidator() error = %v", err)
			}
			err = validator.ValidateActiveTaxonomyLeaves(
				context.Background(),
				"tag-taxonomy-test-001",
				[]string{"Topic/travel"},
			)
			if err == nil {
				t.Fatal("ValidateActiveTaxonomyLeaves() accepted invalid taxonomy response")
			}
			assertTaxonomyRuntimeCode(t, err, testCase.want)
		})
	}
}

func TestHTTPActiveTaxonomyLeafValidatorHonorsContextDeadline(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(100 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	validator, err := NewHTTPActiveTaxonomyLeafValidator(
		server.URL,
		20*time.Millisecond,
		WithHTTPClient(server.Client()),
	)
	if err != nil {
		t.Fatalf("NewHTTPActiveTaxonomyLeafValidator() error = %v", err)
	}
	err = validator.ValidateActiveTaxonomyLeaves(
		context.Background(),
		"tag-taxonomy-test-001",
		[]string{"Topic/travel"},
	)
	if err == nil {
		t.Fatal("ValidateActiveTaxonomyLeaves() ignored the configured deadline")
	}
	assertTaxonomyRuntimeCode(t, err, "CONTENT.MIDDLEWARE.upstream_timeout")
}
