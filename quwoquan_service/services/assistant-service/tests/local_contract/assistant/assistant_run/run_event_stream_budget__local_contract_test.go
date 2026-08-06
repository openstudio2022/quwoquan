// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
// readiness_case: stream-assistant-run-events-local
package assistant_run_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

// streamBudgetTestFailsafe is the wall clock this suite refuses to cross. Every
// case below declares a budget far shorter than it, so crossing it means the run
// event stream has no bound of its own — which is the defect these cases exist
// to catch, not a slow machine.
const streamBudgetTestFailsafe = 8 * time.Second

// blockingRunRepository delays the aggregate read the stream performs before its
// first byte, which is the only way to observe the handshake bound: everything
// the handshake covers (authorization, run load, first journal page) happens
// inside that read.
type blockingRunRepository struct {
	*memoryRunRepository
	loadDelay atomic.Int64
}

func (r *blockingRunRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	if delay := r.loadDelay.Load(); delay > 0 {
		select {
		case <-ctx.Done():
			return runruntime.Run{}, ctx.Err()
		case <-time.After(time.Duration(delay)):
		}
	}
	return r.memoryRunRepository.Load(ctx, runID)
}

// appendProgressEvent publishes one more journal event for a run that is still
// executing. It is what "a healthy long run" looks like to the stream: the
// aggregate never reaches a terminal state, but payload frames keep arriving.
func (r *memoryRunRepository) appendProgressEvent(runID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return
	}
	journal := r.events[runID]
	sequence := int64(0)
	if len(journal) > 0 {
		sequence = journal[len(journal)-1].Sequence
	}
	sequence++
	r.events[runID] = append(journal, runruntime.JournalEvent{
		EventID:   runID + "-progress-" + time.Now().Format("150405.000000000"),
		RunID:     runID,
		Sequence:  sequence,
		Revision:  run.Revision,
		Kind:      "answer_delta",
		Payload:   map[string]any{"delta": "…"},
		CreatedAt: time.Now().UTC(),
	})
	run.JournalSequence = sequence
	r.runs[runID] = run
}

type streamBudgetHarness struct {
	repository *blockingRunRepository
	commands   *runruntime.CommandService
	runID      string
}

func newStreamBudgetHarness(t *testing.T) *streamBudgetHarness {
	t.Helper()
	repository := &blockingRunRepository{
		memoryRunRepository: newMemoryRunRepository(),
	}
	now := time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)
	commands := runruntime.NewCommandService(
		repository,
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
	started, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-budget",
		SessionID:       "session-budget",
		ClientRequestID: "request-budget",
		InputText:       "这次执行会一直跑，不要提前收连接",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	if started.CompletedAt != nil {
		t.Fatal("harness run must stay non-terminal to exercise the stream bounds")
	}
	return &streamBudgetHarness{
		repository: repository,
		commands:   commands,
		runID:      started.RunID,
	}
}

// serveStream drives the real run event route under a scaled budget and returns
// once the handler does. A handler with no bound of its own never returns, so
// the failsafe is what turns the defect into a test failure instead of a hung
// suite.
func (harness *streamBudgetHarness) serveStream(
	t *testing.T,
	budget rtauth.OperationStreamBudget,
) (*httptest.ResponseRecorder, time.Duration) {
	t.Helper()
	handler := runhttp.NewHandler(
		harness.commands,
		runhttp.WithRunEventStreamBudget(budget),
	)
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/runs/"+harness.runID+"/events",
		nil,
	)
	request.Header.Set("X-Client-User-Id", "user-budget")
	served := make(chan time.Duration, 1)
	started := time.Now()
	go func() {
		handler.Routes().ServeHTTP(recorder, request)
		served <- time.Since(started)
	}()
	select {
	case elapsed := <-served:
		return recorder, elapsed
	case <-time.After(streamBudgetTestFailsafe):
		t.Fatalf(
			"run event stream never returned within %s: the declared stream budget is not enforced",
			streamBudgetTestFailsafe,
		)
		return nil, 0
	}
}

