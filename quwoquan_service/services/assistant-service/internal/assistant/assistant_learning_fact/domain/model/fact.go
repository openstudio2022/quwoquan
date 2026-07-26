package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"
)

type FactType string

const (
	FactTypeUserFeedback       FactType = "user_feedback"
	FactTypeInteractionOutcome FactType = "interaction_outcome"
	FactTypeServiceScorecard   FactType = "service_scorecard"
)

type AppendCommand struct {
	EventID           string
	EventVersion      int
	FactType          FactType
	AssistantTurnID   string
	TriggerMessageID  string
	ReferralSource    string
	DomainID          string
	EventType         string
	FeedbackType      string
	FeedbackScore     float64
	ReasonCodes       []string
	ActionType        string
	SuggestedActionID string
	DurationMs        int
	MetricID          string
	MetricValue       float64
	MetricSource      string
	QueryText         string
	AnswerText        string
	FeedbackText      string
	CorrectionText    string
	TrainingEligible  bool
	OccurredAt        time.Time
}

type TrustedContext struct {
	UserID           string
	PersonaID        string
	TraceID          string
	SessionID        string
	PageVisitID      string
	PageID           string
	SurfaceID        string
	RouteID          string
	OperationID      string
	ExperimentBucket string
	ClientSentAt     time.Time
}

type Fact struct {
	StorageID         string    `bson:"_id" json:"-"`
	EventID           string    `bson:"eventId" json:"eventId"`
	EventVersion      int       `bson:"eventVersion" json:"eventVersion"`
	FactType          FactType  `bson:"factType" json:"factType"`
	PayloadDigest     string    `bson:"payloadDigest" json:"payloadDigest"`
	AppendSequence    int64     `bson:"appendSequence" json:"appendSequence"`
	UserID            string    `bson:"userId" json:"userId"`
	PersonaID         string    `bson:"personaId" json:"personaId"`
	AssistantTurnID   string    `bson:"assistantTurnId" json:"assistantTurnId"`
	TriggerMessageID  string    `bson:"triggerMessageId,omitempty" json:"triggerMessageId,omitempty"`
	ReferralSource    string    `bson:"referralSource" json:"referralSource"`
	TraceID           string    `bson:"traceId,omitempty" json:"traceId,omitempty"`
	SessionID         string    `bson:"sessionId,omitempty" json:"sessionId,omitempty"`
	PageVisitID       string    `bson:"pageVisitId,omitempty" json:"pageVisitId,omitempty"`
	PageID            string    `bson:"pageId,omitempty" json:"pageId,omitempty"`
	SurfaceID         string    `bson:"surfaceId,omitempty" json:"surfaceId,omitempty"`
	RouteID           string    `bson:"routeId,omitempty" json:"routeId,omitempty"`
	OperationID       string    `bson:"operationId,omitempty" json:"operationId,omitempty"`
	ExperimentBucket  string    `bson:"experimentBucket,omitempty" json:"experimentBucket,omitempty"`
	DomainID          string    `bson:"domainId" json:"domainId"`
	EventType         string    `bson:"eventType,omitempty" json:"eventType,omitempty"`
	FeedbackType      string    `bson:"feedbackType,omitempty" json:"feedbackType,omitempty"`
	FeedbackScore     float64   `bson:"feedbackScore,omitempty" json:"feedbackScore,omitempty"`
	ReasonCodes       []string  `bson:"reasonCodes,omitempty" json:"reasonCodes,omitempty"`
	ActionType        string    `bson:"actionType,omitempty" json:"actionType,omitempty"`
	SuggestedActionID string    `bson:"suggestedActionId,omitempty" json:"suggestedActionId,omitempty"`
	DurationMs        int       `bson:"durationMs,omitempty" json:"durationMs,omitempty"`
	MetricID          string    `bson:"metricId,omitempty" json:"metricId,omitempty"`
	MetricValue       float64   `bson:"metricValue,omitempty" json:"metricValue,omitempty"`
	MetricSource      string    `bson:"metricSource,omitempty" json:"metricSource,omitempty"`
	QueryText         string    `bson:"queryText,omitempty" json:"queryText,omitempty"`
	QueryTextDigest   string    `bson:"queryTextDigest,omitempty" json:"queryTextDigest,omitempty"`
	AnswerText        string    `bson:"answerText,omitempty" json:"answerText,omitempty"`
	FeedbackText      string    `bson:"feedbackText,omitempty" json:"feedbackText,omitempty"`
	CorrectionText    string    `bson:"correctionText,omitempty" json:"correctionText,omitempty"`
	TrainingEligible  bool      `bson:"trainingEligible" json:"trainingEligible"`
	OccurredAt        time.Time `bson:"occurredAt" json:"occurredAt"`
	ClientSentAt      time.Time `bson:"clientSentAt,omitempty" json:"clientSentAt,omitempty"`
	RecordedAt        time.Time `bson:"recordedAt" json:"recordedAt"`
}

