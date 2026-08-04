package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type feedbackContextResolverRecorder struct {
	calls         int
	accountID     string
	personaID     string
	skillID       string
	surfaceKind   string
	packageID     string
	releaseDigest string
	policy        assistantmodel.AssistantFrozenLearningContextPolicy
	frozenAt      time.Time
}

type feedbackContextResolverFunc func(
	context.Context,
	string,
	string,
	string,
	string,
	string,
	string,
	assistantmodel.AssistantFrozenLearningContextPolicy,
	time.Time,
) assistantmodel.AssistantFeedbackContextSnapshot

func (resolve feedbackContextResolverFunc) ResolveFeedbackContext(
	ctx context.Context,
	accountID string,
	personaID string,
	skillID string,
	surfaceKind string,
	packageID string,
	releaseDigest string,
	policy assistantmodel.AssistantFrozenLearningContextPolicy,
	frozenAt time.Time,
) assistantmodel.AssistantFeedbackContextSnapshot {
	return resolve(
		ctx,
		accountID,
		personaID,
		skillID,
		surfaceKind,
		packageID,
		releaseDigest,
		policy,
		frozenAt,
	)
}

func (resolver *feedbackContextResolverRecorder) ResolveFeedbackContext(
	_ context.Context,
	accountID string,
	personaID string,
	skillID string,
	surfaceKind string,
	packageID string,
	releaseDigest string,
	policy assistantmodel.AssistantFrozenLearningContextPolicy,
	frozenAt time.Time,
) assistantmodel.AssistantFeedbackContextSnapshot {
	resolver.calls++
	resolver.accountID = accountID
	resolver.personaID = personaID
	resolver.skillID = skillID
	resolver.surfaceKind = surfaceKind
	resolver.packageID = packageID
	resolver.releaseDigest = releaseDigest
	resolver.policy = policy
	resolver.frozenAt = frozenAt
	return assistantmodel.AssistantFeedbackContextSnapshot{
		Decision:                "injected",
		ConsentID:               "consent-travel",
		DefinitionDigest:        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ConsentGrantedAt:        frozenAt.Add(-time.Hour),
		SourceWatermarkSequence: 12,
		WindowDays:              policy.WindowDays,
		FeedbackSampleCount:     3,
	}
}

func TestAssistantRunCommandServiceOwnsIdempotencyAndJournal(t *testing.T) {
	t.Parallel()

	repository := newMemoryRunRepository()
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	skillPackages := &rotatingSkillPackageResolver{
		packageID:     "assistant.session.skills",
		releaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
	service := runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			_ context.Context,
			userID string,
			sessionID string,
		) (runruntime.SessionContinuity, error) {
			if userID != "user-1" || sessionID != "session-1" {
				return runruntime.SessionContinuity{}, errors.New("session not found")
			}
			return runruntime.SessionContinuity{}, nil
		}),
		skillPackages,
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return now },
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
	command := runruntime.StartCommand{
		UserID:          "user-1",
		SessionID:       "session-1",
		ClientRequestID: "request-1",
		InputText:       "核对公开资料后给出引用答案",
	}

	first, err := service.Start(context.Background(), command)
	if err != nil {
		t.Fatalf("start first run: %v", err)
	}
	skillPackages.releaseDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	replayed, err := service.Start(context.Background(), command)
	if err != nil {
		t.Fatalf("replay start run: %v", err)
	}
	if replayed.RunID != first.RunID {
		t.Fatalf("idempotency replay created another run: %s != %s", replayed.RunID, first.RunID)
	}
	if first.SkillPackageID != "assistant.session.skills" ||
		first.SkillPackageReleaseDigest !=
			"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ||
		replayed.SkillPackageReleaseDigest != first.SkillPackageReleaseDigest ||
		skillPackages.calls != 1 {
		t.Fatalf(
			"Skill package was not frozen: first=%+v replay=%+v activeReads=%d",
			first,
			replayed,
			skillPackages.calls,
		)
	}
	conflicting := command
	conflicting.InputText = "不同用户意图"
	if _, err := service.Start(context.Background(), conflicting); !errors.Is(
		err,
		runruntime.ErrRevisionConflict,
	) {
		t.Fatalf("same key with different input must conflict, got %v", err)
	}
	if _, err := service.Get(context.Background(), "user-2", first.RunID); !errors.Is(
		err,
		runruntime.ErrRunNotFound,
	) {
		t.Fatalf("cross-owner read must look not found, got %v", err)
	}
	events, err := service.EventsAfter(
		context.Background(),
		"user-1",
		first.RunID,
		0,
		10,
	)
	if err != nil {
		t.Fatalf("read journal: %v", err)
	}
	if len(events) != 1 ||
		events[0].Sequence != 1 ||
		events[0].Kind != "run_accepted" {
		t.Fatalf("unexpected initial journal: %#v", events)
	}
}

