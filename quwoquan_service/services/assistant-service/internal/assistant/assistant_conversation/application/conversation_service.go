package application

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/streaming"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
)

const (
	assistantRunExecutionTimeout  = 3 * time.Minute
	assistantRunExecutionLeaseTTL = 190 * time.Second
)

// runCancelRegistry 登记本实例执行中 turn 的 context.CancelFunc；
// CancelRun 命令据此中断进程内 agent loop。跨实例场景以 Store 的
// running→cancelled CAS 兜底：执行侧 CompleteTurn 会拿回存量 cancelled 终态。
type runCancelRegistry struct {
	mu      sync.Mutex
	cancels map[string]context.CancelFunc
}

func newRunCancelRegistry() *runCancelRegistry {
	return &runCancelRegistry{cancels: map[string]context.CancelFunc{}}
}

func (r *runCancelRegistry) register(turnID string, cancel context.CancelFunc) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.cancels[turnID] = cancel
}

func (r *runCancelRegistry) unregister(turnID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.cancels, turnID)
}

func (r *runCancelRegistry) cancel(turnID string) bool {
	r.mu.Lock()
	cancel, ok := r.cancels[turnID]
	r.mu.Unlock()
	if ok {
		cancel()
	}
	return ok
}

func (s *AssistantService) requireConversationRunStore() (ConversationRunStore, error) {
	if s.conversationRuns == nil {
		return nil, assistantConversationStorageUnavailable(
			"conversation/run store is not configured",
		)
	}
	return s.conversationRuns, nil
}

