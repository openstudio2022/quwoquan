package runruntime

import (
	"context"
	"errors"
	"reflect"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	maxContextSummaryBytes       = 16 * 1024
	maxRecentContextObservations = 8
)

// ContextProgressReceipt is the idempotent Run-owned write unit for AgentLoop
// progress. State is persisted at every safe tool/plan boundary; Compaction is
// present only when CheckpointEvery requires a new bounded semantic summary.
type ContextProgressReceipt struct {
	Scope      string
	Sequence   int64
	State      ContextExecutionState
	Compaction *ContextCompactionCheckpoint
}

// ContextProgressSink persists one receipt through the AssistantRun CAS
// repository. It is injected by DurableWorker; AgentLoop cannot write storage
// directly.
type ContextProgressSink func(context.Context, ContextProgressReceipt) error

type ContextCompactionRuntimeConfig struct {
	Scope                  string
	CheckpointEvery        time.Duration
	StartedAt              time.Time
	InitialState           ContextExecutionState
	InitialCompaction      *ContextCompactionCheckpoint
	InitialReceiptSequence int64
	Now                    func() time.Time
	Sink                   ContextProgressSink
}

type contextCompactionRuntime struct {
	mu              sync.Mutex
	scope           string
	checkpointEvery time.Duration
	lastCompactedAt time.Time
	state           ContextExecutionState
	compaction      *ContextCompactionCheckpoint
	receiptSequence int64
	now             func() time.Time
	sink            ContextProgressSink
}

type contextCompactionRuntimeKey struct{}
type contextCompactionBoundaryKey struct{}

// WithContextCompactionRuntime installs one claim-scoped facade over the
// durable Run checkpoint. It stores no process-global state and therefore
// survives a worker replacement only through the supplied CAS sink.
func WithContextCompactionRuntime(
	ctx context.Context,
	config ContextCompactionRuntimeConfig,
) (context.Context, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	config.Scope = strings.TrimSpace(config.Scope)
	if config.Scope == "" || config.CheckpointEvery <= 0 ||
		config.InitialReceiptSequence < 0 || config.Sink == nil {
		return ctx, errors.New("assistant context compaction runtime is invalid")
	}
	if config.Now == nil {
		config.Now = time.Now
	}
	if err := validateContextExecutionState(config.InitialState); err != nil {
		return ctx, err
	}
	startedAt := config.StartedAt.UTC()
	if startedAt.IsZero() {
		startedAt = config.Now().UTC()
	}
	initialCompaction := cloneContextCompaction(config.InitialCompaction)
	lastCompactedAt := startedAt
	if initialCompaction != nil {
		if err := validateContextCompaction(*initialCompaction); err != nil {
			return ctx, err
		}
		if !contextStateAtOrAfter(config.InitialState, initialCompaction.State) {
			return ctx, errors.New("assistant context state precedes compaction checkpoint")
		}
		lastCompactedAt = initialCompaction.CompactedAt.UTC()
	}
	runtime := &contextCompactionRuntime{
		scope:           config.Scope,
		checkpointEvery: config.CheckpointEvery,
		lastCompactedAt: lastCompactedAt,
		state:           cloneContextExecutionState(config.InitialState),
		compaction:      initialCompaction,
		receiptSequence: config.InitialReceiptSequence,
		now:             config.Now,
		sink:            config.Sink,
	}
	return context.WithValue(ctx, contextCompactionRuntimeKey{}, runtime), nil
}

func ContextCompactionAvailable(ctx context.Context) bool {
	_, ok := contextCompactionRuntimeFromContext(ctx)
	return ok
}

// WithContextCompactionBoundary activates persistence for the root AgentLoop.
// Parallel Subagents inherit the durable host capability but do not contend on
// one linear plan cursor; their bounded outputs are merged by the manager.
func WithContextCompactionBoundary(ctx context.Context) context.Context {
	return context.WithValue(ctx, contextCompactionBoundaryKey{}, true)
}