func TestAssistantRunFreezesPersonalSessionContinuityAndExcludesSharedSurface(t *testing.T) {
	t.Parallel()

	repository := newMemoryRunRepository()
	resolverCalls := 0
	continuity := runruntime.SessionContinuity{
		SummaryID:      "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Text:           "当前目标：完成杭州行程",
		FromTurnID:     "run-history-1",
		ToTurnID:       "run-history-3",
		TurnCount:      3,
		CurrentGoal:    "完成杭州行程",
		ConfirmedFacts: []string{"同行人数为 2 人"},
		PendingItems:   []string{"确认酒店"},
		ConfirmedSlots: map[string]string{"destination": "杭州"},
	}
	service := runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			resolverCalls++
			return continuity, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC) },
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
	command := runruntime.StartCommand{
		UserID:          "user-continuity",
		SessionID:       "session-continuity",
		ClientRequestID: "request-continuity",
		InputText:       "继续上面的计划",
		RequestContext:  runruntime.RequestContext{SurfaceKind: "assistant"},
	}
	personal, err := service.Start(t.Context(), command)
	if err != nil {
		t.Fatalf("start personal Run: %v", err)
	}
	continuity.ConfirmedFacts[0] = "mutated"
	continuity.ConfirmedSlots["destination"] = "mutated"
	if personal.SessionContinuity == nil ||
		personal.SessionContinuity.ConfirmedFacts[0] != "同行人数为 2 人" ||
		personal.SessionContinuity.ConfirmedSlots["destination"] != "杭州" {
		t.Fatalf("AssistantRun did not freeze an immutable continuity snapshot: %+v", personal.SessionContinuity)
	}
	if _, err := service.Start(t.Context(), command); err != nil || resolverCalls != 1 {
		t.Fatalf("idempotent replay re-resolved mutable session state: calls=%d err=%v", resolverCalls, err)
	}

	sharedCommand := command
	sharedCommand.ClientRequestID = "request-continuity-shared"
	sharedCommand.RequestContext = runruntime.RequestContext{SurfaceKind: "conversation"}
	shared, err := service.Start(t.Context(), sharedCommand)
	if err != nil {
		t.Fatalf("start shared Run: %v", err)
	}
	if shared.SessionContinuity != nil {
		t.Fatalf("shared Run leaked personal AssistantSession continuity: %+v", shared.SessionContinuity)
	}
}

func TestAssistantRunFreezesFeedbackContextBeforeExecutionAndExcludesSharedSurface(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	feedback := &feedbackContextResolverRecorder{}
	policy := runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		_ string,
		_ string,
	) (runruntime.FrozenPolicySelection, error) {
		return runruntime.FrozenPolicySelection{
			PolicyID:        policyID,
			ReleaseDigest:   "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			Cohort:          "stable",
			RolloutRevision: 1,
			RuleID:          "travel-companion",
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID: "travel-companion",
				SkillID:    "travel_companion",
				DomainID:   "travel",
			},
			LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
				Enabled:                true,
				AllowedSignals:         []string{"feedback_counts"},
				MinimumFeedbackSamples: 3,
				WindowDays:             30,
			},
		}, nil
	})
	service := runruntime.NewCommandService(
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
		func() time.Time { return now },
		nil,
		runruntime.WithPolicyResolver(policy),
		runruntime.WithFeedbackContextResolver(feedback),
	)
	command := runruntime.StartCommand{
		UserID:           "account-1",
		PersonaID:        "persona-1",
		SessionID:        "session-feedback",
		ClientRequestID:  "request-feedback",
		InputText:        "继续优化杭州旅行计划",
		RequestedSkillID: "travel_companion",
		RequestContext:   runruntime.RequestContext{SurfaceKind: "personal"},
	}
	run, err := service.Start(t.Context(), command)
	if err != nil {
		t.Fatalf("start feedback Run: %v", err)
	}
	if feedback.calls != 1 || feedback.accountID != command.UserID ||
		feedback.personaID != command.PersonaID || feedback.skillID != command.RequestedSkillID ||
		feedback.surfaceKind != "personal" || feedback.frozenAt != now ||
		feedback.packageID != "assistant.session.skills" ||
		feedback.releaseDigest != "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ||
		run.FeedbackContextSnapshot.Decision != "injected" ||
		run.FeedbackContextSnapshot.ConsentID != "consent-travel" {
		t.Fatalf("feedback context was not frozen from current Skill: calls=%d resolver=%+v run=%+v", feedback.calls, feedback, run.FeedbackContextSnapshot)
	}
	if _, err := service.Start(t.Context(), command); err != nil || feedback.calls != 1 {
		t.Fatalf("idempotent replay re-read mutable feedback: calls=%d err=%v", feedback.calls, err)
	}

	shared := command
	shared.ClientRequestID = "request-feedback-shared"
	shared.RequestContext.SurfaceKind = "conversation"
	sharedRun, err := service.Start(t.Context(), shared)
	if err != nil {
		t.Fatalf("start shared feedback Run: %v", err)
	}
	if feedback.calls != 1 ||
		sharedRun.FeedbackContextSnapshot.Decision != "shared_surface_excluded" ||
		sharedRun.FeedbackContextSnapshot.FeedbackSampleCount != 0 {
		t.Fatalf("shared Run exposed private feedback: calls=%d snapshot=%+v", feedback.calls, sharedRun.FeedbackContextSnapshot)
	}
}