func (s *AssistantService) CreateConversation(ctx context.Context, userID string, input assistant.CreateConversationInput) (_ assistant.AssistantConversation, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.CreateConversation",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantConversation{}, err
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantConversation{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	input.ClientRequestID = strings.TrimSpace(input.ClientRequestID)
	if input.ClientRequestID == "" {
		return assistant.AssistantConversation{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"clientRequestId 不能为空",
			"missing clientRequestId",
		)
	}
	conversationID, err := rtid.Generate(rtid.PrefixAssistantConversation)
	if err != nil {
		return assistant.AssistantConversation{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成对话 ID 失败", err.Error())
	}
	now := s.now()
	conversation := assistant.AssistantConversation{
		ConversationID:  conversationID,
		UserID:          userID,
		State:           "active",
		Summary:         strings.TrimSpace(input.Summary),
		ClientRequestID: strings.TrimSpace(input.ClientRequestID),
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	stored, _, err := store.InsertConversation(ctx, conversation)
	if err != nil {
		return assistant.AssistantConversation{}, assistantConversationStorageUnavailable(err.Error())
	}
	return stored, nil
}

func (s *AssistantService) GetConversation(ctx context.Context, userID, conversationID string) (_ assistant.AssistantConversation, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetConversation",
		attribute.String("user.id", userID),
		attribute.String("conversation.id", conversationID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantConversation{}, err
	}
	userID = strings.TrimSpace(userID)
	conversationID = strings.TrimSpace(conversationID)
	conversation, found, err := store.GetConversation(ctx, conversationID)
	if err != nil {
		return assistant.AssistantConversation{}, assistantConversationStorageUnavailable(err.Error())
	}
	if !found || conversation.UserID != userID {
		return assistant.AssistantConversation{}, assistantConversationNotFound()
	}
	return conversation, nil
}

// ListConversations 返回 owner 的会话切片（updatedAt desc keyset 分页）。
func (s *AssistantService) ListConversations(ctx context.Context, userID string, limit int, cursor string) (_ assistant.AssistantConversationListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListConversations",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantConversationListView{}, err
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantConversationListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	items, nextCursor, err := store.ListConversations(ctx, userID, limit, strings.TrimSpace(cursor))
	if err != nil {
		if strings.Contains(err.Error(), "invalid conversations cursor") {
			return assistant.AssistantConversationListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "分页游标无效", err.Error())
		}
		return assistant.AssistantConversationListView{}, assistantConversationStorageUnavailable(err.Error())
	}
	return assistant.AssistantConversationListView{Items: items, NextCursor: nextCursor}, nil
}

// ListConversationTurns 返回 owner 会话内终态轮次摘要（createdAt desc keyset 分页）。
func (s *AssistantService) ListConversationTurns(ctx context.Context, userID, conversationID string, limit int, cursor string) (_ assistant.AssistantTurnListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListConversationTurns",
		attribute.String("user.id", userID),
		attribute.String("conversation.id", conversationID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantTurnListView{}, err
	}
	userID = strings.TrimSpace(userID)
	conversationID = strings.TrimSpace(conversationID)
	conversation, found, err := store.GetConversation(ctx, conversationID)
	if err != nil {
		return assistant.AssistantTurnListView{}, assistantConversationStorageUnavailable(err.Error())
	}
	if !found || conversation.UserID != userID {
		return assistant.AssistantTurnListView{}, assistantConversationNotFound()
	}
	turns, nextCursor, err := store.ListTurns(ctx, userID, conversationID, limit, strings.TrimSpace(cursor))
	if err != nil {
		if strings.Contains(err.Error(), "invalid turns cursor") {
			return assistant.AssistantTurnListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "分页游标无效", err.Error())
		}
		return assistant.AssistantTurnListView{}, assistantRunStorageUnavailable(err.Error())
	}
	items := make([]assistant.AssistantTurnSummaryView, 0, len(turns))
	for _, turn := range turns {
		items = append(items, assistantTurnSummaryView(turn))
	}
	return assistant.AssistantTurnListView{Items: items, NextCursor: nextCursor}, nil
}

func assistantTurnSummaryView(turn assistant.AssistantTurn) assistant.AssistantTurnSummaryView {
	summary := assistant.AssistantTurnSummaryView{
		TurnID:           turn.TurnID,
		ConversationID:   turn.ConversationID,
		Status:           turn.Status,
		InputText:        turn.Input.Text,
		TerminalSnapshot: turn.TerminalSnapshot,
		SkillID:          turn.SkillID,
		DomainID:         turn.DomainID,
		CreatedAt:        turn.CreatedAt.UTC().Format(time.RFC3339),
	}
	if turn.CompletedAt != nil {
		summary.CompletedAt = turn.CompletedAt.UTC().Format(time.RFC3339)
	}
	return summary
}

// CancelRun 将 running turn CAS 为 cancelled 终态并中断进程内执行；
// 已终态取消幂等返回当前 turn，不报错（对齐 metadata CancelAssistantRun 语义）。
func (s *AssistantService) CancelRun(ctx context.Context, userID, turnID string) (_ assistant.AssistantTurn, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.CancelRun",
		attribute.String("user.id", userID),
		attribute.String("turn.id", turnID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	turn, err := s.GetTurn(ctx, userID, turnID)
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	if turn.Status != "running" {
		return turn, nil
	}
	now := s.now()
	cancelled := turn
	cancelled.Status = "cancelled"
	cancelled.CompletedAt = &now
	events, err := s.listAllRunEvents(ctx, turn.TurnID, 0)
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	terminalSnapshot := ProjectAssistantRunTerminalSnapshot(
		events,
		turn.FrozenPolicySelection.PublicRef(),
	)
	cancelled.TerminalSnapshot = &terminalSnapshot
	lastSeq := turn.StreamState.LastSeq
	if len(events) > 0 && events[len(events)-1].Seq > lastSeq {
		lastSeq = events[len(events)-1].Seq
	}
	cancelled.StreamState = assistant.AssistantTurnStreamState{
		LastSeq:     lastSeq,
		Completed:   false,
		ResumeToken: streaming.NewResumeToken(turn.TurnID, lastSeq),
	}
	stored, err := store.CompleteTurn(ctx, cancelled)
	if err != nil {
		return assistant.AssistantTurn{}, assistantRunStorageUnavailable(err.Error())
	}
	if s.cache != nil {
		if err := s.cache.Set(ctx, "assistant:run:cancel:"+turn.TurnID, "1", 10*time.Minute); err != nil {
			slog.WarnContext(ctx, "assistant run cancellation signal write failed",
				slog.String("turnId", turn.TurnID), slog.String("error", err.Error()))
		}
	}
	// 中断本实例执行中的 agent loop；其他实例通过上面的持久化终态与 Redis
	// cancellation signal 同步停止。
	if s.runCancels != nil {
		s.runCancels.cancel(turn.TurnID)
	}
	if err := store.UpdateConversationTurnPointer(ctx, turn.ConversationID, "", turn.TurnID, now); err != nil {
		return assistant.AssistantTurn{}, assistantConversationStorageUnavailable(err.Error())
	}
	return stored, nil
}

func (s *AssistantService) CreateTurn(ctx context.Context, userID, conversationID string, input assistant.CreateTurnInput) (_ assistant.AssistantTurn, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.CreateTurn",
		attribute.String("conversation.id", conversationID),
		attribute.String("turn.type", input.TurnType))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	userID = strings.TrimSpace(userID)
	conversationID = strings.TrimSpace(conversationID)
	if strings.TrimSpace(input.Input.Text) == "" {
		return assistant.AssistantTurn{}, AssistantRunInvalidArgument(
			"missing turn input text",
		)
	}
	input.ClientRequestID = strings.TrimSpace(input.ClientRequestID)
	if input.ClientRequestID == "" {
		return assistant.AssistantTurn{}, AssistantRunInvalidArgument(
			"missing clientRequestId",
		)
	}
	conversation, found, err := store.GetConversation(ctx, conversationID)
	if err != nil {
		return assistant.AssistantTurn{}, assistantConversationStorageUnavailable(err.Error())
	}
	if !found || conversation.UserID != userID {
		return assistant.AssistantTurn{}, assistantConversationNotFound()
	}
	existing, found, err := store.GetTurnByClientRequest(
		ctx,
		userID,
		conversationID,
		input.ClientRequestID,
	)
	if err != nil {
		return assistant.AssistantTurn{}, assistantRunStorageUnavailable(err.Error())
	}
	if found {
		return existing, nil
	}
	// 敏感技能在创建点即拒绝（执行点仍有兜底 gate）。
	if err := s.requireSkillConsent(ctx, userID, input.SkillID); err != nil {
		return assistant.AssistantTurn{}, err
	}
	requestContext := input.RequestContext.Normalized()
	if requestContext.PersonaID == "" {
		return assistant.AssistantTurn{},
			runerrors.AppErrorFromRunPolicyUnavailable(
				"verified persona is required before policy selection",
			)
	}
	if s.frozenPolicies == nil {
		return assistant.AssistantTurn{},
			runerrors.AppErrorFromRunPolicyUnavailable(
				"frozen policy resolver is not configured",
			)
	}
	frozenPolicy, err := s.frozenPolicies.ResolveFrozenPolicy(
		ctx,
		"assistant-default",
		requestContext.PersonaID,
		strings.TrimSpace(input.SkillID),
		strings.TrimSpace(input.DomainID),
	)
	if err != nil {
		return assistant.AssistantTurn{},
			runerrors.AppErrorFromRunPolicyUnavailable(err.Error())
	}
	intersectionEvidence, err := s.resolveAuthorizedIntersectionEvidence(
		ctx,
		userID,
		input.ContextSnapshot.IntersectionEvidenceRefs,
	)
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	pageContext := s.loadPageContext(ctx, userID)
	turnID, err := rtid.Generate(rtid.PrefixAssistantTurn)
	if err != nil {
		return assistant.AssistantTurn{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成轮次 ID 失败", err.Error())
	}
	now := s.now()
	turnType := strings.TrimSpace(input.TurnType)
	if turnType == "" {
		turnType = "user"
	}
	trigger := input.Trigger
	trigger.Type = strings.TrimSpace(trigger.Type)
	trigger.MessageID = strings.TrimSpace(trigger.MessageID)
	if trigger.Type == "" {
		trigger.Type = "user_message"
	}
	var sessionPreferences, longTermPreferences []preferencemodel.Snapshot
	if s.preferenceSnapshots != nil {
		sessionPreferences, longTermPreferences, err =
			s.preferenceSnapshots.ResolveActiveSnapshots(
				ctx,
				userID,
				conversationID,
			)
		if err != nil {
			return assistant.AssistantTurn{}, err
		}
	}
	feedbackContext := s.ResolveFeedbackContextSnapshot(
		ctx,
		userID,
		requestContext.PersonaID,
		frozenPolicy.LearningContextPolicy,
		now,
	)
	turn := assistant.AssistantTurn{
		TurnID:                  turnID,
		ConversationID:          conversationID,
		UserID:                  userID,
		TurnType:                turnType,
		Status:                  "running",
		SkillID:                 frozenPolicy.Template.SkillID,
		DomainID:                frozenPolicy.Template.DomainID,
		PageContext:             pageContext,
		IntersectionEvidence:    intersectionEvidence,
		SessionPreferenceFacts:  sessionPreferences,
		LongTermPreferenceFacts: longTermPreferences,
		Input: assistant.AssistantTurnInput{
			Text: strings.TrimSpace(input.Input.Text),
		},
		Trigger:                 trigger,
		ClientRequestID:         strings.TrimSpace(input.ClientRequestID),
		RequestContext:          requestContext,
		FrozenPolicySelection:   frozenPolicy,
		FeedbackContextSnapshot: feedbackContext,
		TraceID:                 requestContext.TraceID,
		CreatedAt:               now,
	}
	if turn.TraceID == "" {
		turn.TraceID = turnID
	}
	stored, replayed, err := store.InsertTurn(ctx, turn)
	if err != nil {
		return assistant.AssistantTurn{}, assistantRunStorageUnavailable(err.Error())
	}
	if replayed {
		return stored, nil
	}
	if err := store.UpdateConversationTurnPointer(ctx, conversationID, stored.TurnID, stored.TurnID, now); err != nil {
		return assistant.AssistantTurn{}, assistantConversationStorageUnavailable(err.Error())
	}
	return stored, nil
}

func (s *AssistantService) GetTurn(ctx context.Context, userID, turnID string) (_ assistant.AssistantTurn, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetTurn",
		attribute.String("user.id", userID),
		attribute.String("turn.id", turnID))
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := s.requireConversationRunStore()
	if err != nil {
		return assistant.AssistantTurn{}, err
	}
	userID = strings.TrimSpace(userID)
	turnID = strings.TrimSpace(turnID)
	turn, found, err := store.GetTurn(ctx, turnID)
	if err != nil {
		return assistant.AssistantTurn{}, assistantRunStorageUnavailable(err.Error())
	}
	if !found || turn.UserID != userID {
		return assistant.AssistantTurn{}, assistantRunNotFound()
	}
	return turn, nil
}

func (s *AssistantService) ExecuteTurn(ctx context.Context, userID, turnID string) (_ []streaming.Envelope, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ExecuteTurn",
		attribute.String("turn.id", turnID))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.executeTurn(ctx, userID, turnID)
}

