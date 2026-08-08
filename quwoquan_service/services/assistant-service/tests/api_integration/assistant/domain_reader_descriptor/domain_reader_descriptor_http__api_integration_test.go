// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
// readiness_case: get-domain-reader-descriptor-api
// readiness_case: list-domain-reader-descriptors-api
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	descriptorhttp "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/application"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

func TestDomainReaderDescriptorHTTPIsTypedBoundedAndServiceOnly(t *testing.T) {
	descriptor, err := model.NewDescriptor(model.Descriptor{
		DescriptorID:        "circle.gathering_context",
		ResolverRef:         "gathering.current_context",
		OwnerService:        "circle-service",
		OwnerOperationRefs:  []string{"circle.gathering.GetPublicGathering"},
		InputSchemaRef:      "circle.GatheringIDQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"circle.Gathering"},
		AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityInternal,
		MaxFreshnessSeconds: 900,
		SurfaceKinds:        []model.SurfaceKind{model.SurfacePersonal, model.SurfaceShared},
		ArtifactPolicy:      model.ArtifactInlineOrStored,
		CitationPolicy:      model.CitationEntityReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := resource.NewCatalog([]model.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	routes := testRouteDescriptors()
	handler, err := descriptorhttp.NewHandler(
		application.NewQueryService(catalog),
		routes,
	)
	if err != nil {
		t.Fatal(err)
	}

	anonymous := performRequest(handler.Routes(), "/internal/assistant/domain-readers", "")
	assertHTTPError(t, anonymous, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")
	wrongScope := performRequest(
		handler.Routes(),
		"/internal/assistant/domain-readers",
		"assistant.domain_reader.other",
	)
	assertHTTPError(t, wrongScope, http.StatusForbidden, "GATEWAY.USER.forbidden")

	listed := performRequest(
		handler.Routes(),
		"/internal/assistant/domain-readers?limit=1",
		"assistant.domain_reader.read",
	)
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	var list model.ListSlice
	if err := json.Unmarshal(listed.Body.Bytes(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Items) != 1 || list.Items[0].DescriptorID != descriptor.DescriptorID ||
		list.Items[0].DescriptorDigest != descriptor.DescriptorDigest ||
		list.Items[0].MaxFreshnessSeconds != 900 {
		t.Fatalf("list response=%+v", list)
	}

	detail := performRequest(
		handler.Routes(),
		"/internal/assistant/domain-readers/circle.gathering_context",
		"assistant.domain_reader.read",
	)
	if detail.Code != http.StatusOK {
		t.Fatalf("detail status=%d body=%s", detail.Code, detail.Body.String())
	}
	var got model.Descriptor
	if err := json.Unmarshal(detail.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got.ResolverRef != descriptor.ResolverRef ||
		got.ArtifactPolicy != model.ArtifactInlineOrStored {
		t.Fatalf("detail response=%+v", got)
	}

	invalid := performRequest(
		handler.Routes(),
		"/internal/assistant/domain-readers?limit=101",
		"assistant.domain_reader.read",
	)
	assertHTTPError(t, invalid, http.StatusBadRequest, "ASSISTANT.USER.domain_reader_invalid_argument")
	missing := performRequest(
		handler.Routes(),
		"/internal/assistant/domain-readers/missing",
		"assistant.domain_reader.read",
	)
	assertHTTPError(t, missing, http.StatusNotFound, "ASSISTANT.USER.domain_reader_descriptor_not_found")
}

func TestDomainReaderHandlerRejectsNonCanonicalInjectedRouteDescriptors(t *testing.T) {
	routes := testRouteDescriptors()
	routes.List.CommercialStatus = "blocked"
	if _, err := descriptorhttp.NewHandler(
		application.NewQueryService(nil),
		routes,
	); err == nil {
		t.Fatal("blocked route descriptor was accepted")
	}
	routes = testRouteDescriptors()
	routes.Get.PathTemplate = ""
	if _, err := descriptorhttp.NewHandler(
		application.NewQueryService(nil),
		routes,
	); err == nil {
		t.Fatal("route without generated path was accepted")
	}
}

func testRouteDescriptors() descriptorhttp.RouteDescriptors {
	base := rtauth.OperationSecurityDescriptor{
		ContractGraphSHA256: "sha256:" + strings.Repeat("a", 64),
		Method:              http.MethodGet,
		OperationKind:       "query",
		AuthMode:            "required",
		ActorRequirement:    "none",
		Principal:           "service",
		Scopes:              []string{"assistant.domain_reader.read"},
		OwnershipPolicy:     "service_delegation",
		TimeoutMilliseconds: 500,
		Idempotency:         "none",
		CommercialStatus:    "ready",
	}
	get := base
	get.CanonicalOperationID = "assistant.domain_reader_descriptor.GetDomainReaderDescriptor"
	get.PathTemplate = "/internal/assistant/domain-readers/{descriptorId}"
	list := base
	list.CanonicalOperationID = "assistant.domain_reader_descriptor.ListDomainReaderDescriptors"
	list.PathTemplate = "/internal/assistant/domain-readers"
	return descriptorhttp.RouteDescriptors{Get: get, List: list}
}

func performRequest(
	handler http.Handler,
	path string,
	scope string,
) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	if strings.TrimSpace(scope) != "" {
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			rtauth.Principal{Claims: rtauth.Claims{
				Subject: "assistant-service",
				Scope:   scope,
				Roles:   []string{"service"},
			}},
		))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertHTTPError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d body=%s, want %d", recorder.Code, recorder.Body.String(), status)
	}
	var response rterr.ErrorResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if response.Code != code {
		t.Fatalf("error=%+v, want code=%s", response, code)
	}
}