func countEmittedFrames(body string) int {
	frames := 0
	for _, line := range strings.Split(body, "\n") {
		if strings.HasPrefix(line, "data: ") {
			frames++
		}
	}
	return frames
}

// TestRunEventStreamRejectsHandshakeThatNeverProducesFirstByte proves the
// handshake bound. Nothing has reached the wire yet, so the declared stream
// error code is owed to the caller rather than a silently closed socket.
func TestRunEventStreamRejectsHandshakeThatNeverProducesFirstByte(t *testing.T) {
	t.Parallel()
	harness := newStreamBudgetHarness(t)
	harness.repository.loadDelay.Store(int64(streamBudgetTestFailsafe))

	recorder, elapsed := harness.serveStream(t, rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   150,
		IdleMilliseconds:        4000,
		MaxDurationMilliseconds: 6000,
	})

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf(
			"handshake overrun status=%d body=%s",
			recorder.Code,
			recorder.Body,
		)
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode handshake failure: %v body=%s", err, recorder.Body)
	}
	if failure.Code != "ASSISTANT.SYSTEM.stream_unavailable" {
		t.Fatalf("handshake failure code drifted: %s", recorder.Body)
	}
	// The idle bound is 4s and the lifetime 6s; returning near 150ms proves the
	// handshake bound fired and not one of the other two.
	if elapsed > 2*time.Second {
		t.Fatalf(
			"handshake bound=150ms fired after %s: a wider bound closed the stream",
			elapsed,
		)
	}
}

// TestRunEventStreamClosesLiveConnectionWithoutProgress proves the idle bound
// on the exact shape that used to hang: headers are on the wire, the run never
// reaches a terminal state, and no further events arrive.
func TestRunEventStreamClosesLiveConnectionWithoutProgress(t *testing.T) {
	t.Parallel()
	harness := newStreamBudgetHarness(t)

	recorder, elapsed := harness.serveStream(t, rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   3000,
		IdleMilliseconds:        500,
		MaxDurationMilliseconds: 6000,
	})

	if recorder.Code != http.StatusOK {
		t.Fatalf("idle close status=%d body=%s", recorder.Code, recorder.Body)
	}
	if got := recorder.Header().Get("Content-Type"); got != "text/event-stream" {
		t.Fatalf("stream content type=%q", got)
	}
	if frames := countEmittedFrames(recorder.Body.String()); frames == 0 {
		t.Fatalf("idle close discarded the frames already produced: %q", recorder.Body)
	}
	if elapsed < 400*time.Millisecond {
		t.Fatalf("idle bound=500ms closed early after %s", elapsed)
	}
	// The lifetime is 6s, so returning well before it proves idle fired.
	if elapsed > 3*time.Second {
		t.Fatalf("idle bound=500ms did not close a stalled stream: elapsed=%s", elapsed)
	}
	// A bounded close is not a run outcome: the aggregate is still executing and
	// the client resumes from the last event id, so no terminal frame is owed.
	for _, terminal := range []string{"completed", "failed", "cancelled"} {
		if strings.Contains(
			recorder.Body.String(),
			"event: "+terminal+"\n",
		) {
			t.Fatalf(
				"idle close invented terminal event %q for a running run",
				terminal,
			)
		}
	}
	run, err := harness.commands.Get(
		context.Background(),
		"user-budget",
		harness.runID,
	)
	if err != nil {
		t.Fatalf("reload run after idle close: %v", err)
	}
	if run.CompletedAt != nil {
		t.Fatal("closing the connection must not terminate the run itself")
	}
}