func TestAssistantRunRejectsFeedbackSnapshotOutsideFrozenPolicy(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 4, 13, 0, 0, 0, time.UTC)
	policy := runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		_ string,
		_ string,
	) (runruntime.FrozenPolicySelection, error) {
		return runruntime.FrozenPolicySelection{
			PolicyID:        policyID,
			ReleaseDigest:   "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			Cohort:          "stable",
			RolloutRevision: 1,
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID: "travel-companion",
				SkillID:    "travel_companion",
				DomainID:   "travel",
			},
			LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
				Enabled:                true,
				AllowedSignals:         []string{"feedback_counts"},
				MinimumFeedbackSamples: 3,
				WindowDays:             30,
			},
		}, nil
	})
	cases := map[string]assistantmodel.AssistantFeedbackContextSnapshot{
		"unknown decision": {
			Decision:   "caller_invented",
			WindowDays: 30,
		},
		"future consent": {
			Decision:                "injected",
			ConsentID:               "consent-future",
			ConsentGrantedAt:        now.Add(time.Minute),
			DefinitionDigest:        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			SourceWatermarkSequence: 1,
			WindowDays:              30,
			FeedbackSampleCount:     3,
		},
		"metric outside policy": {
			Decision:                "injected",
			ConsentID:               "consent-metric",
			ConsentGrantedAt:        now.Add(-time.Hour),
			DefinitionDigest:        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			SourceWatermarkSequence: 1,
			WindowDays:              30,
			FeedbackSampleCount:     3,
			Metrics: []assistantmodel.AssistantFeedbackMetricSummary{{
				MetricID:    "raw_private_text_score",
				SampleCount: 3,
				Average:     1,
				Latest:      1,
			}},
		},
	}
	for name, snapshot := range cases {
		name, snapshot := name, snapshot
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			service := runruntime.NewCommandService(
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
				func() time.Time { return now },
				nil,
				runruntime.WithPolicyResolver(policy),
				runruntime.WithFeedbackContextResolver(feedbackContextResolverFunc(func(
					context.Context,
					string,
					string,
					string,
					string,
					string,
					string,
					assistantmodel.AssistantFrozenLearningContextPolicy,
					time.Time,
				) assistantmodel.AssistantFeedbackContextSnapshot {
					return snapshot
				})),
			)
			_, err := service.Start(t.Context(), runruntime.StartCommand{
				UserID:           "account-1",
				PersonaID:        "persona-1",
				SessionID:        "session-" + name,
				ClientRequestID:  "request-" + name,
				InputText:        "继续优化旅行计划",
				RequestedSkillID: "travel_companion",
				RequestContext:   runruntime.RequestContext{SurfaceKind: "personal"},
			})
			if !errors.Is(err, runruntime.ErrInvalidRun) {
				t.Fatalf("untrusted feedback snapshot must fail closed, got %v", err)
			}
		})
	}
}