func (s *AssistantService) StreamTurn(ctx context.Context, userID, turnID string, emit func(streaming.Envelope) error) (err error) {
	return s.StreamTurnAfterSeq(ctx, userID, turnID, 0, emit)
}

func (s *AssistantService) StreamTurnAfterSeq(
	ctx context.Context,
	userID string,
	turnID string,
	afterSeq uint64,
	emit func(streaming.Envelope) error,
) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.StreamTurn",
		attribute.String("user.id", userID),
		attribute.String("turn.id", turnID),
		attribute.Int64("stream.after_seq", int64(afterSeq)))
	defer func() { rtobs.EndSpan(span, err) }()

	turn, err := s.GetTurn(ctx, userID, turnID)
	if err != nil {
		return err
	}
	if turn.Status == "running" {
		s.startTurnExecution(ctx, userID, turnID)
	}
	return s.followRunEvents(ctx, turn, afterSeq, emit)
}

func (s *AssistantService) executeTurn(ctx context.Context, userID, turnID string) ([]streaming.Envelope, error) {
	store, err := s.requireConversationRunStore()
	if err != nil {
		return nil, err
	}
	turn, err := s.GetTurn(ctx, userID, turnID)
	if err != nil {
		return nil, err
	}
	if turn.Status != "running" {
		events, listErr := s.listAllRunEvents(ctx, turn.TurnID, 0)
		if listErr != nil {
			return nil, listErr
		}
		if len(events) > 0 {
			return events, nil
		}
		return s.replayCompletedTurnStream(turn, nil)
	}
	eventStore, err := s.requireRunEventStore()
	if err != nil {
		return nil, err
	}
	// 敏感技能执行点强制 consent 门（R-CLOUD02）：fail-closed。
	if err := s.requireSkillConsent(ctx, userID, turn.SkillID); err != nil {
		return nil, err
	}
	contextTurns, err := s.conversationContextTurns(ctx, userID, turn)
	if err != nil {
		return nil, err
	}
	turn.ContextTurns = contextTurns
	loop := s.agentLoop
	if loop == nil {
		loop = NewAgentLoop(nil, ReactRuntime{}, s.now)
	}
	startSeq, err := s.latestRunEventSeq(ctx, turn.TurnID)
	if err != nil {
		return nil, err
	}
	// 执行 ctx 可被取消命令中断；SSE 客户端断开不再取消后台执行。
	runCtx, cancelRun := context.WithCancel(ctx)
	defer cancelRun()
	if s.runCancels != nil {
		s.runCancels.register(turn.TurnID, cancelRun)
		defer s.runCancels.unregister(turn.TurnID)
	}
	stopCancellationWatch := s.watchRunCancellation(runCtx, turn.TurnID, cancelRun)
	defer stopCancellationWatch()
	// 首响 SLO 打点：turn 开始到首个用户可见回答事件（answer.delta/final）。
	turnStartedAt := time.Now()
	firstAnswerObserved := false
	persistEvent := func(envelope streaming.Envelope) error {
		if !firstAnswerObserved {
			switch envelope.EventType {
			case string(AssistantStreamEventAnswerDelta):
				firstAnswerObserved = true
				recordAssistantFirstVisibleResponse(time.Since(turnStartedAt))
			}
		}
		if err := eventStore.AppendRunEvent(runCtx, turn.TurnID, envelope); err != nil {
			return assistantRunStorageUnavailable(err.Error())
		}
		return nil
	}
	out, failure, err := loop.RunTurnWithSinkAfterSeq(runCtx, turn, startSeq, persistEvent)
	if cancelledByCommand := runCtx.Err() != nil && ctx.Err() == nil; cancelledByCommand {
		lastSeq := startSeq
		if len(out) > 0 {
			lastSeq = out[len(out)-1].Seq
		}
		projector := NewStreamProjectorAt(turn, s.now, lastSeq)
		envelope, eventErr := projector.Event(AssistantStreamEventCancelled, map[string]any{
			"status": "cancelled",
		})
		if eventErr != nil {
			return nil, eventErr
		}
		if appendErr := eventStore.AppendRunEvent(context.WithoutCancel(ctx), turn.TurnID, envelope); appendErr != nil {
			return nil, assistantRunStorageUnavailable(appendErr.Error())
		}
		if stateErr := s.updateCancelledStreamState(
			context.WithoutCancel(ctx),
			store,
			turn,
			envelope.Seq,
		); stateErr != nil {
			return nil, stateErr
		}
		return append(out, envelope), nil
	}
	if err != nil {
		return nil, err
	}
	snapshotEvents, err := s.listAllRunEvents(ctx, turn.TurnID, 0)
	if err != nil {
		return nil, err
	}
	terminalSnapshot := ProjectAssistantRunTerminalSnapshot(
		snapshotEvents,
		turn.FrozenPolicySelection.PublicRef(),
	)
	if failure != nil && terminalSnapshot.Failure == nil {
		projectedFailure := publicTerminalFailure(*failure)
		terminalSnapshot.Failure = &projectedFailure
	}
	completedAt := s.now()
	completed := turn
	if failure != nil {
		completed.Status = "failed"
	} else {
		completed.Status = "completed"
	}
	completed.TerminalSnapshot = &terminalSnapshot
	// grounding 结果：completed 且成答非空计 success，其余计 failure
	// （recording rule 派生 assistant_grounding_success_rate）。
	recordAssistantGroundingOutcome(
		failure == nil && strings.TrimSpace(terminalSnapshot.AnswerText) != "",
	)
	if completed.SkillID == "" {
		completed.SkillID = skillIDFromEvents(snapshotEvents)
	}
	if completed.DomainID == "" {
		completed.DomainID = domainIDFromEvents(snapshotEvents)
	}
	lastSeq := startSeq
	if len(snapshotEvents) > 0 {
		lastSeq = snapshotEvents[len(snapshotEvents)-1].Seq
	}
	completed.StreamState = assistant.AssistantTurnStreamState{
		LastSeq:     lastSeq,
		Completed:   failure == nil,
		ResumeToken: streaming.NewResumeToken(turn.TurnID, lastSeq),
	}
	completed.CompletedAt = &completedAt
	stored, err := store.CompleteTurn(ctx, completed)
	if err != nil {
		return nil, assistantRunStorageUnavailable(err.Error())
	}
	if stored.Status != completed.Status {
		if stored.Status == "cancelled" {
			projector := NewStreamProjectorAt(stored, s.now, lastSeq)
			cancelledEvent, eventErr := projector.Event(AssistantStreamEventCancelled, map[string]any{
				"status": "cancelled",
			})
			if eventErr != nil {
				return nil, eventErr
			}
			if appendErr := eventStore.AppendRunEvent(context.WithoutCancel(ctx), turn.TurnID, cancelledEvent); appendErr != nil {
				return nil, assistantRunStorageUnavailable(appendErr.Error())
			}
			if stateErr := s.updateCancelledStreamState(
				context.WithoutCancel(ctx),
				store,
				stored,
				cancelledEvent.Seq,
			); stateErr != nil {
				return nil, stateErr
			}
			return append(out, cancelledEvent), nil
		}
		return nil, assistantRunStorageUnavailable("run terminal state conflict")
	}
	if err := store.UpdateConversationTurnPointer(ctx, turn.ConversationID, "", turn.TurnID, completedAt); err != nil {
		return nil, assistantConversationStorageUnavailable(err.Error())
	}
	s.recordRunScorecard(ctx, stored)
	return out, nil
}