// TestRunEventStreamKeepsProgressingRunOpenUntilDeclaredLifetime is the case the
// idle bound is easiest to get wrong on: a run that legitimately outlives the
// idle bound many times over, because it keeps producing events. The idle bound
// must never fire here, and only the declared lifetime may close the stream.
func TestRunEventStreamKeepsProgressingRunOpenUntilDeclaredLifetime(t *testing.T) {
	t.Parallel()
	harness := newStreamBudgetHarness(t)
	const (
		idleBound = 500 * time.Millisecond
		lifetime  = 2200 * time.Millisecond
	)
	producing := make(chan struct{})
	var producer sync.WaitGroup
	producer.Add(1)
	go func() {
		defer producer.Done()
		ticker := time.NewTicker(150 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-producing:
				return
			case <-ticker.C:
				harness.repository.appendProgressEvent(harness.runID)
			}
		}
	}()
	defer func() {
		close(producing)
		producer.Wait()
	}()

	recorder, elapsed := harness.serveStream(t, rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   3000,
		IdleMilliseconds:        int(idleBound / time.Millisecond),
		MaxDurationMilliseconds: int(lifetime / time.Millisecond),
	})

	if recorder.Code != http.StatusOK {
		t.Fatalf("lifetime close status=%d body=%s", recorder.Code, recorder.Body)
	}
	// The run outlived its idle bound more than four times over. Closing before
	// the declared lifetime would mean continuous progress was mistaken for a
	// stalled producer.
	if elapsed < lifetime-300*time.Millisecond {
		t.Fatalf(
			"stream with continuous events closed after %s, before its %s lifetime: idle bound cannot tell progress from a stall",
			elapsed,
			lifetime,
		)
	}
	if elapsed > lifetime+2*time.Second {
		t.Fatalf(
			"declared lifetime=%s did not close a healthy stream: elapsed=%s",
			lifetime,
			elapsed,
		)
	}
	// Frames spanning several idle windows are what makes the assertion above a
	// statement about idle discrimination rather than about timing luck.
	if frames := countEmittedFrames(recorder.Body.String()); frames < 4 {
		t.Fatalf(
			"expected continuous progress across idle windows, emitted %d frames",
			frames,
		)
	}
}

// TestRunEventStreamBudgetComesFromTheOperationDescriptor keeps the enforced
// values tied to the contract. A literal here — or a hand-picked default when
// the descriptor lookup fails — is exactly how a transport value ends up
// preempting the declared budget.
func TestRunEventStreamBudgetComesFromTheOperationDescriptor(t *testing.T) {
	t.Parallel()
	budget := runhttp.RunEventStreamBudget()
	if budget.HandshakeMilliseconds <= 0 ||
		budget.IdleMilliseconds <= 0 ||
		budget.MaxDurationMilliseconds <= 0 {
		t.Fatalf(
			"StreamAssistantRunEvents descriptor carries no stream budget: %#v",
			budget,
		)
	}
	if budget.HandshakeMilliseconds >= budget.MaxDurationMilliseconds ||
		budget.IdleMilliseconds >= budget.MaxDurationMilliseconds {
		t.Fatalf("unreachable stream budget: %#v", budget)
	}
	var descriptor rtauth.OperationSecurityDescriptor
	found := false
	for _, candidate := range operationsecurity.ForDomain("assistant") {
		if candidate.CanonicalOperationID ==
			"assistant.assistant_run.StreamAssistantRunEvents" {
			descriptor = candidate
			found = true
			break
		}
	}
	if !found {
		t.Fatal("StreamAssistantRunEvents has no generated descriptor")
	}
	if descriptor.StreamBudget == nil {
		t.Fatal("StreamAssistantRunEvents descriptor lost its stream budget")
	}
	if *descriptor.StreamBudget != budget {
		t.Fatalf(
			"enforced budget %#v drifted from descriptor %#v",
			budget,
			*descriptor.StreamBudget,
		)
	}
	// The scalar budget stays available for consumers that only understand one
	// number, but it must be the derived connection lifetime rather than an
	// independently authored second value.
	if descriptor.TimeoutMilliseconds != budget.MaxDurationMilliseconds {
		t.Fatalf(
			"derived timeout=%dms must equal max_duration=%dms",
			descriptor.TimeoutMilliseconds,
			budget.MaxDurationMilliseconds,
		)
	}
}
