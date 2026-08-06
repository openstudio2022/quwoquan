package http

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	learningerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_learning_fact"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

type Handler struct {
	service *learningapplication.AssistantLearningFactAppender
	queries *learningapplication.OpsQueryService
}

type appendRequest struct {
	EventID           string    `json:"eventId"`
	FactType          string    `json:"factType"`
	AssistantTurnID   string    `json:"assistantTurnId"`
	TriggerMessageID  string    `json:"triggerMessageId"`
	ReferralSource    string    `json:"referralSource"`
	DomainID          string    `json:"domainId"`
	EventType         string    `json:"eventType"`
	FeedbackType      string    `json:"feedbackType"`
	FeedbackScore     float64   `json:"feedbackScore"`
	ReasonCodes       []string  `json:"reasonCodes"`
	ActionType        string    `json:"actionType"`
	SuggestedActionID string    `json:"suggestedActionId"`
	DurationMs        int       `json:"durationMs"`
	MetricID          string    `json:"metricId"`
	MetricValue       float64   `json:"metricValue"`
	MetricSource      string    `json:"metricSource"`
	QueryText         string    `json:"queryText"`
	AnswerText        string    `json:"answerText"`
	FeedbackText      string    `json:"feedbackText"`
	CorrectionText    string    `json:"correctionText"`
	TrainingEligible  *bool     `json:"trainingEligible"`
	OccurredAt        time.Time `json:"occurredAt"`
}

func NewHandler(
	service *learningapplication.AssistantLearningFactAppender,
	queries ...*learningapplication.OpsQueryService,
) *Handler {
	var opsQueries *learningapplication.OpsQueryService
	if len(queries) > 0 {
		opsQueries = queries[0]
	}
	return &Handler{service: service, queries: opsQueries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	if mux == nil {
		return
	}
	mux.HandleFunc(
		"POST /assistant/learning/facts",
		handler.handleAppendUserFact,
	)
	mux.HandleFunc(
		"GET /assistant/ops/learning-summary",
		handler.handleGetLearningOpsSummary,
	)
}

func (handler *Handler) handleGetLearningOpsSummary(
	writer http.ResponseWriter,
	request *http.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	userID := ""
	if ok {
		userID = strings.TrimSpace(principal.Actor.AccountID)
	}
	if userID == "" {
		writeError(
			writer,
			request,
			learningerrors.AppErrorFromLearningFactUnauthorized(
				"verified operator account is required",
			),
		)
		return
	}
	if handler.queries == nil {
		writeError(
			writer,
			request,
			learningerrors.AppErrorFromLearningOpsUnavailable(
				"learning ops query service is unavailable",
			),
		)
		return
	}
	summary, err := handler.queries.GetLearningOpsSummary(
		request.Context(),
		userID,
	)
	if err != nil {
		switch {
		case errors.Is(err, learningapplication.ErrUnauthorized):
			writeError(
				writer,
				request,
				learningerrors.AppErrorFromLearningFactUnauthorized(err.Error()),
			)
		default:
			writeError(
				writer,
				request,
				learningerrors.AppErrorFromLearningOpsUnavailable(err.Error()),
			)
		}
		return
	}
	writeJSON(writer, http.StatusOK, summary)
}

func (handler *Handler) handleAppendUserFact(
	writer http.ResponseWriter,
	request *http.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok ||
		strings.TrimSpace(principal.Actor.AccountID) == "" ||
		strings.TrimSpace(principal.Actor.PersonaID) == "" {
		writeError(
			writer,
			request,
			learningerrors.AppErrorFromLearningFactUnauthorized(
				"verified account and persona are required",
			),
		)
		return
	}
	command, err := decodeCommand(request)
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	clientSentAt, err := parseOptionalTime(
		request.Header.Get("X-Client-Sent-At"),
	)
	if err != nil {
		writeError(
			writer,
			request,
			learningerrors.AppErrorFromLearningFactInvalid(err.Error()),
		)
		return
	}
	trusted := model.TrustedContext{
		UserID:           principal.Actor.AccountID,
		PersonaID:        principal.Actor.PersonaID,
		TraceID:          request.Header.Get("X-Trace-Id"),
		ClientSessionID:  request.Header.Get("X-Client-Session-Id"),
		PageVisitID:      request.Header.Get("X-Client-Page-Visit-Id"),
		PageID:           request.Header.Get("X-Client-Page-Id"),
		SurfaceID:        request.Header.Get("X-Client-Surface-Id"),
		RouteID:          request.Header.Get("X-Client-Route-Id"),
		OperationID:      request.Header.Get("X-Client-Operation-Id"),
		ExperimentBucket: request.Header.Get("X-Client-Experiment-Bucket"),
		ClientSentAt:     clientSentAt,
	}
	receipt, err := handler.service.Append(
		request.Context(),
		learningapplication.AppendInput{
			Kind:           learningapplication.AppendKindUserFeedback,
			Command:        command,
			TrustedContext: &trusted,
		},
	)
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	writeJSON(writer, http.StatusOK, receipt)
}

func decodeCommand(request *http.Request) (model.AppendCommand, error) {
	var body appendRequest
	decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		return model.AppendCommand{}, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return model.AppendCommand{},
				errors.New("request body must contain exactly one JSON value")
		}
		return model.AppendCommand{}, err
	}
	if body.TrainingEligible == nil {
		return model.AppendCommand{},
			errors.New("trainingEligible is required")
	}
	factType, err := assistantgenerated.ParseAssistantLearningFactType(
		body.FactType,
	)
	if err != nil {
		return model.AppendCommand{}, fmt.Errorf("factType must be canonical: %w", err)
	}
	if factType == assistantgenerated.AssistantLearningFactTypeUnknown {
		return model.AppendCommand{},
			errors.New("factType must be canonical and non-empty")
	}
	referralSource, err := assistantgenerated.ParseAssistantReferralSource(
		body.ReferralSource,
	)
	if err != nil {
		return model.AppendCommand{},
			fmt.Errorf("referralSource must be canonical: %w", err)
	}
	if referralSource == assistantgenerated.AssistantReferralSourceUnknown {
		return model.AppendCommand{},
			errors.New("referralSource must be canonical and non-empty")
	}
	eventType, err := parseOptionalInteractionEventType(body.EventType)
	if err != nil {
		return model.AppendCommand{}, err
	}
	feedbackType, err := parseOptionalFeedbackType(body.FeedbackType)
	if err != nil {
		return model.AppendCommand{}, err
	}
	return model.AppendCommand{
		EventID:           body.EventID,
		FactType:          model.FactType(factType.WireName()),
		AssistantTurnID:   body.AssistantTurnID,
		TriggerMessageID:  body.TriggerMessageID,
		ReferralSource:    referralSource.WireName(),
		DomainID:          body.DomainID,
		EventType:         eventType,
		FeedbackType:      feedbackType,
		FeedbackScore:     body.FeedbackScore,
		ReasonCodes:       body.ReasonCodes,
		ActionType:        body.ActionType,
		SuggestedActionID: body.SuggestedActionID,
		DurationMs:        body.DurationMs,
		MetricID:          body.MetricID,
		MetricValue:       body.MetricValue,
		MetricSource:      body.MetricSource,
		QueryText:         body.QueryText,
		AnswerText:        body.AnswerText,
		FeedbackText:      body.FeedbackText,
		CorrectionText:    body.CorrectionText,
		TrainingEligible:  *body.TrainingEligible,
		OccurredAt:        body.OccurredAt,
	}, nil
}