func (s *AssistantService) requireRunEventStore() (AssistantRunEventStore, error) {
	if s.runEvents == nil {
		return nil, assistantRunStorageUnavailable("assistant run event store is not configured")
	}
	return s.runEvents, nil
}

func (s *AssistantService) latestRunEventSeq(ctx context.Context, runID string) (uint64, error) {
	events, err := s.listAllRunEvents(ctx, runID, 0)
	if err != nil {
		return 0, err
	}
	if len(events) == 0 {
		return 0, nil
	}
	return events[len(events)-1].Seq, nil
}

func (s *AssistantService) listAllRunEvents(
	ctx context.Context,
	runID string,
	afterSeq uint64,
) ([]streaming.Envelope, error) {
	store, err := s.requireRunEventStore()
	if err != nil {
		return nil, err
	}
	events := make([]streaming.Envelope, 0)
	for {
		page, listErr := store.ListRunEvents(ctx, runID, afterSeq, 200)
		if listErr != nil {
			return nil, assistantRunStorageUnavailable(listErr.Error())
		}
		events = append(events, page...)
		if len(page) < 200 {
			return events, nil
		}
		afterSeq = page[len(page)-1].Seq
	}
}

func (s *AssistantService) startTurnExecution(ctx context.Context, userID, turnID string) {
	if s.runExecutions == nil {
		s.runExecutions = newRunExecutionRegistry()
	}
	s.runExecutions.start(turnID, func() {
		executionCtx, cancel := context.WithTimeout(
			context.WithoutCancel(ctx),
			assistantRunExecutionTimeout,
		)
		defer cancel()
		acquired, err := s.claimRunExecution(executionCtx, turnID)
		if err != nil {
			s.failTurnExecution(context.WithoutCancel(executionCtx), userID, turnID, err)
			return
		}
		if !acquired {
			return
		}
		if _, err := s.executeTurn(executionCtx, userID, turnID); err != nil {
			s.failTurnExecution(context.WithoutCancel(executionCtx), userID, turnID, err)
		}
	})
}

