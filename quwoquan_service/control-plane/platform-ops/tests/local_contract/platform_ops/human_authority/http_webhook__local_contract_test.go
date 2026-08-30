// spec_ref:
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-002.t1
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-002.t2
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-002.t3
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-003.t1
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-003.t2
// - specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-003.t3
package local_contract

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	authorityhttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/adapters/inbound/http"
	authorityapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/application"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	authoritystore "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/infrastructure/persistence"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func newHTTPHandler(t *testing.T) *authorityhttp.Handler {
	t.Helper()
	_, priv, _ := ed25519.GenerateKey(nil)
	signer, _ := authorityapp.NewEd25519Signer("test", priv, true)
	facade, _ := authorityapp.NewFacade(authoritystore.NewMemoryStore(), signer, []authorityapp.GitHubMapping{{Repository: "quwoquan/quwoquan", Environment: "production", DecisionKind: "production_campaign_approval", Scope: "production-campaign"}})
	roles, _ := authorityapp.NewRoleMapper(map[string][]string{"oidc-release": {"release_owner"}, "oidc-engineering": {"engineering_delivery_owner"}})
	handler, err := authorityhttp.NewHandler(facade, roles, []byte("github-webhook-secret-value"))
	if err != nil {
		t.Fatal(err)
	}
	return handler
}
func TestOIDCRoutesRequireVerifiedPrincipalAndPermission(t *testing.T) {
	handler := newHTTPHandler(t)
	body := `{"decisionUnitId":"http-1","requiredRoles":["engineering_delivery_owner"],"stage":"production_campaign","decisionKind":"production_campaign_approval","scope":{"objective":"objective-http"},"target":"prod","fingerprint":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","actions":["promote"],"options":[{"optionId":"approve","neutralLabel":"批准","userOutcome":"候选可发布","businessOutcome":"进入灰度","cost":"已冻结","timeToEffect":"窗口内","risk":"受控","reversibility":"可撤销","scopeChange":"无","unknowns":[],"nextStep":"consume"}],"evidenceExpiresAt":"2026-08-30T03:00:00Z"}`
	request := httptest.NewRequest(http.MethodPost, authorityhttp.BasePath+"decision-units", strings.NewReader(body))
	request.Header.Set("Idempotency-Key", "create-http-1")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous status=%d", response.Code)
	}
	principal := rtauth.Principal{Claims: rtauth.Claims{Issuer: "https://issuer", Subject: "operator-1", Roles: []string{"oidc-release"}, Permissions: []string{"ops.human-authority.write"}}, Actor: operation.ActorContext{AccountID: "operator-1"}}
	request = httptest.NewRequest(http.MethodPost, authorityhttp.BasePath+"decision-units", strings.NewReader(body))
	request.Header.Set("Idempotency-Key", "create-http-1-authenticated")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("authenticated status=%d body=%s", response.Code, response.Body.String())
	}
	request = httptest.NewRequest(http.MethodGet, authorityhttp.BasePath+"decision-units/http-1", nil)
	request = request.WithContext(rtauth.WithPrincipal(context.Background(), principal))
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("missing read permission status=%d", response.Code)
	}
}
func TestGitHubWebhookHMACIdempotencyConflictAndClosedSet(t *testing.T) {
	handler := newHTTPHandler(t)
	payload := []byte(`{"action":"requested","installation":{"id":7},"repository":{"full_name":"quwoquan/quwoquan"},"workflow_run":{"id":9,"head_sha":"abc","run_attempt":1},"environment":"production","candidate_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	send := func(delivery, event string, raw []byte, valid bool) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodPost, authorityhttp.GitHubWebhookPath, bytes.NewReader(raw))
		request.Header.Set("X-GitHub-Delivery", delivery)
		request.Header.Set("X-GitHub-Event", event)
		mac := hmac.New(sha256.New, []byte("github-webhook-secret-value"))
		mac.Write(raw)
		signature := hex.EncodeToString(mac.Sum(nil))
		if !valid {
			signature = strings.Repeat("0", 64)
		}
		request.Header.Set("X-Hub-Signature-256", "sha256="+signature)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	if response := send("d1", "deployment_protection_rule", payload, false); response.Code != http.StatusUnauthorized {
		t.Fatalf("bad hmac=%d", response.Code)
	}
	if response := send("d1", "push", payload, true); response.Code != http.StatusBadRequest {
		t.Fatalf("bad event=%d", response.Code)
	}
	approvedFirst := bytes.Replace(payload, []byte(`"requested"`), []byte(`"approved"`), 1)
	if response := send("d0", "deployment_protection_rule", approvedFirst, true); response.Code != http.StatusConflict {
		t.Fatalf("approved before request=%d body=%s", response.Code, response.Body.String())
	}
	if response := send("d1", "deployment_protection_rule", payload, true); response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"replayed":false`) {
		t.Fatalf("first=%d %s", response.Code, response.Body.String())
	}
	if response := send("d1", "deployment_protection_rule", payload, true); response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"replayed":true`) {
		t.Fatalf("replay=%d %s", response.Code, response.Body.String())
	}
	changed := bytes.Replace(payload, []byte(`"requested"`), []byte(`"approved"`), 1)
	if response := send("d1", "deployment_protection_rule", changed, true); response.Code != http.StatusConflict {
		t.Fatalf("conflict=%d body=%s", response.Code, response.Body.String())
	}
}

func TestCollectionWireWrongRoleAndExactIdempotency(t *testing.T) {
	handler := newHTTPHandler(t)
	unit := `{"decisionUnitId":"http-list","requiredRoles":["engineering_delivery_owner"],"stage":"production_campaign","decisionKind":"production_campaign_approval","scope":{"objective":"objective-http"},"target":"prod","fingerprint":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","actions":["promote"],"options":[{"optionId":"approve","neutralLabel":"批准","userOutcome":"候选可发布","businessOutcome":"进入灰度","cost":"已冻结","timeToEffect":"窗口内","risk":"受控","reversibility":"可撤销","scopeChange":"无","unknowns":[],"nextStep":"consume"}],"evidenceExpiresAt":"2026-08-30T03:00:00Z"}`
	principal := rtauth.Principal{Claims: rtauth.Claims{Issuer: "https://issuer", Subject: "operator-1", Roles: []string{"oidc-release"}, Permissions: []string{"ops.human-authority.write", "ops.human-authority.read"}}, Actor: operation.ActorContext{AccountID: "operator-1"}}
	sendCreate := func(body, key string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodPost, authorityhttp.BasePath+"decision-units", strings.NewReader(body))
		request.Header.Set("Idempotency-Key", key)
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	first := sendCreate(unit, "same-key")
	if first.Code != http.StatusCreated {
		t.Fatalf("first=%d %s", first.Code, first.Body.String())
	}
	replay := sendCreate(unit, "same-key")
	if replay.Code != http.StatusCreated || replay.Body.String() != first.Body.String() {
		t.Fatalf("replay=%d same=%v", replay.Code, replay.Body.String() == first.Body.String())
	}
	mismatch := sendCreate(strings.Replace(unit, "objective-http", "objective-other", 1), "same-key")
	if mismatch.Code != http.StatusConflict {
		t.Fatalf("mismatch=%d %s", mismatch.Code, mismatch.Body.String())
	}
	list := httptest.NewRequest(http.MethodGet, authorityhttp.BasePath+"decision-units", nil)
	wrongRole := principal
	wrongRole.Roles = []string{"oidc-unknown"}
	list = list.WithContext(rtauth.WithPrincipal(list.Context(), wrongRole))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, list)
	if response.Code != http.StatusOK || strings.Contains(response.Body.String(), "http-list") {
		t.Fatalf("wrong role collection=%d %s", response.Code, response.Body.String())
	}
	engineer := principal
	engineer.Roles = []string{"oidc-engineering"}
	list = httptest.NewRequest(http.MethodGet, authorityhttp.BasePath+"decision-units", nil)
	list = list.WithContext(rtauth.WithPrincipal(list.Context(), engineer))
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, list)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "http-list") {
		t.Fatalf("role collection=%d %s", response.Code, response.Body.String())
	}
	forbiddenWire := `{"round":1,"facts":["f"],"impacts":[],"unknowns":[],"role":"release_owner","actorId":"forged","mfaProvenance":"forged"}`
	submit := httptest.NewRequest(http.MethodPost, authorityhttp.BasePath+"decision-units/http-list/submissions", strings.NewReader(forbiddenWire))
	submit.Header.Set("Idempotency-Key", "submit-forged")
	submit = submit.WithContext(rtauth.WithPrincipal(submit.Context(), engineer))
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, submit)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("forged wire=%d %s", response.Code, response.Body.String())
	}
}