func parseOptionalInteractionEventType(raw string) (string, error) {
	if strings.TrimSpace(raw) == "" {
		return "", nil
	}
	value, err := assistantgenerated.ParseInteractionEventType(raw)
	if err != nil {
		return "", fmt.Errorf("eventType must be canonical: %w", err)
	}
	if value == assistantgenerated.InteractionEventTypeUnknown {
		return "", errors.New("eventType must be canonical and non-empty")
	}
	return value.WireName(), nil
}

func parseOptionalFeedbackType(raw string) (string, error) {
	if strings.TrimSpace(raw) == "" {
		return "", nil
	}
	value, err := assistantgenerated.ParseFeedbackType(raw)
	if err != nil {
		return "", fmt.Errorf("feedbackType must be canonical: %w", err)
	}
	if value == assistantgenerated.FeedbackTypeUnknown {
		return "", errors.New("feedbackType must be canonical and non-empty")
	}
	return value.WireName(), nil
}

func mapError(err error) error {
	switch {
	case errors.Is(err, learningapplication.ErrIdentityConflict):
		return learningerrors.AppErrorFromLearningFactIdentityConflict(
			err.Error(),
		)
	case errors.Is(err, learningapplication.ErrOwnerMismatch):
		return learningerrors.AppErrorFromLearningFactOwnerMismatch(err.Error())
	case errors.Is(err, learningapplication.ErrRunNotFound):
		return learningerrors.AppErrorFromLearningFactRunNotFound(err.Error())
	case errors.Is(err, learningapplication.ErrUnauthorized):
		return learningerrors.AppErrorFromLearningFactUnauthorized(err.Error())
	case errors.Is(err, learningapplication.ErrStoreUnavailable):
		return learningerrors.AppErrorFromLearningFactSinkUnavailable(err.Error())
	default:
		return learningerrors.AppErrorFromLearningFactInvalid(err.Error())
	}
}

func parseOptionalTime(value string) (time.Time, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return time.Time{}, nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return time.Time{}, errors.New("X-Client-Sent-At must be RFC3339")
	}
	return parsed.UTC(), nil
}

func writeError(
	writer http.ResponseWriter,
	request *http.Request,
	err error,
) {
	rterr.WriteHTTPError(
		writer,
		err,
		rterr.HTTPWriteOptionsFromRequest(request),
	)
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