func TestAssistantRunCommandServiceClosesCommandsWithCAS(t *testing.T) {
	t.Parallel()

	repository := newMemoryRunRepository()
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	service := runruntime.NewCommandService(
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
	run, err := service.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-1",
		SessionID:       "session-1",
		ClientRequestID: "request-commands",
		InputText:       "执行一个可暂停任务",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	run, err = service.Pause(
		context.Background(),
		"user-1",
		run.RunID,
		"command-pause",
		"用户暂离",
	)
	if err != nil || run.State.WireName() != "paused" {
		t.Fatalf("pause run: state=%s err=%v", run.State, err)
	}
	run, err = service.Resume(
		context.Background(),
		"user-1",
		run.RunID,
		"command-resume",
	)
	if err != nil || run.State.WireName() != "orienting" {
		t.Fatalf("resume run: state=%s err=%v", run.State, err)
	}
	run, err = service.Steer(
		context.Background(),
		"user-1",
		run.RunID,
		"command-steer",
		"只采用可回查来源",
	)
	if err != nil || run.GoalRevision != 1 {
		t.Fatalf("steer run: goalRevision=%d err=%v", run.GoalRevision, err)
	}
	run, err = service.Cancel(
		context.Background(),
		"user-1",
		run.RunID,
		"command-cancel",
	)
	if err != nil || run.State.WireName() != "cancelled" || run.CompletedAt == nil {
		t.Fatalf("cancel run: state=%s completedAt=%v err=%v", run.State, run.CompletedAt, err)
	}
	revision := run.Revision
	run, err = service.Cancel(
		context.Background(),
		"user-1",
		run.RunID,
		"command-cancel",
	)
	if err != nil || run.Revision != revision {
		t.Fatalf("terminal cancel must be idempotent: revision=%d err=%v", run.Revision, err)
	}
	events, err := service.EventsAfter(
		context.Background(),
		"user-1",
		run.RunID,
		1,
		10,
	)
	if err != nil {
		t.Fatalf("read command journal: %v", err)
	}
	if len(events) != 4 {
		t.Fatalf("expected pause/resume/steer/cancel events, got %#v", events)
	}
	for index, event := range events {
		want := int64(index + 2)
		if event.Sequence != want {
			t.Fatalf("journal sequence gap at %d: got %d want %d", index, event.Sequence, want)
		}
	}
}

type memoryRunRepository struct {
	mu       sync.Mutex
	runs     map[string]runruntime.Run
	requests map[string]string
	events   map[string][]runruntime.JournalEvent
	receipts map[string]runruntime.CommandReceipt
}

func newMemoryRunRepository() *memoryRunRepository {
	return &memoryRunRepository{
		runs:     make(map[string]runruntime.Run),
		requests: make(map[string]string),
		events:   make(map[string][]runruntime.JournalEvent),
		receipts: make(map[string]runruntime.CommandReceipt),
	}
}

func (r *memoryRunRepository) Load(
	_ context.Context,
	runID string,
) (runruntime.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return run, nil
}

func (r *memoryRunRepository) LoadByRequest(
	_ context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	runID, ok := r.requests[userID+"\x00"+sessionID+"\x00"+clientRequestID]
	if !ok {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return r.runs[runID], nil
}

func (r *memoryRunRepository) Commit(
	_ context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, found := r.runs[run.RunID]
	if found {
		if current.Revision != expectedRevision {
			return runruntime.ErrRevisionConflict
		}
	} else if expectedRevision != 0 {
		return runruntime.ErrRevisionConflict
	}
	requestKey := run.UserID + "\x00" + run.SessionID + "\x00" + run.ClientRequestID
	if existingID, ok := r.requests[requestKey]; ok && existingID != run.RunID {
		return runruntime.ErrRevisionConflict
	}
	journal := r.events[run.RunID]
	lastSequence := int64(0)
	if len(journal) > 0 {
		lastSequence = journal[len(journal)-1].Sequence
	}
	for _, event := range events {
		if event.Sequence != lastSequence+1 {
			return runruntime.ErrRevisionConflict
		}
		lastSequence = event.Sequence
		journal = append(journal, event)
	}
	r.runs[run.RunID] = run
	r.requests[requestKey] = run.RunID
	r.events[run.RunID] = journal
	if receipt != nil {
		key := receipt.RunID + "\x00" + receipt.CommandID
		if _, exists := r.receipts[key]; exists {
			return runruntime.ErrRevisionConflict
		}
		r.receipts[key] = *receipt
	}
	return nil
}

func (r *memoryRunRepository) LoadCommandReceipt(
	_ context.Context,
	runID string,
	commandID string,
) (runruntime.CommandReceipt, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	receipt, ok := r.receipts[runID+"\x00"+commandID]
	if !ok {
		return runruntime.CommandReceipt{}, runruntime.ErrRunNotFound
	}
	return receipt, nil
}

func (r *memoryRunRepository) EventsAfter(
	_ context.Context,
	runID string,
	afterSequence int64,
	limit int,
) ([]runruntime.JournalEvent, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.runs[runID]; !ok {
		return nil, runruntime.ErrRunNotFound
	}
	result := make([]runruntime.JournalEvent, 0, limit)
	for _, event := range r.events[runID] {
		if event.Sequence <= afterSequence {
			continue
		}
		result = append(result, event)
		if len(result) == limit {
			break
		}
	}
	return result, nil
}

func (r *memoryRunRepository) LatestSequence(
	_ context.Context,
	runID string,
) (int64, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return 0, runruntime.ErrRunNotFound
	}
	return run.JournalSequence, nil
}
