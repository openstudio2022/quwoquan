package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	assignmenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/http"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
// readiness_case: get-experiment-assignment-local
// readiness_case: get-experiment-stats-local
func TestExperimentAssignmentHTTPBoundaryOwnsQueriesAndRejectsPublicWrites(t *testing.T) {
	store := newAssignmentStore()
	experiments, err := experimentapp.NewFacade(store, store)
	if err != nil {
		t.Fatal(err)
	}
	assignments, err := assignmentapp.NewFacade(experiments, store, store)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := assignmenthttp.NewHandler(assignments)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	handler.Register(mux)

	observedAt := time.Date(2026, time.July, 31, 10, 0, 0, 0, time.UTC)
	expected, err := store.experiment.Assign("persona:observed", observedAt)
	if err != nil {
		t.Fatal(err)
	}
	first, inserted, err := assignments.AppendObserved(
		context.Background(),
		assignmentapp.AssignmentObservation{
			ExperimentID: expected.ExperimentID, ExperimentRevision: expected.ExperimentRevision,
			SubjectKey: expected.SubjectKey, Variant: expected.Variant, ObservedAt: observedAt,
		},
	)
	if err != nil || !inserted {
		t.Fatalf("append observed assignment: inserted=%v fact=%+v err=%v", inserted, first, err)
	}

	assignmentPath := "/ops/experiments/" + expected.ExperimentID + "/assignment"
	assignmentResponse := performAssignmentRequest(
		mux,
		requestWithAssignmentActor(
			http.MethodGet,
			assignmentPath,
			operation.ActorContext{PersonaID: "observed"},
		),
	)
	if assignmentResponse.Code != http.StatusOK {
		t.Fatalf("assignment status=%d body=%s", assignmentResponse.Code, assignmentResponse.Body.String())
	}
	var read assignmentdomain.Fact
	decodeAssignmentResponse(t, assignmentResponse, &read)
	if read != first {
		t.Fatalf("assignment=%+v want=%+v", read, first)
	}

	statsResponse := performAssignmentRequest(
		mux,
		requestWithAssignmentActor(
			http.MethodGet,
			"/ops/experiments/"+expected.ExperimentID+"/stats",
			operation.ActorContext{AccountID: "operator-local"},
		),
	)
	if statsResponse.Code != http.StatusOK ||
		!strings.Contains(statsResponse.Body.String(), `"assignedSubjects":1`) ||
		!strings.Contains(statsResponse.Body.String(), `"`+expected.Variant+`":1`) {
		t.Fatalf("stats status=%d body=%s", statsResponse.Code, statsResponse.Body.String())
	}

	unauthorized := performAssignmentRequest(
		mux,
		httptest.NewRequest(http.MethodGet, assignmentPath, nil),
	)
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
	assertAssignmentRuntimeError(
		t,
		unauthorized,
		"OPS.USER.experiment_assignment_unauthorized",
	)

	missingAssignment := performAssignmentRequest(
		mux,
		requestWithAssignmentActor(
			http.MethodGet,
			assignmentPath,
			operation.ActorContext{PersonaID: "missing"},
		),
	)
	if missingAssignment.Code != http.StatusNotFound {
		t.Fatalf("missing assignment status=%d body=%s", missingAssignment.Code, missingAssignment.Body.String())
	}
	assertAssignmentRuntimeError(
		t,
		missingAssignment,
		"OPS.USER.experiment_assignment_not_found",
	)

	missingExperiment := performAssignmentRequest(
		mux,
		requestWithAssignmentActor(
			http.MethodGet,
			"/ops/experiments/missing/assignment",
			operation.ActorContext{PersonaID: "observed"},
		),
	)
	if missingExperiment.Code != http.StatusNotFound {
		t.Fatalf("missing experiment status=%d body=%s", missingExperiment.Code, missingExperiment.Body.String())
	}
	assertAssignmentRuntimeError(
		t,
		missingExperiment,
		"OPS.USER.experiment_assignment_experiment_not_found",
	)

	publicWrite := performAssignmentRequest(
		mux,
		requestWithAssignmentActor(
			http.MethodPost,
			assignmentPath,
			operation.ActorContext{PersonaID: "observed"},
		),
	)
	if publicWrite.Code != http.StatusNotFound || store.count() != 1 {
		t.Fatalf("public write status=%d facts=%d body=%s", publicWrite.Code, store.count(), publicWrite.Body.String())
	}
	assertAssignmentRuntimeError(t, publicWrite, "GATEWAY.USER.route_not_found")
}

func requestWithAssignmentActor(
	method string,
	path string,
	actor operation.ActorContext,
) *http.Request {
	request := httptest.NewRequest(method, path, nil)
	return request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: actor},
	))
}

func performAssignmentRequest(handler http.Handler, request *http.Request) *httptest.ResponseRecorder {
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func decodeAssignmentResponse(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	target any,
) {
	t.Helper()
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response %s: %v", recorder.Body.String(), err)
	}
}

func assertAssignmentRuntimeError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantCode string,
) {
	t.Helper()
	var response rterr.ErrorResponse
	decodeAssignmentResponse(t, recorder, &response)
	if response.Code != wantCode {
		t.Fatalf("runtime error code=%q want=%q body=%s", response.Code, wantCode, recorder.Body.String())
	}
}