func (s *AssistantService) claimRunExecution(
	ctx context.Context,
	turnID string,
) (bool, error) {
	if s.cache == nil {
		// 仅测试装配允许无 Redis；生产 composition 会 fail-fast。
		return true, nil
	}
	acquired, err := s.cache.SetNX(
		ctx,
		"assistant:run:execution:"+turnID,
		turnID,
		assistantRunExecutionLeaseTTL,
	)
	if err != nil {
		return false, fmt.Errorf(
			"acquire assistant run execution lease: %w",
			err,
		)
	}
	return acquired, nil
}

func (s *AssistantService) followRunEvents(
	ctx context.Context,
	initial assistant.AssistantTurn,
	afterSeq uint64,
	emit func(streaming.Envelope) error,
) error {
	eventStore, err := s.requireRunEventStore()
	if err != nil {
		return err
	}
	store, err := s.requireConversationRunStore()
	if err != nil {
		return err
	}
	lastSeq := afterSeq
	emittedCount := 0
	sawCancellation := false
	poll := time.NewTicker(40 * time.Millisecond)
	defer poll.Stop()
	retryStart := time.NewTicker(time.Second)
	defer retryStart.Stop()
	current := initial
	for {
		events, listErr := eventStore.ListRunEvents(ctx, current.TurnID, lastSeq, 200)
		if listErr != nil {
			return assistantRunStorageUnavailable(listErr.Error())
		}
		for _, envelope := range events {
			if envelope.Seq <= lastSeq {
				continue
			}
			if emit != nil {
				if err := emit(envelope); err != nil {
					return err
				}
			}
			emittedCount++
			if envelope.EventType == string(AssistantStreamEventCancelled) {
				sawCancellation = true
			}
			lastSeq = envelope.Seq
		}
		if len(events) == 200 {
			continue
		}
		stored, found, getErr := store.GetTurn(ctx, current.TurnID)
		if getErr != nil {
			return assistantRunStorageUnavailable(getErr.Error())
		}
		if !found || stored.UserID != current.UserID {
			return assistantRunNotFound()
		}
		current = stored
		if current.Status != "running" {
			if current.Status == "cancelled" && !sawCancellation {
				if emittedCount == 0 &&
					current.StreamState.LastSeq > 0 &&
					afterSeq >= current.StreamState.LastSeq {
					return nil
				}
				replay := current
				if replay.StreamState.LastSeq <= lastSeq {
					replay.StreamState.LastSeq = lastSeq + 1
					replay.StreamState.ResumeToken = streaming.NewResumeToken(
						replay.TurnID,
						replay.StreamState.LastSeq,
					)
				}
				_, replayErr := s.replayCompletedTurnStream(replay, emit)
				return replayErr
			}
			if emittedCount == 0 {
				if current.StreamState.LastSeq > 0 &&
					afterSeq >= current.StreamState.LastSeq {
					return nil
				}
				_, replayErr := s.replayCompletedTurnStream(current, emit)
				return replayErr
			}
			if lastSeq < current.StreamState.LastSeq {
				continue
			}
			return nil
		}
		select {
		case <-ctx.Done():
			// 客户端主动断开是正常的 SSE 生命周期；后台执行继续并写入事件日志。
			return nil
		case <-retryStart.C:
			s.startTurnExecution(ctx, current.UserID, current.TurnID)
		case <-poll.C:
		}
	}
}

