package local_contract

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
	rolloutmetrics "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/observability"
)

func TestMiddlewareRebuildsNetworkAttributesAndUsesVerifiedDevice(t *testing.T) {
	policy := rolloutPolicy("5")
	for _, name := range []string{"canary", "5", "20", "50"} {
		stage := policy.Stages[name]
		stage.Regions = domain.Selector{Mode: "include", Values: []string{"440000"}}
		stage.Carriers = domain.Selector{Mode: "include", Values: []string{"chinatelecom"}}
		policy.Stages[name] = stage
	}
	policy.InternalCanary.DeviceActorIDs = []string{"verified-device"}
	evaluator, err := application.NewEvaluator(
		policy, testAllocationKey, newMemoryStore(), 30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}

	seenTarget := domain.TargetStable
	handler := httpadapter.Middleware(evaluator, fixedNetworkResolver{}, "X-Edge-Client-IP", nil)(
		http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
			seenTarget = application.TargetFromContext(request.Context())
			if got := request.Header.Get("X-Client-Region-Code"); got != "440000" {
				t.Fatalf("region=%q", got)
			}
			if got := request.Header.Get("X-Client-Carrier"); got != "chinatelecom" {
				t.Fatalf("carrier=%q", got)
			}
			response.WriteHeader(http.StatusNoContent)
		}),
	)
	request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
	request.Header.Set("X-Edge-Client-IP", "203.0.113.10")
	request.Header.Set("X-Client-Region-Code", "110000")
	request.Header.Set("X-Client-Carrier", "chinaunicom")
	request.Header.Set("X-Client-Device-Platform", "android")
	request.Header.Set("X-Client-App-Version", "1.9.0")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-1", DeviceActorID: "verified-device"},
	}))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if seenTarget != domain.TargetCandidate {
		t.Fatalf("target=%s", seenTarget)
	}
}

func TestRolloutMetricsAreBoundedAndDistinguishMissingSubjectFromStoreFailure(t *testing.T) {
	registry := prometheus.NewRegistry()
	observer := rolloutmetrics.NewMetrics(registry)
	policy := rolloutPolicy("5")

	missingSubjectEvaluator, err := application.NewEvaluator(
		policy, testAllocationKey, newMemoryStore(), 30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}
	missingSubjectHandler := httpadapter.Middleware(
		missingSubjectEvaluator, fixedNetworkResolver{}, "X-Edge-Client-IP", observer,
	)(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusNoContent)
	}))
	missingSubjectRequest := rolloutMetricRequest()
	missingSubjectResponse := httptest.NewRecorder()
	missingSubjectHandler.ServeHTTP(missingSubjectResponse, missingSubjectRequest)
	if missingSubjectResponse.Code != http.StatusNoContent {
		t.Fatalf("missing subject status=%d", missingSubjectResponse.Code)
	}

	failingStore := newMemoryStore()
	failingStore.failure = errors.New("redis unavailable")
	failingEvaluator, err := application.NewEvaluator(
		policy, testAllocationKey, failingStore, 30*24*time.Hour,
	)
	if err != nil {
		t.Fatal(err)
	}
	failingHandler := httpadapter.Middleware(
		failingEvaluator, fixedNetworkResolver{}, "X-Edge-Client-IP", observer,
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("assignment store failure must fail closed before proxying")
	}))
	failingRequest := rolloutMetricRequest()
	failingRequest = failingRequest.WithContext(rtauth.WithPrincipal(
		failingRequest.Context(),
		rtauth.Principal{Actor: operation.ActorContext{DeviceActorID: "verified-device"}},
	))
	failingResponse := httptest.NewRecorder()
	failingHandler.ServeHTTP(failingResponse, failingRequest)
	if failingResponse.Code != http.StatusServiceUnavailable {
		t.Fatalf("store failure status=%d body=%s", failingResponse.Code, failingResponse.Body.String())
	}
	observer.ObserveDecision(application.DecisionObservation{
		Stage: "5", Target: "stable", Platform: "web", AppVersion: "1.9.0",
		AppBuild: "19000", Region: "203.0.113.1", Carrier: "unknown",
		Reason: "evaluation_failure",
	})
	for index := 0; index < 2100; index++ {
		observer.ObserveDecision(application.DecisionObservation{
			Stage: "5", Target: "stable", Platform: "android",
			AppVersion: fmt.Sprintf("1.%d.0", index), AppBuild: fmt.Sprintf("%d", index),
			Region: fmt.Sprintf("region%d", index), Carrier: fmt.Sprintf("carrier%d", index),
			Reason: "bucket_outside_threshold",
		})
	}

	families, err := registry.Gather()
	if err != nil {
		t.Fatal(err)
	}
	observed := map[string]map[string]string{}
	metricCount := 0
	overflowSeen := false
	for _, family := range families {
		if family.GetName() != "api_edge_rollout_decisions_total" {
			continue
		}
		for _, metric := range family.GetMetric() {
			metricCount++
			labels := map[string]string{}
			for _, label := range metric.GetLabel() {
				name := label.GetName()
				switch name {
				case "deviceActorId", "device_actor_id", "ip", "subjectDigest", "subject_digest":
					t.Fatalf("identifying metric label %q must not exist", name)
				}
				if label.GetValue() == "203.0.113.1" {
					t.Fatalf("source IP must not be retained as metric label %q", name)
				}
				labels[name] = label.GetValue()
			}
			if labels["app_version"] == "overflow" && labels["app_build"] == "overflow" &&
				labels["region"] == "overflow" && labels["carrier"] == "overflow" {
				overflowSeen = true
			}
			observed[labels["reason"]] = labels
		}
	}
	if metricCount > 2049 {
		t.Fatalf("rollout metric series=%d exceeds the 2048 detailed plus bounded overflow contract", metricCount)
	}
	if !overflowSeen {
		t.Fatal("rollout metric series overflow must collapse identifying dimensions")
	}
	assertRolloutMetricLabels(t, observed["missing_rollout_subject"], "stable")
	assertRolloutMetricLabels(t, observed["assignment_store_failure"], "unavailable")
}

func rolloutMetricRequest() *http.Request {
	request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
	request.Header.Set("X-Edge-Client-IP", "203.0.113.10")
	request.Header.Set("X-Client-Device-Platform", "android")
	request.Header.Set("X-Client-App-Version", "1.9.0")
	request.Header.Set("X-Client-App-Build", "19000")
	return request
}

func assertRolloutMetricLabels(t *testing.T, labels map[string]string, target string) {
	t.Helper()
	if labels == nil {
		t.Fatalf("rollout metric for target %q was not recorded", target)
	}
	want := map[string]string{
		"stage": "5", "target": target, "platform": "android",
		"app_version": "1.9.0", "app_build": "19000",
		"region": "440000", "carrier": "chinatelecom",
	}
	for name, expected := range want {
		if labels[name] != expected {
			t.Fatalf("label %s=%q want %q; labels=%v", name, labels[name], expected, labels)
		}
	}
}

type fixedNetworkResolver struct{}

func (fixedNetworkResolver) Resolve(net.IP) httpadapter.NetworkAttributes {
	return httpadapter.NetworkAttributes{Region: "440000", Carrier: "chinatelecom"}
}
