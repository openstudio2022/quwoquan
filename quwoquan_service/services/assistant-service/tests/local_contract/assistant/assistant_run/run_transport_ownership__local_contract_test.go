// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#open-004
package assistant_run_test

import (
	"context"
	"encoding/json"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	sessionhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
)

const assistantSessionInternalImport = "quwoquan_service/services/assistant-service/internal/assistant/assistant_session"

type declaredRoute struct {
	Method    string `yaml:"method"`
	Path      string `yaml:"path"`
	Operation string `yaml:"operation"`
}

func assistantRunServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve assistant run transport ownership test path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatalf("resolve assistant-service root: %v", err)
	}
	return root
}

func declaredAssistantRunRoutes(t *testing.T, root string) []declaredRoute {
	t.Helper()
	payload, err := os.ReadFile(filepath.Join(
		root, "contracts", "assistant", "assistant_run", "operations.yaml",
	))
	if err != nil {
		t.Fatalf("read assistant_run operations: %v", err)
	}
	var document struct {
		APIRoutes []declaredRoute `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("decode assistant_run operations: %v", err)
	}
	if len(document.APIRoutes) == 0 {
		t.Fatal("assistant_run declares no api_routes")
	}
	return document.APIRoutes
}

// servePathTemplate turns the contract path template into a concrete request
// path so ServeMux pattern matching can be observed.
func servePathTemplate(path string) string {
	replaced := path
	for _, segment := range []struct {
		template string
		value    string
	}{
		{"{sessionId}", "session-ownership"},
		{"{runId}", "run-ownership"},
		{"{toolUseId}", "tool-use-ownership"},
	} {
		replaced = strings.ReplaceAll(replaced, segment.template, segment.value)
	}
	return replaced
}

// TestAssistantRunOwnsItsInboundTransportAndSessionDoesNot proves the physical
// split: every AssistantRun api_route resolves inside the assistant_run object
// adapter, and none of them is reachable through AssistantSession orchestration.
func TestAssistantRunOwnsItsInboundTransportAndSessionDoesNot(t *testing.T) {
	t.Parallel()
	root := assistantRunServiceRoot(t)
	routes := declaredAssistantRunRoutes(t, root)

	runMux := http.NewServeMux()
	runhttp.NewHandler(newOwnershipRunCommandService(t)).RegisterRoutes(runMux)
	sessionRoutes := sessionhttp.NewHandler(nil).Routes()

	for _, route := range routes {
		request := httptest.NewRequest(
			route.Method,
			servePathTemplate(route.Path),
			nil,
		)
		if _, pattern := runMux.Handler(request); strings.TrimSpace(pattern) == "" {
			t.Fatalf(
				"AssistantRun adapter does not own %s %s (%s)",
				route.Method,
				route.Path,
				route.Operation,
			)
		}
		recorder := httptest.NewRecorder()
		sessionRoutes.ServeHTTP(recorder, httptest.NewRequest(
			route.Method,
			servePathTemplate(route.Path),
			nil,
		))
		if recorder.Code != http.StatusNotFound {
			t.Fatalf(
				"AssistantSession adapter still serves %s %s: status=%d",
				route.Method,
				route.Path,
				recorder.Code,
			)
		}
	}
}

// TestAssistantRunDoesNotImportAssistantSessionInternals locks the object
// boundary independently of HTTP route behavior. Generated AssistantSession
// wire types remain public contracts; the sibling object's private source does
// not.
func TestAssistantRunDoesNotImportAssistantSessionInternals(t *testing.T) {
	t.Parallel()
	root := filepath.Join(assistantRunServiceRoot(t), "internal", "assistant", "assistant_run")
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(path) != ".go" {
			return nil
		}
		payload, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if strings.Contains(string(payload), assistantSessionInternalImport) {
			t.Errorf("AssistantRun imports AssistantSession private source: %s", path)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("scan AssistantRun imports: %v", err)
	}
}

// TestAssistantRunCancelClosesEntirelyInsideRunObject drives cancel through the
// AssistantRun inbound adapter, its own application use cases and its own
// repository port, and asserts the terminal aggregate plus journal event come
// back without any AssistantSession orchestration in the path.
func TestAssistantRunCancelClosesEntirelyInsideRunObject(t *testing.T) {
	t.Parallel()
	commands := newOwnershipRunCommandService(t)
	started, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-ownership",
		SessionID:       "session-ownership",
		ClientRequestID: "request-ownership",
		InputText:       "取消这次执行前先确认引用",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	handler := runhttp.NewHandler(commands)
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/runs/"+started.RunID+"/cancel",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "user-ownership")
	request.Header.Set("Idempotency-Key", "command-cancel-ownership")
	handler.Routes().ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("cancel through run adapter: status=%d body=%s", recorder.Code, recorder.Body)
	}
	var envelope struct {
		RunID  string `json:"runId"`
		Status string `json:"status"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode run envelope: %v", err)
	}
	if envelope.RunID != started.RunID || envelope.Status != "cancelled" {
		t.Fatalf("run adapter returned %+v", envelope)
	}
	events, err := commands.EventsAfter(
		context.Background(),
		"user-ownership",
		started.RunID,
		1,
		10,
	)
	if err != nil {
		t.Fatalf("read run journal: %v", err)
	}
	if len(events) != 1 || events[0].Kind != "run_cancelled" {
		t.Fatalf("cancel journal is not owned by AssistantRun: %#v", events)
	}
}

// TestAssistantRunAdapterFailsClosedWithoutRunCommandService proves the run
// transport reports the AssistantRun-owned storage failure instead of falling
// back to any AssistantSession path.
func TestAssistantRunAdapterFailsClosedWithoutRunCommandService(t *testing.T) {
	t.Parallel()
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/runs/run-missing/cancel",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "user-ownership")
	request.Header.Set("Idempotency-Key", "command-cancel-missing")
	runhttp.NewHandler(nil).Routes().ServeHTTP(recorder, request)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("unconfigured run adapter status=%d body=%s", recorder.Code, recorder.Body)
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode failure: %v", err)
	}
	if failure.Code != "ASSISTANT.SYSTEM.run_storage_unavailable" {
		t.Fatalf("run adapter failure code drifted: %s", recorder.Body)
	}
}

func newOwnershipRunCommandService(t *testing.T) *runruntime.CommandService {
	t.Helper()
	now := time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)
	return runruntime.NewCommandService(
		newMemoryRunRepository(),
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time {
			now = now.Add(time.Second)
			return now
		},
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
}