func (s *AssistantService) watchRunCancellation(
	ctx context.Context,
	turnID string,
	cancel context.CancelFunc,
) func() {
	if s.cache == nil {
		return func() {}
	}
	done := make(chan struct{})
	var once sync.Once
	go func() {
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-done:
				return
			case <-ticker.C:
				value, err := s.cache.Get(ctx, "assistant:run:cancel:"+turnID)
				if err == nil && value == "1" {
					cancel()
					return
				}
			}
		}
	}()
	return func() {
		once.Do(func() { close(done) })
	}
}

func (s *AssistantService) updateCancelledStreamState(
	ctx context.Context,
	store ConversationRunStore,
	turn assistant.AssistantTurn,
	lastSeq uint64,
) error {
	turn.Status = "cancelled"
	current, found, getErr := store.GetTurn(ctx, turn.TurnID)
	if getErr != nil {
		return assistantRunStorageUnavailable(getErr.Error())
	}
	if found && current.Status == "cancelled" && current.CompletedAt != nil {
		turn.CompletedAt = current.CompletedAt
	}
	if turn.CompletedAt == nil {
		completedAt := s.now()
		turn.CompletedAt = &completedAt
	}
	events, err := s.listAllRunEvents(ctx, turn.TurnID, 0)
	if err != nil {
		return err
	}
	terminalSnapshot := ProjectAssistantRunTerminalSnapshot(
		events,
		turn.FrozenPolicySelection.PublicRef(),
	)
	turn.TerminalSnapshot = &terminalSnapshot
	turn.StreamState = assistant.AssistantTurnStreamState{
		LastSeq:     lastSeq,
		Completed:   false,
		ResumeToken: streaming.NewResumeToken(turn.TurnID, lastSeq),
	}
	stored, err := store.CompleteTurn(ctx, turn)
	if err != nil {
		return assistantRunStorageUnavailable(err.Error())
	}
	if stored.Status != "cancelled" ||
		stored.StreamState.LastSeq < lastSeq {
		return assistantRunStorageUnavailable(
			"cancelled run stream state did not advance",
		)
	}
	return nil
}

