package compaction

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

const (
	maxNarrativeRunes = 3000
	maxSummaryRunes   = 4000
	maxCommitAttempts = 4
)

var sessionCompactionTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "assistant_session_compaction_total",
		Help: "AssistantSession rolling compaction attempts by bounded outcome.",
	},
	[]string{"outcome"},
)

type CompletedRunSource struct {
	CompletionEventID string
	RunID             string
	SessionID         string
	UserID            string
	CurrentGoal       string
	UserInput         string
	AnswerText        string
	ConfirmedFacts    []string
	PendingItems      []string
	ConfirmedSlots    map[string]string
	CompletedAt       time.Time
}

type NarrativeInput struct {
	PreviousSummary string
	CurrentGoal     string
	UserInput       string
	AnswerText      string
	ConfirmedFacts  []string
	PendingItems    []string
	ConfirmedSlots  map[string]string
}

type NarrativeGenerator interface {
	GenerateRollingNarrative(context.Context, NarrativeInput) (string, error)
}

type NarrativeGeneratorFunc func(context.Context, NarrativeInput) (string, error)

func (generate NarrativeGeneratorFunc) GenerateRollingNarrative(
	ctx context.Context,
	input NarrativeInput,
) (string, error) {
	return generate(ctx, input)
}

type Service struct {
	store     sessionports.SessionStore
	generator NarrativeGenerator
}

func NewService(
	store sessionports.SessionStore,
	generator NarrativeGenerator,
) *Service {
	if store == nil || generator == nil {
		panic("assistant session compaction dependencies are required")
	}
	return &Service{store: store, generator: generator}
}

func (service *Service) CompactCompletedRun(
	ctx context.Context,
	source CompletedRunSource,
) (sessionmodel.AssistantSessionContextSummary, error) {
	if err := validateSource(source); err != nil {
		sessionCompactionTotal.WithLabelValues("invalid").Inc()
		return sessionmodel.AssistantSessionContextSummary{}, err
	}
	for attempt := 0; attempt < maxCommitAttempts; attempt++ {
		session, found, err := service.store.GetSession(ctx, source.SessionID)
		if err != nil {
			sessionCompactionTotal.WithLabelValues("failed").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, err
		}
		if !found || session.UserID != source.UserID || session.State != "active" {
			sessionCompactionTotal.WithLabelValues("rejected").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, errors.New(
				"assistant session compaction owner or lifecycle is invalid",
			)
		}
		// The terminal relay is at-least-once. On the common commit-before-outbox-
		// acknowledgement retry, return the already-owned summary without making a
		// second provider call. If a later summary already exists, the transactional
		// receipt remains the final replay authority below.
		if session.ContextSummary != nil &&
			strings.TrimSpace(session.ContextSummary.ToTurnID) == source.RunID {
			sessionCompactionTotal.WithLabelValues("replayed").Inc()
			return *session.ContextSummary, nil
		}
		next := nextSummaryDraft(session, source)
		narrative, err := service.generator.GenerateRollingNarrative(
			ctx,
			NarrativeInput{
				PreviousSummary: previousSummaryText(session.ContextSummary),
				CurrentGoal:     next.CurrentGoal,
				UserInput:       source.UserInput,
				AnswerText:      source.AnswerText,
				ConfirmedFacts:  append([]string(nil), next.ConfirmedFacts...),
				PendingItems:    append([]string(nil), next.PendingItems...),
				ConfirmedSlots:  cloneStringMap(next.ConfirmedSlots),
			},
		)
		if err != nil {
			sessionCompactionTotal.WithLabelValues("failed").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, err
		}
		narrative = strings.TrimSpace(narrative)
		if narrative == "" || len([]rune(narrative)) > maxNarrativeRunes {
			sessionCompactionTotal.WithLabelValues("rejected").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, errors.New(
				"assistant session compaction narrative is invalid",
			)
		}
		next.Text = renderProtectedSummary(next, narrative)
		if len([]rune(next.Text)) > maxSummaryRunes {
			sessionCompactionTotal.WithLabelValues("rejected").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, errors.New(
				"assistant session compaction exceeded its context budget",
			)
		}
		next.SummaryID, err = summaryDigest(source, next)
		if err != nil {
			sessionCompactionTotal.WithLabelValues("failed").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, err
		}
		result, err := service.store.CommitSessionSummary(
			ctx,
			sessionports.SessionSummaryCommit{
				CompletionEventID:      source.CompletionEventID,
				SessionID:              source.SessionID,
				ExpectedVersion:        session.SummaryVersion,
				ExpectedSourceSequence: session.SummarySourceSequence,
				NextSourceSequence:     session.SummarySourceSequence + 1,
				Summary:                next,
				UpdatedAt:              source.CompletedAt,
			},
		)
		if err != nil {
			sessionCompactionTotal.WithLabelValues("failed").Inc()
			return sessionmodel.AssistantSessionContextSummary{}, err
		}
		if result.Conflict {
			continue
		}
		if result.Applied {
			sessionCompactionTotal.WithLabelValues("applied").Inc()
			return next, nil
		}
		if result.Replayed {
			persisted, ok, readErr := service.store.GetSession(ctx, source.SessionID)
			if readErr != nil || !ok || persisted.ContextSummary == nil {
				sessionCompactionTotal.WithLabelValues("failed").Inc()
				if readErr != nil {
					return sessionmodel.AssistantSessionContextSummary{}, readErr
				}
				return sessionmodel.AssistantSessionContextSummary{}, errors.New(
					"assistant session summary receipt has no persisted summary",
				)
			}
			sessionCompactionTotal.WithLabelValues("replayed").Inc()
			return *persisted.ContextSummary, nil
		}
	}
	sessionCompactionTotal.WithLabelValues("conflict").Inc()
	return sessionmodel.AssistantSessionContextSummary{}, errors.New(
		"assistant session summary remained concurrently modified",
	)
}

