package http

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
)

type BatchProcessor interface {
	ProcessBatch(context.Context, []behaviorapp.BehaviorEventInput) error
}

type Handler struct {
	processor BatchProcessor
}

func NewHandler(processor BatchProcessor) *Handler {
	if processor == nil {
		panic("ContentBehaviorFact HTTP handler requires batch processor")
	}
	return &Handler{processor: processor}
}

type reportBatch struct {
	UserID        string                           `json:"userId"`
	SessionID     string                           `json:"sessionId"`
	FeedSessionID string                           `json:"feedSessionId"`
	Events        []behaviorapp.BehaviorEventInput `json:"events"`
}

func (handler *Handler) Report(writer http.ResponseWriter, request *http.Request) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromUnauthorized(
			"ReportBehaviors requires a verified persona or device principal",
		))
		return
	}
	actorID, ok := principal.Actor.BusinessActorID()
	if !ok {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromUnauthorized(
			"ReportBehaviors principal has no business actor",
		))
		return
	}
	raw, err := readRequestBody(request)
	if err != nil {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体读取失败",
			err.Error(),
		))
		return
	}
	var batch reportBatch
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&batch); err != nil {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体解析失败",
			err.Error(),
		))
		return
	}
	if err := requireEOF(decoder); err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	if len(batch.Events) == 0 {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"events 不能为空",
			"empty events",
		))
		return
	}
	batch.UserID = actorID
	if operationContext, found := operation.FromContext(request.Context()); found && strings.TrimSpace(operationContext.SessionID) != "" {
		batch.SessionID = strings.TrimSpace(operationContext.SessionID)
	}
	for index := range batch.Events {
		event := &batch.Events[index]
		event.UserID = actorID
		event.PersonaID = strings.TrimSpace(principal.Actor.PersonaID)
		event.DeviceActorID = strings.TrimSpace(principal.Actor.DeviceActorID)
		if strings.TrimSpace(event.SessionID) == "" {
			event.SessionID = strings.TrimSpace(batch.SessionID)
		}
		if strings.TrimSpace(event.FeedSessionID) == "" {
			event.FeedSessionID = strings.TrimSpace(batch.FeedSessionID)
		}
		switch strings.ToLower(strings.TrimSpace(event.Action)) {
		case "like", "comment", "report":
			writeHTTPError(writer, request, rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"该行为由服务端权威采集，需走专属命令路由",
				"like/comment/report are server-authoritative; use the dedicated command route",
			))
			return
		}
	}
	if err := handler.processor.ProcessBatch(request.Context(), batch.Events); err != nil {
		writeHTTPError(writer, request, mapCommandError(err))
		return
	}
	writer.WriteHeader(http.StatusNoContent)
}

func mapCommandError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return err
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return contentgenerated.AppErrorFromUpstreamTimeout(
			"report behaviors dependency timed out: " + err.Error(),
		)
	}
	return contentgenerated.AppErrorFromStorageWriteFailed(
		"persist report behaviors batch: " + err.Error(),
	)
}

const maxRequestBytes = 128 * 1024

func readRequestBody(request *http.Request) ([]byte, error) {
	var reader io.Reader = request.Body
	var compressed *gzip.Reader
	if strings.EqualFold(strings.TrimSpace(request.Header.Get("Content-Encoding")), "gzip") {
		var err error
		compressed, err = gzip.NewReader(request.Body)
		if err != nil {
			return nil, fmt.Errorf("invalid gzip body: %w", err)
		}
		defer compressed.Close()
		reader = compressed
	}
	raw, err := io.ReadAll(io.LimitReader(reader, maxRequestBytes+1))
	if err != nil {
		return nil, fmt.Errorf("read behavior body: %w", err)
	}
	if len(raw) > maxRequestBytes {
		return nil, fmt.Errorf("behavior body exceeds %d bytes", maxRequestBytes)
	}
	return raw, nil
}

func requireEOF(decoder *json.Decoder) error {
	var extra any
	err := decoder.Decode(&extra)
	if errors.Is(err, io.EOF) {
		return nil
	}
	if err == nil {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "请求体只能包含一个对象", "multiple JSON values")
	}
	return rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error())
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