type Receipt struct {
	EventID        string    `bson:"eventId" json:"eventId"`
	EventVersion   int       `bson:"eventVersion" json:"eventVersion"`
	Accepted       bool      `bson:"accepted" json:"accepted"`
	Deduplicated   bool      `bson:"-" json:"deduplicated"`
	AppendSequence int64     `bson:"appendSequence" json:"appendSequence"`
	PayloadDigest  string    `bson:"payloadDigest" json:"payloadDigest"`
	RecordedAt     time.Time `bson:"recordedAt" json:"recordedAt"`
}

type RedactedPayload struct {
	EventID           string    `bson:"eventId" json:"eventId"`
	EventVersion      int       `bson:"eventVersion" json:"eventVersion"`
	AppendSequence    int64     `bson:"appendSequence" json:"appendSequence"`
	FactType          FactType  `bson:"factType" json:"factType"`
	UserID            string    `bson:"userId" json:"userId"`
	PersonaID         string    `bson:"personaId" json:"personaId"`
	AssistantTurnID   string    `bson:"assistantTurnId" json:"assistantTurnId"`
	TriggerMessageID  string    `bson:"triggerMessageId,omitempty" json:"triggerMessageId,omitempty"`
	ReferralSource    string    `bson:"referralSource" json:"referralSource"`
	TraceID           string    `bson:"traceId,omitempty" json:"traceId,omitempty"`
	SessionID         string    `bson:"sessionId,omitempty" json:"sessionId,omitempty"`
	PageVisitID       string    `bson:"pageVisitId,omitempty" json:"pageVisitId,omitempty"`
	PageID            string    `bson:"pageId,omitempty" json:"pageId,omitempty"`
	SurfaceID         string    `bson:"surfaceId,omitempty" json:"surfaceId,omitempty"`
	RouteID           string    `bson:"routeId,omitempty" json:"routeId,omitempty"`
	OperationID       string    `bson:"operationId,omitempty" json:"operationId,omitempty"`
	ExperimentBucket  string    `bson:"experimentBucket,omitempty" json:"experimentBucket,omitempty"`
	DomainID          string    `bson:"domainId" json:"domainId"`
	EventType         string    `bson:"eventType,omitempty" json:"eventType,omitempty"`
	FeedbackType      string    `bson:"feedbackType,omitempty" json:"feedbackType,omitempty"`
	FeedbackScore     float64   `bson:"feedbackScore,omitempty" json:"feedbackScore,omitempty"`
	ReasonCodes       []string  `bson:"reasonCodes,omitempty" json:"reasonCodes,omitempty"`
	ActionType        string    `bson:"actionType,omitempty" json:"actionType,omitempty"`
	SuggestedActionID string    `bson:"suggestedActionId,omitempty" json:"suggestedActionId,omitempty"`
	DurationMs        int       `bson:"durationMs,omitempty" json:"durationMs,omitempty"`
	MetricID          string    `bson:"metricId,omitempty" json:"metricId,omitempty"`
	MetricValue       float64   `bson:"metricValue,omitempty" json:"metricValue,omitempty"`
	MetricSource      string    `bson:"metricSource,omitempty" json:"metricSource,omitempty"`
	QueryTextDigest   string    `bson:"queryTextDigest,omitempty" json:"queryTextDigest,omitempty"`
	TrainingEligible  bool      `bson:"trainingEligible" json:"trainingEligible"`
	OccurredAt        time.Time `bson:"occurredAt" json:"occurredAt"`
	RecordedAt        time.Time `bson:"recordedAt" json:"recordedAt"`
}

