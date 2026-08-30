package http

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"

	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/ports"
	"time"

	authorityapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/application"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
)

const (
	BasePath                = "/control-plane/platform/human-authority/"
	GitHubWebhookPath       = BasePath + "webhooks/github"
	maxBodyBytes      int64 = 64 * 1024
)

type Handler struct {
	mutationMu    sync.Mutex
	facade        *authorityapp.Facade
	roles         *authorityapp.RoleMapper
	webhookSecret []byte
}

func NewHandler(facade *authorityapp.Facade, roles *authorityapp.RoleMapper, webhookSecret []byte) (*Handler, error) {
	if facade == nil || roles == nil || len(webhookSecret) < 16 {
		return nil, errors.New("human authority HTTP handler requires facade, role mapper and webhook secret")
	}
	return &Handler{facade: facade, roles: roles, webhookSecret: append([]byte(nil), webhookSecret...)}, nil
}
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == GitHubWebhookPath {
		h.github(w, r)
		return
	}
	actor, err := h.actor(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	path := strings.TrimPrefix(r.URL.Path, BasePath)
	switch {
	case r.Method == http.MethodGet && path == "decision-units":
		if err := requireScope(actor, "ops.human-authority.read"); err != nil {
			writeError(w, r, err)
			return
		}
		units, err := h.facade.List(r.Context(), actor)
		writeResult(w, r, http.StatusOK, map[string]any{"items": units}, err)
	case r.Method == http.MethodPost && path == "decision-units":
		h.create(w, r, actor)
	case strings.HasPrefix(path, "decision-units/"):
		h.decisionUnit(w, r, actor, path)
	case strings.HasPrefix(path, "receipts/"):
		h.receipt(w, r, actor, path)
	case strings.HasPrefix(path, "signing-keys/") && r.Method == http.MethodGet:
		if err := requireScope(actor, "ops.human-authority.read"); err != nil {
			writeError(w, r, err)
			return
		}
		key, err := h.facade.PublicKey(strings.TrimPrefix(path, "signing-keys/"))
		writeResult(w, r, http.StatusOK, key, err)
	default:
		http.NotFound(w, r)
	}
}
func (h *Handler) actor(r *http.Request) (authorityapp.Actor, error) {
	p, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(p.Issuer) == "" || strings.TrimSpace(p.Actor.AccountID) == "" {
		return authorityapp.Actor{}, httpError(model.ErrWrongRole, "verified operator OIDC principal required")
	}
	scopes := append([]string(nil), p.Permissions...)
	scopes = append(scopes, strings.Fields(p.Scope)...)
	return authorityapp.Actor{ID: strings.TrimSpace(p.Actor.AccountID), Roles: h.roles.RolesFor(p.Roles), Scopes: scopes, MFAProvenance: "runtime/auth OIDC verifier RequireMFA=true"}, nil
}
func requireScope(actor authorityapp.Actor, scope string) error {
	if !authorityapp.ScopeAllowed(actor.Scopes, scope) {
		return httpError(model.ErrWrongRole, "operator permission denied")
	}
	return nil
}
func (h *Handler) create(w http.ResponseWriter, r *http.Request, a authorityapp.Actor) {
	if err := requireScope(a, "ops.human-authority.write"); err != nil {
		writeError(w, r, err)
		return
	}
	raw, err := readBody(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input model.DecisionUnit
	if err = decodeBytes(raw, &input); err != nil {
		writeError(w, r, err)
		return
	}
	h.idempotent(w, r, "create", raw, http.StatusCreated, func() (any, error) { return h.facade.Create(r.Context(), a, input) })
}
func (h *Handler) decisionUnit(w http.ResponseWriter, r *http.Request, a authorityapp.Actor, path string) {
	rest := strings.TrimPrefix(path, "decision-units/")
	if strings.HasSuffix(rest, ":finalize") && r.Method == http.MethodPost {
		if err := requireScope(a, "ops.human-authority.authorize"); err != nil {
			writeError(w, r, err)
			return
		}
		raw, err := readBody(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input authorityapp.FinalizeInput
		if err = decodeBytes(raw, &input); err != nil {
			writeError(w, r, err)
			return
		}
		id := strings.TrimSuffix(rest, ":finalize")
		h.idempotent(w, r, "finalize:"+id, raw, http.StatusOK, func() (any, error) { return h.facade.Finalize(r.Context(), a, id, input) })
		return
	}
	parts := strings.Split(rest, "/")
	if len(parts) == 1 && r.Method == http.MethodGet {
		if err := requireScope(a, "ops.human-authority.read"); err != nil {
			writeError(w, r, err)
			return
		}
		unit, err := h.facade.Read(r.Context(), a, parts[0])
		writeResult(w, r, http.StatusOK, unit, err)
		return
	}
	if len(parts) == 2 && parts[1] == "submissions" && r.Method == http.MethodPost {
		if err := requireScope(a, "ops.human-authority.write"); err != nil {
			writeError(w, r, err)
			return
		}
		raw, err := readBody(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input authorityapp.SubmitRequest
		if err = decodeBytes(raw, &input); err != nil {
			writeError(w, r, err)
			return
		}
		h.idempotent(w, r, "submit:"+parts[0], raw, http.StatusOK, func() (any, error) { return h.facade.Submit(r.Context(), a, parts[0], input) })
		return
	}
	if len(parts) == 3 && parts[1] == "rounds" && strings.HasSuffix(parts[2], ":seal") && r.Method == http.MethodPost {
		if err := requireScope(a, "ops.human-authority.write"); err != nil {
			writeError(w, r, err)
			return
		}
		round, err := strconv.Atoi(strings.TrimSuffix(parts[2], ":seal"))
		if err != nil {
			writeError(w, r, model.ErrInvalid)
			return
		}
		raw, err := readBody(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		if len(bytes.TrimSpace(raw)) == 0 {
			raw = []byte("{}")
		}
		var empty struct{}
		if err = decodeBytes(raw, &empty); err != nil {
			writeError(w, r, err)
			return
		}
		h.idempotent(w, r, "seal:"+parts[0]+":"+strconv.Itoa(round), raw, http.StatusOK, func() (any, error) { return h.facade.Seal(r.Context(), a, parts[0], round) })
		return
	}
	http.NotFound(w, r)
}
func (h *Handler) idempotent(w http.ResponseWriter, r *http.Request, operation string, raw []byte, status int, execute func() (any, error)) {
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	key := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if key == "" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	digest := model.Digest(raw)
	stored, found, err := h.facade.Idempotency(r.Context(), operation, key)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if found {
		if stored.RequestDigest != digest {
			writeError(w, r, model.ErrConflict)
			return
		}
		writeExactJSON(w, stored.StatusCode, stored.ResponseBytes)
		return
	}
	value, err := execute()
	if err != nil {
		writeError(w, r, err)
		return
	}
	response, err := json.Marshal(value)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err = h.facade.SaveIdempotency(r.Context(), ports.IdempotencyRecord{Operation: operation, Key: key, RequestDigest: digest, StatusCode: status, ResponseBytes: response}); err != nil {
		writeError(w, r, err)
		return
	}
	writeExactJSON(w, status, response)
}
func writeExactJSON(w http.ResponseWriter, status int, raw []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(append(append([]byte(nil), raw...), byte(10)))
}

func (h *Handler) receipt(w http.ResponseWriter, r *http.Request, a authorityapp.Actor, path string) {
	rest := strings.TrimPrefix(path, "receipts/")
	if r.Method == http.MethodGet && !strings.Contains(rest, ":") {
		if err := requireScope(a, "ops.human-authority.read"); err != nil {
			writeError(w, r, err)
			return
		}
		receipt, err := h.facade.Receipt(r.Context(), rest)
		writeAuthorityReceipt(w, r, receipt, err)
		return
	}
	if strings.HasSuffix(rest, ":consume") && r.Method == http.MethodPost {
		if err := requireScope(a, "ops.human-authority.consume"); err != nil {
			writeError(w, r, err)
			return
		}
		raw, err := readBody(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input authorityapp.TransitionInput
		if err = decodeBytes(raw, &input); err != nil {
			writeError(w, r, err)
			return
		}
		id := strings.TrimSuffix(rest, ":consume")
		h.idempotentAuthority(w, r, "consume:"+id, raw, func() (model.AuthorizationReceipt, error) {
			return h.facade.Consume(r.Context(), a, id, strings.TrimSpace(r.Header.Get("If-Match")), strings.TrimSpace(r.Header.Get("Idempotency-Key")), input)
		})
		return
	}
	if strings.HasSuffix(rest, ":revoke") && r.Method == http.MethodPost {
		if err := requireScope(a, "ops.human-authority.revoke"); err != nil {
			writeError(w, r, err)
			return
		}
		raw, err := readBody(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var input struct {
			Reason string `json:"reason"`
		}
		if err = decodeBytes(raw, &input); err != nil {
			writeError(w, r, err)
			return
		}
		id := strings.TrimSuffix(rest, ":revoke")
		h.idempotentAuthority(w, r, "revoke:"+id, raw, func() (model.AuthorizationReceipt, error) {
			return h.facade.Revoke(r.Context(), a, id, strings.TrimSpace(r.Header.Get("If-Match")), strings.TrimSpace(r.Header.Get("Idempotency-Key")), input.Reason)
		})
		return
	}
	http.NotFound(w, r)
}

func writeAuthorityReceipt(w http.ResponseWriter, r *http.Request, receipt model.AuthorizationReceipt, err error) {
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("ETag", receipt.ETag)
	w.Header().Set("X-QWQ-Authority-Signature-Algorithm", receipt.SignatureAlgorithm)
	w.Header().Set("X-QWQ-Authority-Key-Id", receipt.KeyID)
	w.Header().Set("X-QWQ-Authority-Signature", receipt.Signature)
	w.Header().Set("X-QWQ-Authority-Issuer", receipt.Issuer)
	w.Header().Set("X-QWQ-Authority-Provider-Version", receipt.ProviderVersion)
	w.Header().Set("X-QWQ-Authority-Provider-Commit", receipt.ProviderCommit)
	w.Header().Set("X-QWQ-Authority-Contract-Version", receipt.ContractVersion)
	w.Header().Set("X-QWQ-Authority-Chain-Commit", receipt.ChainCommit)
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(receipt)
}
func (h *Handler) idempotentAuthority(w http.ResponseWriter, r *http.Request, operation string, raw []byte, execute func() (model.AuthorizationReceipt, error)) {
	if strings.TrimSpace(r.Header.Get("If-Match")) == "" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	key := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if key == "" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	requestDigest := model.Digest(raw)
	h.mutationMu.Lock()
	defer h.mutationMu.Unlock()
	stored, found, err := h.facade.Idempotency(r.Context(), operation, key)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if found {
		if stored.RequestDigest != requestDigest {
			writeError(w, r, model.ErrConflict)
			return
		}
		var receipt model.AuthorizationReceipt
		if json.Unmarshal(stored.ResponseBytes, &receipt) != nil {
			writeError(w, r, model.ErrReceiptMismatch)
			return
		}
		writeAuthorityReceipt(w, r, receipt, nil)
		return
	}
	receipt, err := execute()
	if err != nil {
		writeError(w, r, err)
		return
	}
	response, err := json.Marshal(receipt)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err = h.facade.SaveIdempotency(r.Context(), ports.IdempotencyRecord{Operation: operation, Key: key, RequestDigest: requestDigest, StatusCode: http.StatusOK, ResponseBytes: response}); err != nil {
		writeError(w, r, err)
		return
	}
	writeAuthorityReceipt(w, r, receipt, nil)
}

type githubPayload struct {
	Action       string `json:"action"`
	Installation struct {
		ID int64 `json:"id"`
	} `json:"installation"`
	Repository struct {
		FullName string `json:"full_name"`
	} `json:"repository"`
	WorkflowRun struct {
		ID         int64  `json:"id"`
		HeadSHA    string `json:"head_sha"`
		RunAttempt int64  `json:"run_attempt"`
	} `json:"workflow_run"`
	Environment     string `json:"environment"`
	CandidateDigest string `json:"candidate_digest"`
}

func (h *Handler) github(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}
	raw, err := readBody(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if !verifyGitHub(h.webhookSecret, raw, r.Header.Get("X-Hub-Signature-256")) {
		writeError(w, r, httpError(model.ErrWrongRole, "github signature invalid"))
		return
	}
	delivery, event := strings.TrimSpace(r.Header.Get("X-GitHub-Delivery")), strings.TrimSpace(r.Header.Get("X-GitHub-Event"))
	if delivery == "" || event != "deployment_protection_rule" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	var payload githubPayload
	if json.Unmarshal(raw, &payload) != nil {
		writeError(w, r, model.ErrInvalid)
		return
	}
	if payload.Action != "requested" && payload.Action != "approved" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	if payload.Installation.ID <= 0 || strings.TrimSpace(payload.Repository.FullName) == "" || payload.WorkflowRun.ID <= 0 || payload.WorkflowRun.RunAttempt <= 0 || strings.TrimSpace(payload.WorkflowRun.HeadSHA) == "" || strings.TrimSpace(payload.Environment) == "" || strings.TrimSpace(payload.CandidateDigest) == "" {
		writeError(w, r, model.ErrInvalid)
		return
	}
	approval := model.GitHubApproval{DeliveryID: delivery, PayloadDigest: model.Digest(raw), InstallationID: payload.Installation.ID, Repository: payload.Repository.FullName, RunID: payload.WorkflowRun.ID, RunAttempt: payload.WorkflowRun.RunAttempt, HeadSHA: payload.WorkflowRun.HeadSHA, CandidateDigest: payload.CandidateDigest, Environment: payload.Environment, Event: event, Action: payload.Action, Requested: payload.Action == "requested", Approved: payload.Action == "approved", NativeProtection: false, OccurredAt: time.Now().UTC()}
	stored, replayed, err := h.facade.RecordGitHub(r.Context(), approval)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"approval": stored, "replayed": replayed})
}
func verifyGitHub(secret, raw []byte, header string) bool {
	const prefix = "sha256="
	if !strings.HasPrefix(header, prefix) {
		return false
	}
	provided, err := hex.DecodeString(strings.TrimPrefix(header, prefix))
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(raw)
	return hmac.Equal(provided, mac.Sum(nil))
}
func readBody(r *http.Request) ([]byte, error) {
	reader := io.LimitReader(r.Body, maxBodyBytes+1)
	raw, err := io.ReadAll(reader)
	if err != nil || int64(len(raw)) > maxBodyBytes {
		return nil, model.ErrInvalid
	}
	return raw, nil
}
func decode(r *http.Request, target any) error {
	raw, err := readBody(r)
	if err != nil {
		return err
	}
	return decodeBytes(raw, target)
}
func decodeBytes(raw []byte, target any) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(target); err != nil {
		return model.ErrInvalid
	}
	if dec.Decode(&struct{}{}) != io.EOF {
		return model.ErrInvalid
	}
	return nil
}

type wrappedHTTPError struct {
	cause error
	debug string
}

func (e wrappedHTTPError) Error() string        { return e.cause.Error() }
func (e wrappedHTTPError) Unwrap() error        { return e.cause }
func httpError(cause error, debug string) error { return wrappedHTTPError{cause: cause, debug: debug} }
func writeResult(w http.ResponseWriter, r *http.Request, status int, value any, err error) {
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, status, value)
}
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeError(w http.ResponseWriter, r *http.Request, err error) {
	status := http.StatusInternalServerError
	kind := rterr.KindSystem
	reason := "human_authority_storage_failed"
	message := "人工授权记录保存失败"
	recovery := "retry"
	switch {
	case errors.Is(err, model.ErrWrongRole):
		status = http.StatusUnauthorized
		kind = rterr.KindUser
		reason = "human_authority_unauthorized"
		message = "人工授权身份未授权"
		recovery = "escalate"
	case errors.Is(err, model.ErrInvalid):
		status = http.StatusBadRequest
		kind = rterr.KindUser
		reason = "human_authority_invalid"
		message = "人工授权请求无效"
		recovery = "surface"
	case errors.Is(err, model.ErrNotFound):
		status = http.StatusNotFound
		kind = rterr.KindUser
		reason = "human_authority_not_found"
		message = "人工授权记录不存在"
		recovery = "surface"
	case errors.Is(err, model.ErrConflict), errors.Is(err, model.ErrRoundsUnsealed), errors.Is(err, model.ErrReceiptMismatch), errors.Is(err, model.ErrReceiptExpired):
		status = http.StatusConflict
		kind = rterr.KindUser
		reason = "human_authority_conflict"
		message = "人工授权状态冲突"
		recovery = "surface"
	case errors.Is(err, model.ErrHardVeto):
		status = http.StatusUnprocessableEntity
		kind = rterr.KindUser
		reason = "human_authority_hard_veto"
		message = "硬否决条件未通过"
		recovery = "surface"
	case errors.Is(err, model.ErrSoD):
		status = http.StatusUnprocessableEntity
		kind = rterr.KindUser
		reason = "human_authority_sod_failed"
		message = "职责分离要求未满足"
		recovery = "escalate"
	case errors.Is(err, model.ErrEvidenceExpired):
		status = http.StatusUnprocessableEntity
		kind = rterr.KindUser
		reason = "human_authority_evidence_expired"
		message = "人工证据已过期"
		recovery = "surface"
	}
	debug := reason
	if wrapped := new(wrappedHTTPError); errors.As(err, wrapped) {
		debug = wrapped.debug
	}
	appErr := rterr.NewAppError(rterr.NewCode(rterr.ModuleOps, kind, reason), message, debug).WithMetadata(reason, status).WithRecoveryDirective(recovery, "inlineCard", 0)
	rterr.WriteHTTPError(w, appErr, rterr.HTTPWriteOptionsFromRequest(r))
}