// RestoreContextExecution returns immutable copies of the latest persisted
// cursor and semantic checkpoint for AgentLoop hydration.
func RestoreContextExecution(
	ctx context.Context,
) (ContextExecutionState, *ContextCompactionCheckpoint, bool) {
	runtime, ok := activeContextCompactionRuntimeFromContext(ctx)
	if !ok {
		return ContextExecutionState{}, nil, false
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	return cloneContextExecutionState(runtime.state),
		cloneContextCompaction(runtime.compaction), true
}

func ContextCompactionDue(ctx context.Context) bool {
	runtime, ok := activeContextCompactionRuntimeFromContext(ctx)
	if !ok {
		return false
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	return !runtime.now().UTC().Before(
		runtime.lastCompactedAt.Add(runtime.checkpointEvery),
	)
}

// PersistContextProgress commits the exact execution cursor without forcing a
// model summary. This closes the crash window between periodic compactions and
// prevents a restarted worker from receiving fresh source/tool budgets.
func PersistContextProgress(
	ctx context.Context,
	state ContextExecutionState,
) error {
	runtime, ok := activeContextCompactionRuntimeFromContext(ctx)
	if !ok {
		return nil
	}
	return runtime.commit(ctx, state, nil)
}

// CommitContextCompaction atomically replaces recent observation digests with
// a bounded semantic summary and persists the exact cursor at which it was
// produced. The summary is untrusted presentation-free context, never policy.
func CommitContextCompaction(
	ctx context.Context,
	state ContextExecutionState,
	summaryText string,
) (*ContextCompactionCheckpoint, error) {
	runtime, ok := activeContextCompactionRuntimeFromContext(ctx)
	if !ok {
		return nil, errors.New("assistant context compaction runtime is unavailable")
	}
	summaryText = strings.TrimSpace(summaryText)
	if summaryText == "" || len([]byte(summaryText)) > maxContextSummaryBytes {
		return nil, errors.New("assistant context compaction summary is invalid")
	}
	cleanState := cloneContextExecutionState(state)
	cleanState.RecentObservations = nil
	runtime.mu.Lock()
	currentRevision := int64(0)
	if runtime.compaction != nil {
		currentRevision = runtime.compaction.ContextRevision
	}
	runtime.mu.Unlock()
	checkpoint := &ContextCompactionCheckpoint{
		ContextRevision: currentRevision + 1,
		SummaryText:     summaryText,
		State:           cleanState,
		CompactedAt:     runtime.now().UTC(),
	}
	if err := runtime.commit(ctx, cleanState, checkpoint); err != nil {
		return nil, err
	}
	return cloneContextCompaction(checkpoint), nil
}

func (r *contextCompactionRuntime) commit(
	ctx context.Context,
	state ContextExecutionState,
	compaction *ContextCompactionCheckpoint,
) error {
	if err := validateContextExecutionState(state); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if !contextStateAtOrAfter(state, r.state) {
		return ErrRevisionConflict
	}
	if compaction != nil {
		if err := validateContextCompaction(*compaction); err != nil {
			return err
		}
		expectedRevision := int64(1)
		if r.compaction != nil {
			expectedRevision = r.compaction.ContextRevision + 1
		}
		if compaction.ContextRevision != expectedRevision ||
			!contextStateAtOrAfter(state, compaction.State) {
			return ErrRevisionConflict
		}
	}
	receipt := ContextProgressReceipt{
		Scope:      r.scope,
		Sequence:   r.receiptSequence + 1,
		State:      cloneContextExecutionState(state),
		Compaction: cloneContextCompaction(compaction),
	}
	if err := r.sink(ctx, receipt); err != nil {
		return err
	}
	r.receiptSequence = receipt.Sequence
	r.state = cloneContextExecutionState(state)
	if compaction != nil {
		r.compaction = cloneContextCompaction(compaction)
		r.lastCompactedAt = compaction.CompactedAt.UTC()
	}
	return nil
}

func contextCompactionRuntimeFromContext(
	ctx context.Context,
) (*contextCompactionRuntime, bool) {
	if ctx == nil {
		return nil, false
	}
	runtime, ok := ctx.Value(contextCompactionRuntimeKey{}).(*contextCompactionRuntime)
	return runtime, ok && runtime != nil
}

func activeContextCompactionRuntimeFromContext(
	ctx context.Context,
) (*contextCompactionRuntime, bool) {
	runtime, ok := contextCompactionRuntimeFromContext(ctx)
	active, _ := ctx.Value(contextCompactionBoundaryKey{}).(bool)
	return runtime, ok && active
}

// AppendContextObservation retains only the bounded observation digest needed
// to continue planning after a crash. It never stores raw results or prompts.
func AppendContextObservation(
	state ContextExecutionState,
	observation ContextObservationSnapshot,
) ContextExecutionState {
	next := cloneContextExecutionState(state)
	observation.ToolName = strings.TrimSpace(observation.ToolName)
	observation.Status = strings.TrimSpace(observation.Status)
	observation.Summary = strings.TrimSpace(observation.Summary)
	observation.SourceIDs = uniqueContextStrings(observation.SourceIDs)
	next.RecentObservations = append(next.RecentObservations, observation)
	if len(next.RecentObservations) > maxRecentContextObservations {
		next.RecentObservations = append(
			[]ContextObservationSnapshot(nil),
			next.RecentObservations[len(next.RecentObservations)-maxRecentContextObservations:]...,
		)
	}
	return next
}

// ContextProgressScope is the canonical receipt identity for the current goal
// revision. It intentionally matches budget receipt scoping without exposing
// either receipt sequence to callers.
func ContextProgressScope(run Run) string {
	return budgetReceiptScope(run)
}

func (r *Run) RecordContextProgress(
	receipt ContextProgressReceipt,
	now time.Time,
) error {
	if r == nil || terminalState(r.State) ||
		strings.TrimSpace(receipt.Scope) != ContextProgressScope(*r) ||
		receipt.Sequence <= 0 {
		return ErrInvalidRun
	}
	if err := validateContextExecutionState(receipt.State); err != nil {
		return err
	}
	currentState := ContextExecutionState{}
	currentScope := ""
	currentSequence := int64(0)
	var currentCompaction *ContextCompactionCheckpoint
	if r.Checkpoint != nil {
		currentState = cloneContextExecutionState(r.Checkpoint.ContextState)
		currentScope = strings.TrimSpace(r.Checkpoint.ContextReceiptScope)
		currentSequence = r.Checkpoint.ContextReceiptSeq
		currentCompaction = cloneContextCompaction(r.Checkpoint.ContextCompaction)
	}
	if currentScope == receipt.Scope {
		switch {
		case receipt.Sequence < currentSequence:
			return nil
		case receipt.Sequence == currentSequence:
			if reflect.DeepEqual(currentState, receipt.State) &&
				reflect.DeepEqual(currentCompaction, receipt.Compaction) {
				return nil
			}
			return ErrRevisionConflict
		}
	}
	if !contextStateAtOrAfter(receipt.State, currentState) {
		return ErrRevisionConflict
	}
	if receipt.Compaction != nil {
		if err := validateContextCompaction(*receipt.Compaction); err != nil {
			return err
		}
		expectedRevision := int64(1)
		if currentCompaction != nil {
			expectedRevision = currentCompaction.ContextRevision + 1
		}
		if receipt.Compaction.ContextRevision != expectedRevision ||
			!contextStateAtOrAfter(receipt.State, receipt.Compaction.State) {
			return ErrRevisionConflict
		}
	}
	if r.Checkpoint == nil {
		if _, err := r.CreateCheckpoint(
			"checkpoint:"+r.RunID+":context",
			r.DefinitionOfDone.Outcome,
			nil,
			"",
			remainingBudgetFromConsumption(*r, BudgetConsumption{}),
			now,
		); err != nil {
			return err
		}
	}
	r.Checkpoint.ContextState = cloneContextExecutionState(receipt.State)
	if receipt.Compaction != nil {
		r.Checkpoint.ContextCompaction = cloneContextCompaction(receipt.Compaction)
	}
	r.Checkpoint.ContextReceiptScope = receipt.Scope
	r.Checkpoint.ContextReceiptSeq = receipt.Sequence
	r.touch(now)
	r.Checkpoint.Revision = r.Revision
	return nil
}

func validateContextExecutionState(state ContextExecutionState) error {
	if state.PlanCursor < 0 || state.ToolIteration < 0 ||
		state.ReflectionIteration < 0 || state.NavigationDepth < 0 ||
		state.ToolIteration > state.PlanCursor ||
		state.ReflectionIteration > state.PlanCursor {
		return errors.New("assistant context execution cursor is invalid")
	}
	if len(state.ToolHistory) != state.ToolIteration ||
		len(state.RecentObservations) > maxRecentContextObservations {
		return errors.New("assistant context execution history is invalid")
	}
	if !validUniqueContextStrings(state.SourceIDs) ||
		!validNonBlankContextStrings(state.ToolHistory) ||
		!validNonBlankContextStrings(state.ModelHistory) {
		return errors.New("assistant context execution ledger is invalid")
	}
	for _, observation := range state.RecentObservations {
		if observation.Iteration <= 0 || observation.Iteration > state.PlanCursor ||
			strings.TrimSpace(observation.Status) == "" ||
			strings.TrimSpace(observation.Summary) == "" ||
			!validUniqueContextStrings(observation.SourceIDs) {
			return errors.New("assistant context observation snapshot is invalid")
		}
	}
	return nil
}

func validateContextCompaction(checkpoint ContextCompactionCheckpoint) error {
	if checkpoint.ContextRevision <= 0 ||
		strings.TrimSpace(checkpoint.SummaryText) == "" ||
		len([]byte(checkpoint.SummaryText)) > maxContextSummaryBytes ||
		checkpoint.CompactedAt.IsZero() {
		return errors.New("assistant context compaction checkpoint is invalid")
	}
	return validateContextExecutionState(checkpoint.State)
}

func contextStateAtOrAfter(
	next ContextExecutionState,
	current ContextExecutionState,
) bool {
	if next.PlanCursor < current.PlanCursor ||
		next.ToolIteration < current.ToolIteration ||
		next.ReflectionIteration < current.ReflectionIteration ||
		!stringPrefix(next.ToolHistory, current.ToolHistory) ||
		!stringPrefix(next.ModelHistory, current.ModelHistory) ||
		!stringSetContains(next.SourceIDs, current.SourceIDs) {
		return false
	}
	return true
}

func stringPrefix(values []string, prefix []string) bool {
	if len(values) < len(prefix) {
		return false
	}
	for index := range prefix {
		if values[index] != prefix[index] {
			return false
		}
	}
	return true
}

func stringSetContains(values []string, required []string) bool {
	available := make(map[string]struct{}, len(values))
	for _, value := range values {
		available[value] = struct{}{}
	}
	for _, value := range required {
		if _, ok := available[value]; !ok {
			return false
		}
	}
	return true
}

func validUniqueContextStrings(values []string) bool {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			return false
		}
		if _, ok := seen[value]; ok {
			return false
		}
		seen[value] = struct{}{}
	}
	return true
}

func validNonBlankContextStrings(values []string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return false
		}
	}
	return true
}

func uniqueContextStrings(values []string) []string {
	seen := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			seen[value] = struct{}{}
		}
	}
	result := make([]string, 0, len(seen))
	for value := range seen {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func cloneContextExecutionState(state ContextExecutionState) ContextExecutionState {
	cloned := state
	cloned.SourceIDs = append([]string(nil), state.SourceIDs...)
	cloned.ToolHistory = append([]string(nil), state.ToolHistory...)
	cloned.ModelHistory = append([]string(nil), state.ModelHistory...)
	cloned.RecentObservations = make(
		[]ContextObservationSnapshot,
		len(state.RecentObservations),
	)
	for index, observation := range state.RecentObservations {
		cloned.RecentObservations[index] = observation
		cloned.RecentObservations[index].SourceIDs = append(
			[]string(nil),
			observation.SourceIDs...,
		)
	}
	return cloned
}

func cloneContextCompaction(
	checkpoint *ContextCompactionCheckpoint,
) *ContextCompactionCheckpoint {
	if checkpoint == nil {
		return nil
	}
	cloned := *checkpoint
	cloned.State = cloneContextExecutionState(checkpoint.State)
	return &cloned
}