func Build(
	command AppendCommand,
	trusted TrustedContext,
	now time.Time,
) (Fact, error) {
	command.EventID = strings.TrimSpace(command.EventID)
	command.AssistantTurnID = strings.TrimSpace(command.AssistantTurnID)
	command.TriggerMessageID = strings.TrimSpace(command.TriggerMessageID)
	command.ReferralSource = strings.TrimSpace(command.ReferralSource)
	command.DomainID = strings.TrimSpace(command.DomainID)
	trusted.UserID = strings.TrimSpace(trusted.UserID)
	trusted.PersonaID = strings.TrimSpace(trusted.PersonaID)
	if command.EventID == "" || command.EventVersion <= 0 {
		return Fact{}, errors.New("eventId and positive eventVersion are required")
	}
	if command.AssistantTurnID == "" ||
		command.ReferralSource == "" ||
		command.DomainID == "" {
		return Fact{}, errors.New(
			"assistantTurnId, referralSource and domainId are required",
		)
	}
	if trusted.UserID == "" || trusted.PersonaID == "" {
		return Fact{}, errors.New("trusted account and persona are required")
	}
	if command.FactType != FactTypeUserFeedback &&
		command.FactType != FactTypeInteractionOutcome &&
		command.FactType != FactTypeServiceScorecard {
		return Fact{}, fmt.Errorf("unsupported factType %q", command.FactType)
	}
	if command.DurationMs < 0 {
		return Fact{}, errors.New("durationMs must not be negative")
	}
	if !finite(command.FeedbackScore) || !finite(command.MetricValue) {
		return Fact{}, errors.New("numeric values must be finite")
	}

	fact := Fact{
		StorageID:         Identity(command.EventID, command.EventVersion),
		EventID:           command.EventID,
		EventVersion:      command.EventVersion,
		FactType:          command.FactType,
		UserID:            trusted.UserID,
		PersonaID:         trusted.PersonaID,
		AssistantTurnID:   command.AssistantTurnID,
		TriggerMessageID:  command.TriggerMessageID,
		ReferralSource:    command.ReferralSource,
		TraceID:           strings.TrimSpace(trusted.TraceID),
		SessionID:         strings.TrimSpace(trusted.SessionID),
		PageVisitID:       strings.TrimSpace(trusted.PageVisitID),
		PageID:            strings.TrimSpace(trusted.PageID),
		SurfaceID:         strings.TrimSpace(trusted.SurfaceID),
		RouteID:           strings.TrimSpace(trusted.RouteID),
		OperationID:       strings.TrimSpace(trusted.OperationID),
		ExperimentBucket:  strings.TrimSpace(trusted.ExperimentBucket),
		DomainID:          command.DomainID,
		EventType:         strings.TrimSpace(command.EventType),
		FeedbackType:      strings.TrimSpace(command.FeedbackType),
		FeedbackScore:     command.FeedbackScore,
		ReasonCodes:       normalizedList(command.ReasonCodes),
		ActionType:        strings.TrimSpace(command.ActionType),
		SuggestedActionID: strings.TrimSpace(command.SuggestedActionID),
		DurationMs:        command.DurationMs,
		MetricID:          strings.TrimSpace(command.MetricID),
		MetricValue:       command.MetricValue,
		MetricSource:      strings.TrimSpace(command.MetricSource),
		QueryText:         strings.TrimSpace(command.QueryText),
		AnswerText:        strings.TrimSpace(command.AnswerText),
		FeedbackText:      strings.TrimSpace(command.FeedbackText),
		CorrectionText:    strings.TrimSpace(command.CorrectionText),
		TrainingEligible:  command.TrainingEligible,
		OccurredAt:        command.OccurredAt.UTC(),
		ClientSentAt:      trusted.ClientSentAt.UTC(),
		RecordedAt:        now.UTC(),
	}
	if fact.OccurredAt.IsZero() {
		fact.OccurredAt = fact.RecordedAt
	}
	fact.QueryTextDigest = textDigest(fact.QueryText)
	if hasRestrictedText(fact) && fact.TrainingEligible {
		return Fact{}, errors.New(
			"facts containing restricted raw text cannot be training eligible",
		)
	}
	if fact.FactType != FactTypeServiceScorecard &&
		(fact.MetricID != "" ||
			fact.MetricSource != "" ||
			fact.MetricValue != 0) {
		return Fact{}, errors.New(
			"metric fields are reserved for service_scorecard",
		)
	}
	switch fact.FactType {
	case FactTypeUserFeedback:
		if fact.FeedbackType == "" && fact.ActionType == "" {
			return Fact{}, errors.New(
				"user_feedback requires feedbackType or actionType",
			)
		}
		if fact.EventType != "" {
			return Fact{}, errors.New(
				"user_feedback must not include interaction eventType",
			)
		}
	case FactTypeInteractionOutcome:
		if fact.EventType == "" && fact.ActionType == "" {
			return Fact{}, errors.New(
				"interaction_outcome requires eventType or actionType",
			)
		}
		if fact.FeedbackType != "" || fact.FeedbackScore != 0 ||
			fact.FeedbackText != "" || fact.CorrectionText != "" {
			return Fact{}, errors.New(
				"interaction_outcome must not include feedback fields",
			)
		}
	case FactTypeServiceScorecard:
		if fact.MetricID == "" || fact.MetricSource == "" {
			return Fact{}, errors.New(
				"service_scorecard requires metricId and metricSource",
			)
		}
		if fact.MetricValue < 0 || fact.MetricValue > 5 {
			return Fact{}, errors.New("metricValue must be in range [0,5]")
		}
		if fact.EventType != "" || fact.FeedbackType != "" ||
			fact.FeedbackScore != 0 || len(fact.ReasonCodes) != 0 ||
			fact.ActionType != "" || fact.SuggestedActionID != "" ||
			fact.DurationMs != 0 || hasRestrictedText(fact) {
			return Fact{}, errors.New(
				"service_scorecard must contain only metric fields",
			)
		}
	}
	fact.PayloadDigest = Digest(fact)
	return fact, nil
}

