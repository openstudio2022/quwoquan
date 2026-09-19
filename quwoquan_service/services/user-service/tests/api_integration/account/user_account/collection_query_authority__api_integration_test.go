package api_integration

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-002
import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/generated/operationsecurity"
	auth "quwoquan_service/runtime/auth"
	inbound "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	authority "quwoquan_service/services/user-service/internal/account/user_account/application"
	persistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	persona "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	"strings"
	"testing"
	"time"
)

func TestCollectionQueryAuthorityHTTPCurrentIdentity(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	phone := "+8618013813996"
	code := requestOtpCode(t, phone)
	login := doRequest(t, http.MethodPost, "/auth/login/phone", `{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"collection-query-device","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`, nil)
	if login.Code != http.StatusOK {
		t.Fatalf("source login failed: %d", login.Code)
	}
	body := parseJSON(t, login)
	source, _ := body["accessToken"].(string)
	if source == "" {
		t.Fatal("source credential missing")
	}
	claims, err := testAccessVerifier.Verify(source)
	if err != nil || claims.Persona == "" {
		t.Fatal("source persona credential missing")
	}
	store, err := persistence.NewEnforcementStore(pgPool)
	if err != nil {
		t.Fatal(err)
	}
	key := make([]byte, 32)
	if _, err = rand.Read(key); err != nil {
		t.Fatal(err)
	}
	a, err := authority.NewCollectionQueryAuthority(testAccessVerifier, store, persona.NewOwnerReader(pgPool), authority.CollectionAuthorityKeys{ActiveID: "ephemeral", VerificationKeys: map[string][]byte{"ephemeral": key}}, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	inbound.NewCollectionQueryAuthorityHandler(a).RegisterRoutes(mux)
	handler := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: testAccessVerifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("user"))(mux))
	server := httptest.NewServer(handler)
	defer server.Close()
	request := func(path, caller, scope string, payload any) (int, json.RawMessage) {
		t.Helper()
		raw, e := json.Marshal(payload)
		if e != nil {
			t.Fatal(e)
		}
		r, e := http.NewRequest(http.MethodPost, server.URL+path, bytes.NewReader(raw))
		if e != nil {
			t.Fatal(e)
		}
		r.Header.Set("Content-Type", "application/json")
		for k, v := range serviceHeadersFor(caller, scope) {
			r.Header.Set(k, v)
		}
		response, e := server.Client().Do(r)
		if e != nil {
			t.Fatal(e)
		}
		defer response.Body.Close()
		var result json.RawMessage
		if json.NewDecoder(response.Body).Decode(&result) != nil {
			t.Fatal("invalid authority JSON")
		}
		return response.StatusCode, result
	}
	binding := authority.CollectionQueryBinding{OperationID: "content.post_collection.GetPostCollectionManagement", CollectionID: "collection", PersistedHash: strings.Repeat("a", 64), BodyDigest: "sha256:" + strings.Repeat("b", 64), Method: "POST", Path: "/internal/graphql", Surface: "postCollection", RequestID: "http-request"}
	issue := struct {
		Source  string                           `json:"sourceAccessToken"`
		Binding authority.CollectionQueryBinding `json:"binding"`
	}{source, binding}
	status, raw := request("/internal/user/collection-query-grants", "service:api-edge", "user.collection_query.issue", issue)
	if status != 200 {
		t.Fatalf("issue status=%d", status)
	}
	var granted authority.CollectionQueryGrantResult
	if json.Unmarshal(raw, &granted) != nil || granted.Grant == "" {
		t.Fatal("grant missing")
	}
	verify := struct {
		Grant   string                           `json:"grant"`
		Binding authority.CollectionQueryBinding `json:"binding"`
	}{granted.Grant, binding}
	for i := 0; i < 2; i++ {
		status, raw = request("/internal/user/collection-query-grants/verify", "service:content-service", "user.collection_query.verify", verify)
		var identity authority.VerifiedCollectionQueryIdentity
		if status != 200 || json.Unmarshal(raw, &identity) != nil || identity.PersonaID != claims.Persona || identity.AccountID != claims.Subject {
			t.Fatalf("verify status=%d", status)
		}
	}
	verify.Binding.CollectionID = "other"
	if status, _ = request("/internal/user/collection-query-grants/verify", "service:content-service", "user.collection_query.verify", verify); status != 403 {
		t.Fatalf("binding drift admitted: %d", status)
	}
	verify.Binding = binding
	closed := doRequest(t, http.MethodPost, "/owner/account/close", `{"clientRequestId":"collection-authority-close"}`, map[string]string{"Authorization": "Bearer " + source})
	if closed.Code != 200 {
		t.Fatalf("close failed: %d", closed.Code)
	}
	if status, _ = request("/internal/user/collection-query-grants/verify", "service:content-service", "user.collection_query.verify", verify); status != 403 {
		t.Fatalf("closed grant admitted: %d", status)
	}
}