func (s *AssistantService) failTurnExecution(
	ctx context.Context,
	userID string,
	turnID string,
	executionErr error,
) {
	store, err := s.requireConversationRunStore()
	if err != nil {
		return
	}
	turn, err := s.GetTurn(ctx, userID, turnID)
	if err != nil || turn.Status != "running" {
		return
	}
	eventStore, err := s.requireRunEventStore()
	if err != nil {
		return
	}
	lastSeq, err := s.latestRunEventSeq(ctx, turnID)
	if err != nil {
		return
	}
	failure := modelFailure("run_execution", executionErr)
	projector := NewStreamProjectorAt(turn, s.now, lastSeq)
	envelope, err := projector.Failure(AssistantStreamEventFailed, map[string]any{
		"status": "failed",
	}, failure)
	if err != nil {
		return
	}
	if err := eventStore.AppendRunEvent(ctx, turnID, envelope); err != nil {
		return
	}
	completedAt := s.now()
	turn.Status = "failed"
	turn.CompletedAt = &completedAt
	events, err := s.listAllRunEvents(ctx, turnID, 0)
	if err != nil {
		return
	}
	terminalSnapshot := ProjectAssistantRunTerminalSnapshot(
		events,
		turn.FrozenPolicySelection.PublicRef(),
	)
	if terminalSnapshot.Failure == nil {
		projectedFailure := publicTerminalFailure(failure)
		terminalSnapshot.Failure = &projectedFailure
	}
	turn.TerminalSnapshot = &terminalSnapshot
	turn.StreamState = assistant.AssistantTurnStreamState{
		LastSeq:     envelope.Seq,
		Completed:   false,
		ResumeToken: streaming.NewResumeToken(turnID, envelope.Seq),
	}
	stored, err := store.CompleteTurn(ctx, turn)
	if err != nil || stored.Status != "failed" {
		return
	}
	if err := store.UpdateConversationTurnPointer(ctx, turn.ConversationID, "", turnID, completedAt); err != nil {
		slog.WarnContext(ctx, "assistant failed run pointer update failed",
			slog.String("turnId", turnID), slog.String("error", err.Error()))
	}
	s.recordRunScorecard(ctx, stored)
}