func Identity(eventID string, eventVersion int) string {
	return fmt.Sprintf("%s:%d", strings.TrimSpace(eventID), eventVersion)
}

func Digest(fact Fact) string {
	material := fact
	material.StorageID = ""
	material.PayloadDigest = ""
	material.AppendSequence = 0
	material.RecordedAt = time.Time{}
	material.TraceID = ""
	material.SessionID = ""
	material.PageVisitID = ""
	material.PageID = ""
	material.SurfaceID = ""
	material.RouteID = ""
	material.OperationID = ""
	material.ExperimentBucket = ""
	material.ClientSentAt = time.Time{}
	raw, _ := json.Marshal(material)
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func (fact Fact) RedactedPayload() RedactedPayload {
	return RedactedPayload{
		EventID:           fact.EventID,
		EventVersion:      fact.EventVersion,
		AppendSequence:    fact.AppendSequence,
		FactType:          fact.FactType,
		UserID:            fact.UserID,
		PersonaID:         fact.PersonaID,
		AssistantTurnID:   fact.AssistantTurnID,
		TriggerMessageID:  fact.TriggerMessageID,
		ReferralSource:    fact.ReferralSource,
		TraceID:           fact.TraceID,
		SessionID:         fact.SessionID,
		PageVisitID:       fact.PageVisitID,
		PageID:            fact.PageID,
		SurfaceID:         fact.SurfaceID,
		RouteID:           fact.RouteID,
		OperationID:       fact.OperationID,
		ExperimentBucket:  fact.ExperimentBucket,
		DomainID:          fact.DomainID,
		EventType:         fact.EventType,
		FeedbackType:      fact.FeedbackType,
		FeedbackScore:     fact.FeedbackScore,
		ReasonCodes:       append([]string(nil), fact.ReasonCodes...),
		ActionType:        fact.ActionType,
		SuggestedActionID: fact.SuggestedActionID,
		DurationMs:        fact.DurationMs,
		MetricID:          fact.MetricID,
		MetricValue:       fact.MetricValue,
		MetricSource:      fact.MetricSource,
		QueryTextDigest:   fact.QueryTextDigest,
		TrainingEligible:  fact.TrainingEligible,
		OccurredAt:        fact.OccurredAt,
		RecordedAt:        fact.RecordedAt,
	}
}

func textDigest(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func normalizedList(values []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func hasRestrictedText(fact Fact) bool {
	return fact.QueryText != "" ||
		fact.AnswerText != "" ||
		fact.FeedbackText != "" ||
		fact.CorrectionText != ""
}

func finite(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0)
}
