package infrastructure_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	external "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

type circleReaderStub struct {
	exists bool
	err    error
}

func (stub circleReaderStub) CircleExists(context.Context, string) (bool, error) {
	return stub.exists, stub.err
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestTargetReaderUsesCanonicalOwnerAndRoutePair(t *testing.T) {
	t.Helper()
	var requestedPath string
	owner := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requestedPath = request.URL.EscapedPath()
		writer.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(owner.Close)
	reader := requireTargetReader(t, owner.URL, circleReaderStub{exists: true})

	err := reader.RequireNavigable(context.Background(), model.TargetRef{
		ObjectTypeRef: "photo_spot", ObjectID: "spot/001", RouteID: "homepageDetail",
	})
	if err != nil {
		t.Fatalf("RequireNavigable: %v", err)
	}
	if requestedPath != "/homepages/spot%2F001" {
		t.Fatalf("entity owner path = %q", requestedPath)
	}
	if err := reader.RequireNavigable(context.Background(), model.TargetRef{
		ObjectTypeRef: "photo_spot", ObjectID: "spot-001", RouteID: "gatheringDetail",
	}); !errors.Is(err, ports.ErrTargetNotNavigable) {
		t.Fatalf("non-canonical route error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestTargetReaderDistinguishesMissingTargetFromAuthorityFailure(t *testing.T) {
	statuses := []struct {
		name   string
		status int
		want   error
	}{
		{name: "missing", status: http.StatusNotFound, want: ports.ErrTargetNotNavigable},
		{name: "authority unavailable", status: http.StatusServiceUnavailable, want: ports.ErrTargetAuthorityUnavailable},
	}
	for _, current := range statuses {
		current := current
		t.Run(current.name, func(t *testing.T) {
			owner := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writer.WriteHeader(current.status)
			}))
			t.Cleanup(owner.Close)
			reader := requireTargetReader(t, owner.URL, circleReaderStub{exists: true})
			err := reader.RequireNavigable(context.Background(), model.TargetRef{
				ObjectTypeRef: "content", ObjectID: "post-001", RouteID: "workBrowser",
			})
			if !errors.Is(err, current.want) {
				t.Fatalf("error = %v, want %v", err, current.want)
			}
		})
	}
}

func requireTargetReader(t *testing.T, ownerURL string, circles external.LocalCircleReader) *external.TargetReader {
	t.Helper()
	reader, err := external.NewTargetReader(external.TargetReaderConfig{
		ContentBaseURL: ownerURL, EntityBaseURL: ownerURL, UserBaseURL: ownerURL,
		Circles: circles,
	})
	if err != nil {
		t.Fatalf("NewTargetReader: %v", err)
	}
	return reader
}
