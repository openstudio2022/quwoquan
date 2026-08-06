// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
// readiness_case: stream-assistant-run-events-api
package assistant_run_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

// runEventStreamIntegrationFailsafe is the wall clock this case refuses to
// cross. The declared bounds below are an order of magnitude shorter, so
// crossing it means the run event stream is once again unbounded against the
// real journal rather than merely slow.
const runEventStreamIntegrationFailsafe = 20 * time.Second

// TestRunEventStreamOverRealJournalIsBoundedWhileRunStaysActive is the
// production shape of the hang: a run persisted in MongoDB that never reaches a
// terminal state, streamed through the real inbound adapter over the real
// journal repository. Before the operation declared a stream budget there was
// nothing in this path to end the connection, and the request never returned.
func TestRunEventStreamOverRealJournalIsBoundedWhileRunStaysActive(t *testing.T) {
	database := requirePublicWebMongo(t)
	for _, collection := range []string{
		"assistant_runs",
		"assistant_run_events",
		"assistant_run_command_receipts",
	} {
		if _, err := database.Collection(collection).DeleteMany(
			t.Context(),
			map[string]any{},
		); err != nil {
			t.Fatalf("reset %s: %v", collection, err)
		}
	}
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	commands := runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		runruntime.StaticSkillPackageIdentityResolver{
			PackageID:     "assistant.session.skills",
			ReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(intersectionEvidencePolicyResolver()),
	)
	started, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "user-stream-budget",
		SessionID:       "session-stream-budget",
		ClientRequestID: "request-stream-budget",
		InputText:       "这次执行不会进入终态",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	if started.CompletedAt != nil {
		t.Fatal("this case requires a run that stays active")
	}

	// The declared production bounds are minutes long by design, so the shape is
	// reproduced at the same ordering with a scaled budget. The unscaled values
	// are asserted to come from the descriptor below.
	scaled := rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   5000,
		IdleMilliseconds:        900,
		MaxDurationMilliseconds: 10000,
	}
	handler := runhttp.NewHandler(
		commands,
		runhttp.WithRunEventStreamBudget(scaled),
	)
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+started.RunID+"/events",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "user-stream-budget")
	served := make(chan time.Duration, 1)
	begin := time.Now()
	go func() {
		handler.Routes().ServeHTTP(recorder, request)
		served <- time.Since(begin)
	}()
	var elapsed time.Duration
	select {
	case elapsed = <-served:
	case <-time.After(runEventStreamIntegrationFailsafe):
		t.Fatalf(
			"run event stream over the real journal never returned within %s",
			runEventStreamIntegrationFailsafe,
		)
	}

	if recorder.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", recorder.Code, recorder.Body)
	}
	if got := recorder.Header().Get("Content-Type"); got != "text/event-stream" {
		t.Fatalf("stream content type=%q", got)
	}
	if !strings.Contains(recorder.Body.String(), `"runId":"`+started.RunID+`"`) {
		t.Fatalf("stream did not replay the persisted journal: %s", recorder.Body)
	}
	if elapsed < 700*time.Millisecond {
		t.Fatalf("idle bound=900ms closed the stream early after %s", elapsed)
	}
	if elapsed > scaled.MaxDuration() {
		t.Fatalf(
			"stalled stream survived past its idle bound to %s: only the lifetime closed it",
			elapsed,
		)
	}
	// A bounded close is a transport decision. The run keeps executing and the
	// client resumes from the last event id, so the aggregate must be untouched.
	current, err := commands.Get(
		t.Context(),
		"user-stream-budget",
		started.RunID,
	)
	if err != nil {
		t.Fatalf("reload run after bounded close: %v", err)
	}
	if current.CompletedAt != nil {
		t.Fatal("bounding the connection must not terminate the persisted run")
	}
}

// TestRunEventStreamProductionBudgetIsContractDeclared keeps the deployed values
// on the contract. The case above scales the durations to stay fast; without
// this one, nothing would prove the composition root enforces the declared
// budget rather than a duration chosen in the transport.
func TestRunEventStreamProductionBudgetIsContractDeclared(t *testing.T) {
	deployed := runhttp.RunEventStreamBudget()
	var declared *rtauth.OperationStreamBudget
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if descriptor.CanonicalOperationID ==
			"assistant.assistant_run.StreamAssistantRunEvents" {
			declared = descriptor.StreamBudget
			if descriptor.TimeoutMilliseconds !=
				descriptor.StreamBudget.MaxDurationMilliseconds {
				t.Fatalf(
					"streaming timeout=%dms must be derived from max_duration=%dms",
					descriptor.TimeoutMilliseconds,
					descriptor.StreamBudget.MaxDurationMilliseconds,
				)
			}
			break
		}
	}
	if declared == nil {
		t.Fatal("StreamAssistantRunEvents declares no reliability.stream_budget")
	}
	if *declared != deployed {
		t.Fatalf(
			"deployed budget %#v is not the declared budget %#v",
			deployed,
			*declared,
		)
	}
}
