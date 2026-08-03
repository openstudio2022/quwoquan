package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	reporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportstore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane/testsupport"
	"quwoquan_service/runtime/operation"
)

func TestConfigInstanceReportCommitsAtomicObjectPacket(t *testing.T) {
	t.Parallel()
	path := t.TempDir() + "/platform-ops.json"
	store := testsupport.NewFileStore(path)
	stateStore, err := reportstore.NewStateStore(store, store)
	if err != nil {
		t.Fatal(err)
	}
	desired := reportapp.DesiredHashReaderFunc(func(
		context.Context,
		string,
		string,
	) (string, error) {
		return "desired-config-hash", nil
	})
	const candidate = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	handler, err := reporthttp.NewHandler(
		reportapp.NewCommandFacade(stateStore, desired, nil),
		reportapp.NewQueryFacade(stateStore),
		candidate,
	)
	if err != nil {
		t.Fatal(err)
	}
	requestBody := `{"environment":"beta","cluster":"beta-control-a","service":"content-service","releaseManifestDigest":"` + candidate + `","effectiveHash":"desired-config-hash","source":"release-package"}`
	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/control-plane/platform/configs/instances/content-service-beta-control-a-0:report",
			bytes.NewBufferString(requestBody),
		)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "service:content-service@beta"},
		}))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt=%d status=%d body=%s", attempt, response.Code, response.Body.String())
		}
	}
	if document, found, err := store.GetDocument(
		"config_instance_reports",
		"content-service-beta-control-a-0",
	); err != nil || !found || document["inSync"] != true {
		t.Fatalf("document found=%v value=%+v err=%v", found, document, err)
	}
	if workflow, found, err := store.GetWorkflow(
		"config_instance_report",
		"content-service-beta-control-a-0",
	); err != nil || !found || workflow.State != "in_sync" {
		t.Fatalf("workflow found=%v value=%+v err=%v", found, workflow, err)
	}
	audits, err := store.ListAudits()
	if err != nil || len(audits) != 1 {
		t.Fatalf("audits=%+v err=%v", audits, err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var state testsupport.FileState
	if err := json.Unmarshal(raw, &state); err != nil {
		t.Fatal(err)
	}
	if len(state.MutationReceipts) != 1 || len(state.MutationOutbox) != 1 {
		t.Fatalf("receipts=%d outbox=%d", len(state.MutationReceipts), len(state.MutationOutbox))
	}
	if state.MutationOutbox[0].EventType != "ConfigInstanceReported" {
		t.Fatalf("outbox=%+v", state.MutationOutbox)
	}
}
