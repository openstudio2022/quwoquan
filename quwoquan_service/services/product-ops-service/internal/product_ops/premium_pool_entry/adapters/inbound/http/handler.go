package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
)

const (
	collectionPath = "/control-plane/product/recommendation/premium-pool"
	itemPathPrefix = collectionPath + "/"
)

type ErrorWriter func(http.ResponseWriter, *http.Request, int, string, string)

type Handler struct {
	service    *application.Service
	writeError ErrorWriter
}

func NewHandler(service *application.Service, writeError ErrorWriter) *Handler {
	if service == nil || writeError == nil {
		panic("PremiumPoolEntry HTTP handler requires service and error writer")
	}
	return &Handler{service: service, writeError: writeError}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("PremiumPoolEntry HTTP handler requires mux")
	}
	mux.Handle(collectionPath, handler)
	mux.Handle(itemPathPrefix, handler)
}

func (handler *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == collectionPath:
		handler.list(w, r)
	case r.Method == http.MethodPost && r.URL.Path == collectionPath:
		handler.upsert(w, r)
	case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":rollback"):
		handler.rollback(w, r)
	case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, ":takedown"):
		handler.takedown(w, r)
	default:
		handler.writeError(w, r, http.StatusNotFound, "精选池接口不存在", "PremiumPoolEntry route or method is not registered")
	}
}

type upsertRequest struct {
	ContentID        string  `json:"contentId"`
	Scope            string  `json:"scope"`
	QualityScore     float64 `json:"qualityScore"`
	QualityAdmission string  `json:"qualityAdmission"`
	SupplySource     string  `json:"supplySource"`
	SourceTaskID     string  `json:"sourceTaskId"`
	AuditID          string  `json:"auditId"`
	RollbackToken    string  `json:"rollbackToken"`
	ExpiresAt        string  `json:"expiresAt"`
}

func (handler *Handler) list(w http.ResponseWriter, r *http.Request) {
	activeOnly, _ := strconv.ParseBool(strings.TrimSpace(r.URL.Query().Get("activeOnly")))
	items, err := handler.service.List(r.Context(), activeOnly)
	if err != nil {
		handler.writeApplicationError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (handler *Handler) upsert(w http.ResponseWriter, r *http.Request) {
	commandContext, err := commandContextFromRequest(r)
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	var request upsertRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		handler.writeApplicationError(w, r, model.ErrInvalidArgument, true)
		return
	}
	expiresAt, err := time.Parse(time.RFC3339, strings.TrimSpace(request.ExpiresAt))
	if err != nil {
		handler.writeApplicationError(w, r, model.ErrInvalidArgument, true)
		return
	}
	entry, err := handler.service.Upsert(r.Context(), application.UpsertCommand{
		ContentID: request.ContentID, Scope: request.Scope,
		QualityScore: request.QualityScore, QualityAdmission: request.QualityAdmission,
		SupplySource: request.SupplySource, SourceTaskID: request.SourceTaskID,
		AuditID: request.AuditID, RollbackToken: request.RollbackToken,
		ExpiresAt: expiresAt, Context: commandContext,
	})
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, entry)
}

func (handler *Handler) rollback(w http.ResponseWriter, r *http.Request) {
	if err := requireEmptyObject(r); err != nil {
		handler.writeApplicationError(w, r, model.ErrInvalidArgument, true)
		return
	}
	commandContext, err := commandContextFromRequest(r)
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	entry, err := handler.service.Rollback(
		r.Context(), itemContentID(r.URL.Path, ":rollback"), commandContext,
	)
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, entry)
}

func (handler *Handler) takedown(w http.ResponseWriter, r *http.Request) {
	if err := requireEmptyObject(r); err != nil {
		handler.writeApplicationError(w, r, model.ErrInvalidArgument, true)
		return
	}
	commandContext, err := commandContextFromRequest(r)
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	result, err := handler.service.Takedown(
		r.Context(), itemContentID(r.URL.Path, ":takedown"), commandContext,
	)
	if err != nil {
		handler.writeApplicationError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) writeApplicationError(
	w http.ResponseWriter,
	r *http.Request,
	err error,
	write bool,
) {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		handler.writeError(w, r, http.StatusBadRequest, "精选池请求无效", err.Error())
	case errors.Is(err, model.ErrNotFound):
		handler.writeError(w, r, http.StatusNotFound, "精选池条目不存在", err.Error())
	case application.IsUserConflict(err):
		handler.writeError(w, r, http.StatusConflict, "精选池状态已变化，请刷新后重试", err.Error())
	default:
		message := "精选池读取失败，请稍后重试"
		if write {
			message = "精选池操作失败，请稍后重试"
		}
		handler.writeError(w, r, http.StatusInternalServerError, message, err.Error())
	}
}

func commandContextFromRequest(r *http.Request) (ports.CommandContext, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ports.CommandContext{}, model.ErrInvalidArgument
	}
	actorID := strings.TrimSpace(principal.Actor.AccountID)
	if actorID == "" {
		return ports.CommandContext{}, model.ErrInvalidArgument
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		return ports.CommandContext{}, model.ErrInvalidArgument
	}
	nowID := strings.ReplaceAll(time.Now().UTC().Format(time.RFC3339Nano), ":", "")
	requestID := strings.TrimSpace(r.Header.Get("X-Request-Id"))
	if requestID == "" {
		requestID = "req-premium-" + nowID
	}
	traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id"))
	if traceID == "" {
		traceID = requestID
	}
	environment := strings.TrimSpace(os.Getenv("APP_ENV"))
	if environment == "" {
		environment = "unknown"
	}
	return ports.CommandContext{
		ActorID: actorID, Environment: environment, RequestID: requestID,
		TraceID: traceID, IdempotencyKey: idempotencyKey,
	}, nil
}

func decodeStrictJSON(r *http.Request, target any) error {
	if r == nil || r.Body == nil {
		return errors.New("request body is required")
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 32768))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain exactly one object")
	}
	return nil
}

func requireEmptyObject(r *http.Request) error {
	var body map[string]any
	if err := decodeStrictJSON(r, &body); err != nil {
		return err
	}
	if len(body) != 0 {
		return errors.New("request body must be an empty object")
	}
	return nil
}

func itemContentID(path, suffix string) string {
	value := strings.TrimPrefix(path, itemPathPrefix)
	return strings.TrimSpace(strings.TrimSuffix(value, suffix))
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