// recordRunScorecard 在 run 终态时写入唯一 AssistantLearningFact。
// eventId 派生自 turnId，durable receipt 保证重复完成幂等；
// 落盘失败只结构化告警，不阻塞用户回答。
func (s *AssistantService) recordRunScorecard(ctx context.Context, turn assistant.AssistantTurn) {
	if s.learningFacts == nil {
		return
	}
	scoreValue := 1.0
	if turn.Status == "failed" {
		scoreValue = 0.0
	}
	score := ServiceScorecardFactCommand{
		EventID:         "turn:" + turn.TurnID + ":completion",
		AssistantTurnID: turn.TurnID,
		DomainID:        turn.DomainID,
		MetricID:        "turn_completion",
		MetricValue:     scoreValue,
		MetricSource:    "service_auto",
		OccurredAt:      s.now(),
	}
	if err := s.learningFacts.AppendServiceScorecard(ctx, score); err != nil {
		slog.WarnContext(ctx, "assistant run scorecard record failed",
			slog.String("turnId", turn.TurnID), slog.String("error", err.Error()))
	}
}

// replayCompletedTurnStream 为已终态 turn 提供确定性的重放事件；
// 服务重启后 SSE 重连不再 404，而是收到终态摘要并立即完成。
func (s *AssistantService) replayCompletedTurnStream(
	turn assistant.AssistantTurn,
	emit func(streaming.Envelope) error,
) ([]streaming.Envelope, error) {
	payload := map[string]any{
		"conversationId": turn.ConversationID,
		"turnId":         turn.TurnID,
		"status":         turn.Status,
		"resumeToken":    turn.StreamState.ResumeToken,
	}
	if turn.TerminalSnapshot != nil {
		payload["processes"] = turn.TerminalSnapshot.Processes
	}
	eventType := AssistantStreamEventCompleted
	switch turn.Status {
	case "failed":
		eventType = AssistantStreamEventFailed
	case "cancelled":
		eventType = AssistantStreamEventCancelled
	default:
		if turn.TerminalSnapshot != nil &&
			strings.TrimSpace(turn.TerminalSnapshot.AnswerText) != "" {
			payload["finalAnswer"] = turn.TerminalSnapshot.AnswerText
		}
	}
	seq := turn.StreamState.LastSeq
	if seq == 0 {
		seq = 1
	}
	envelope := streaming.Envelope{
		EventID:   turn.TurnID + ":replay",
		StreamID:  turn.TurnID,
		EventType: string(eventType),
		Seq:       seq,
		TraceID:   turn.TraceID,
		Payload:   payload,
		CreatedAt: s.now(),
	}
	if turn.TerminalSnapshot != nil && turn.TerminalSnapshot.Failure != nil {
		envelope.RuntimeFailure = runtimeFailureFromTerminal(
			*turn.TerminalSnapshot.Failure,
		)
	}
	if emit != nil {
		if err := emit(envelope); err != nil {
			return nil, err
		}
	}
	return []streaming.Envelope{envelope}, nil
}

func (s *AssistantService) conversationContextTurns(ctx context.Context, userID string, turn assistant.AssistantTurn) ([]assistant.AssistantConversationContextTurn, error) {
	store, err := s.requireConversationRunStore()
	if err != nil {
		return nil, err
	}
	candidates, err := store.ListCompletedTurns(ctx, userID, turn.ConversationID, 6)
	if err != nil {
		return nil, assistantRunStorageUnavailable(err.Error())
	}
	out := []assistant.AssistantConversationContextTurn{}
	for _, item := range candidates {
		if item.TurnID == turn.TurnID || strings.TrimSpace(item.Input.Text) == "" {
			continue
		}
		out = append(out, assistant.AssistantConversationContextTurn{
			Role:     "user",
			Text:     item.Input.Text,
			SkillID:  item.SkillID,
			DomainID: item.DomainID,
		})
		answer := ""
		if item.TerminalSnapshot != nil {
			answer = strings.TrimSpace(item.TerminalSnapshot.AnswerText)
		}
		if answer != "" {
			out = append(out, assistant.AssistantConversationContextTurn{
				Role:     "assistant",
				Text:     answer,
				SkillID:  item.SkillID,
				DomainID: item.DomainID,
			})
		}
	}
	return out, nil
}