func TestReceiptHTTPEmitsVerifiableWrapperAndStrongCASHeaders(t *testing.T) {
	_, private, _ := ed25519.GenerateKey(nil)
	signer, _ := authorityapp.NewEd25519Signer("http-key", private, true)
	facade, _ := authorityapp.NewFacade(authoritystore.NewMemoryStore(), signer, nil)
	unit := model.DecisionUnit{ID: "http-receipt", Stage: "production_campaign", DecisionKind: "production_campaign_approval", RiskClassification: "production_critical", Scope: model.CanonicalScope{"objective": "objective-http"}, Target: "prod", Fingerprint: "sha256:" + strings.Repeat("a", 64), Actions: []string{"promote"}, Options: []model.DecisionOption{{OptionID: "approve", NeutralLabel: "approve", UserOutcome: "ok", BusinessOutcome: "ok", Cost: "low", TimeToEffect: "now", Risk: "controlled", Reversibility: "yes", ScopeChange: "none", Unknowns: []string{}, NextStep: "consume"}}, EvidenceExpiresAt: time.Date(2099, 1, 1, 0, 0, 0, 0, time.UTC)}
	created, err := facade.Create(context.Background(), authorityapp.Actor{ID: "creator"}, unit)
	if err != nil {
		t.Fatal(err)
	}
	roles := created.RequiredRoles
	for _, round := range []int{1, 2} {
		for _, role := range roles {
			created, err = facade.Submit(context.Background(), authorityapp.Actor{ID: "actor-" + role, Roles: []string{role}}, created.ID, authorityapp.SubmitRequest{Round: round, Facts: []string{"fact"}, Impacts: []string{}, Unknowns: []string{}, SelectedOptionID: map[bool]string{true: "approve", false: ""}[round == 2]})
			if err != nil {
				t.Fatal(err)
			}
		}
		created, err = facade.Seal(context.Background(), authorityapp.Actor{ID: "sealer"}, created.ID, round)
		if err != nil {
			t.Fatal(err)
		}
	}
	created, err = facade.Finalize(context.Background(), authorityapp.Actor{ID: "actor-release_owner", Roles: []string{"release_owner"}}, created.ID, authorityapp.FinalizeInput{SelectedOptionID: "approve"})
	if err != nil {
		t.Fatal(err)
	}
	mapper, _ := authorityapp.NewRoleMapper(nil)
	handler, _ := authorityhttp.NewHandler(facade, mapper, []byte("github-webhook-secret-value"))
	principal := rtauth.Principal{Claims: rtauth.Claims{Issuer: "https://issuer", Subject: "executor", Permissions: []string{"ops.human-authority.read", "ops.human-authority.consume"}}, Actor: operation.ActorContext{AccountID: "executor"}}
	send := func(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(method, path, strings.NewReader(body))
		for key, value := range headers {
			request.Header.Set(key, value)
		}
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	get := send(http.MethodGet, authorityhttp.BasePath+"receipts/"+created.Decision.ID, "", nil)
	if get.Code != http.StatusOK || get.Header().Get("ETag") != created.Receipt.ETag || !strings.Contains(get.Body.String(), `"attestationCanonicalBytes"`) {
		t.Fatalf("get=%d headers=%v body=%s", get.Code, get.Header(), get.Body.String())
	}
	body := `{"action":"promote","commandDigest":"sha256:` + strings.Repeat("b", 64) + `","fingerprint":"` + created.Fingerprint + `","scope":{"objective":"objective-http"}}`
	missing := send(http.MethodPost, authorityhttp.BasePath+"receipts/"+created.Decision.ID+":consume", body, map[string]string{"Idempotency-Key": "consume-http"})
	if missing.Code != http.StatusBadRequest {
		t.Fatalf("missing if-match=%d", missing.Code)
	}
	consumed := send(http.MethodPost, authorityhttp.BasePath+"receipts/"+created.Decision.ID+":consume", body, map[string]string{"Idempotency-Key": "consume-http", "If-Match": created.Receipt.ETag})
	if consumed.Code != http.StatusOK || consumed.Header().Get("ETag") == created.Receipt.ETag || !strings.Contains(consumed.Body.String(), `"winnerIdempotencyKey":"consume-http"`) {
		t.Fatalf("consumed=%d headers=%v body=%s", consumed.Code, consumed.Header(), consumed.Body.String())
	}
}

func TestGitHubMappingMissingAndIdentityMismatchFailClosed(t *testing.T) {
	handler := newHTTPHandler(t)
	send := func(delivery string, raw []byte) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodPost, authorityhttp.GitHubWebhookPath, bytes.NewReader(raw))
		request.Header.Set("X-GitHub-Delivery", delivery)
		request.Header.Set("X-GitHub-Event", "deployment_protection_rule")
		mac := hmac.New(sha256.New, []byte("github-webhook-secret-value"))
		mac.Write(raw)
		request.Header.Set("X-Hub-Signature-256", "sha256="+hex.EncodeToString(mac.Sum(nil)))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		return response
	}
	unmapped := []byte(`{"action":"requested","installation":{"id":7},"repository":{"full_name":"other/repo"},"workflow_run":{"id":9,"run_attempt":1,"head_sha":"abc"},"environment":"production","candidate_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	if r := send("u1", unmapped); r.Code != http.StatusBadRequest {
		t.Fatalf("unmapped=%d %s", r.Code, r.Body.String())
	}
	requested := []byte(`{"action":"requested","installation":{"id":7},"repository":{"full_name":"quwoquan/quwoquan"},"workflow_run":{"id":9,"run_attempt":1,"head_sha":"abc"},"environment":"production","candidate_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	if r := send("r1", requested); r.Code != http.StatusOK {
		t.Fatalf("requested=%d %s", r.Code, r.Body.String())
	}
	approvedMismatch := bytes.Replace(requested, []byte(`"requested"`), []byte(`"approved"`), 1)
	approvedMismatch = bytes.Replace(approvedMismatch, []byte(`"run_attempt":1`), []byte(`"run_attempt":2`), 1)
	if r := send("a1", approvedMismatch); r.Code != http.StatusConflict {
		t.Fatalf("tuple mismatch=%d %s", r.Code, r.Body.String())
	}
	approved := bytes.Replace(requested, []byte(`"requested"`), []byte(`"approved"`), 1)
	if r := send("a2", approved); r.Code != http.StatusOK {
		t.Fatalf("approved=%d %s", r.Code, r.Body.String())
	}
}

func TestBootstrapRegistersOnlyExactWebhookOutsideGuard(t *testing.T) {
	raw, err := os.ReadFile("../../../../cmd/api/bootstrap.go")
	if err != nil {
		t.Fatal(err)
	}
	source := string(raw)
	if !strings.Contains(source, `unguarded.Handle("POST /control-plane/platform/human-authority/webhooks/github"`) {
		t.Fatal("exact webhook must be registered outside operation guard")
	}
	if strings.Contains(source, `unguarded.Handle("/control-plane/platform/human-authority/"`) {
		t.Fatal("Portal route prefix must not be unguarded")
	}
	if !strings.Contains(source, `asm.Mux.Handle("/control-plane/platform/human-authority/"`) {
		t.Fatal("Portal routes must enter generated operation guard")
	}
}