func validateSource(source CompletedRunSource) error {
	if strings.TrimSpace(source.CompletionEventID) == "" ||
		strings.TrimSpace(source.RunID) == "" ||
		strings.TrimSpace(source.SessionID) == "" ||
		strings.TrimSpace(source.UserID) == "" ||
		strings.TrimSpace(source.CurrentGoal) == "" ||
		strings.TrimSpace(source.UserInput) == "" ||
		strings.TrimSpace(source.AnswerText) == "" || source.CompletedAt.IsZero() {
		return errors.New("completed AssistantRun source is invalid for compaction")
	}
	return nil
}

func nextSummaryDraft(
	session sessionmodel.AssistantSession,
	source CompletedRunSource,
) sessionmodel.AssistantSessionContextSummary {
	previous := session.ContextSummary
	fromTurnID := source.RunID
	turnCount := 1
	confirmedFacts := []string{}
	pendingItems := []string{}
	confirmedSlots := map[string]string{}
	if previous != nil {
		if strings.TrimSpace(previous.FromTurnID) != "" {
			fromTurnID = previous.FromTurnID
		}
		turnCount = previous.TurnCount + 1
		confirmedFacts = append(confirmedFacts, previous.ConfirmedFacts...)
		pendingItems = append(pendingItems, previous.PendingItems...)
		for key, value := range previous.ConfirmedSlots {
			confirmedSlots[key] = value
		}
	}
	confirmedFacts = uniqueBoundedStrings(
		append(confirmedFacts, source.ConfirmedFacts...),
		32,
	)
	pendingItems = uniqueBoundedStrings(
		append(pendingItems, source.PendingItems...),
		32,
	)
	for key, value := range source.ConfirmedSlots {
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if key != "" && value != "" {
			confirmedSlots[key] = value
		}
	}
	return sessionmodel.AssistantSessionContextSummary{
		FromTurnID:     fromTurnID,
		ToTurnID:       source.RunID,
		TurnCount:      turnCount,
		CurrentGoal:    strings.TrimSpace(source.CurrentGoal),
		ConfirmedFacts: confirmedFacts,
		PendingItems:   pendingItems,
		ConfirmedSlots: confirmedSlots,
	}
}

func renderProtectedSummary(
	summary sessionmodel.AssistantSessionContextSummary,
	narrative string,
) string {
	lines := []string{"当前目标：" + strings.TrimSpace(summary.CurrentGoal)}
	if len(summary.ConfirmedSlots) > 0 {
		keys := make([]string, 0, len(summary.ConfirmedSlots))
		for key := range summary.ConfirmedSlots {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		pairs := make([]string, 0, len(keys))
		for _, key := range keys {
			pairs = append(pairs, key+"="+summary.ConfirmedSlots[key])
		}
		lines = append(lines, "已确认槽位："+strings.Join(pairs, "；"))
	}
	if len(summary.ConfirmedFacts) > 0 {
		lines = append(lines, "已确认事实："+strings.Join(summary.ConfirmedFacts, "；"))
	}
	if len(summary.PendingItems) > 0 {
		lines = append(lines, "待处理："+strings.Join(summary.PendingItems, "；"))
	}
	lines = append(lines, "连续摘要："+narrative)
	return strings.Join(lines, "\n")
}

func summaryDigest(
	source CompletedRunSource,
	summary sessionmodel.AssistantSessionContextSummary,
) (string, error) {
	encoded, err := json.Marshal(struct {
		CompletionEventID string                                      `json:"completionEventId"`
		SessionID         string                                      `json:"sessionId"`
		Summary           sessionmodel.AssistantSessionContextSummary `json:"summary"`
	}{
		CompletionEventID: source.CompletionEventID,
		SessionID:         source.SessionID,
		Summary:           summary,
	})
	if err != nil {
		return "", fmt.Errorf("encode assistant session summary identity: %w", err)
	}
	digest := sha256.Sum256(append([]byte("assistant-session-summary\x00"), encoded...))
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func previousSummaryText(value *sessionmodel.AssistantSessionContextSummary) string {
	if value == nil {
		return ""
	}
	return value.Text
}

func uniqueBoundedStrings(values []string, limit int) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
		if len(result) == limit {
			break
		}
	}
	return result
}

func cloneStringMap(value map[string]string) map[string]string {
	if value == nil {
		return nil
	}
	cloned := make(map[string]string, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}
