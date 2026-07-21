package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	credentialapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	credentialmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	credentialpersistence "quwoquan_service/services/user-service/internal/infrastructure/account/credential_binding/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/infrastructure/user/persistence"
)

func TestDevicePushEndpointHTTPPacketUsesRealPostgresAndStrictPrincipals(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	const (
		accountID = "device-push-owner"
		personaID = "device-push-persona"
		deviceID  = "ios-device"
	)
	createTestProfile(t, accountID, "device push owner")
	createTestPersonaFull(
		t,
		personaID,
		accountID,
		personaID,
		"Device Push Persona",
		"open",
		true,
		true,
	)
	accountProbe, found, err := userpersistence.NewPgPersonaStore(pgPool).
		ResolveOwnerAccountID(context.Background(), personaID)
	if err != nil || !found || accountProbe != accountID {
		t.Fatalf(
			"persona owner reader fixture invalid: account=%q found=%v err=%v",
			accountProbe,
			found,
			err,
		)
	}

	publicPath := "/user/devices/" + deviceID + "/push-endpoints/apns_voip"
	rec := doRequest(
		t,
		http.MethodPut,
		publicPath,
		`{"token":"plaintext-apns-token","appVersion":"1.0.0"}`,
		nil,
	)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("public upsert 未认证必须 401: status=%d body=%s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodPut,
		publicPath,
		`{"token":"plaintext-apns-token","appVersion":"1.0.0"}`,
		serviceHeaders("user.push_endpoint.invalidate"),
	)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf(
			"service principal 不得冒充 account 调用 public upsert: status=%d body=%s",
			rec.Code,
			rec.Body,
		)
	}
	rec = doRequest(
		t,
		http.MethodPut,
		publicPath,
		`{"token":"plaintext-apns-token","appVersion":"1.0.0"}`,
		authHeaders(accountID),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("public upsert: status=%d body=%s", rec.Code, rec.Body)
	}
	first := parseJSON(t, rec)
	endpointRef, _ := first["endpointRef"].(string)
	if endpointRef == "" || strings.Contains(rec.Body.String(), "plaintext-apns-token") {
		t.Fatalf("upsert response 必须返回 ref 且不泄露 token: %s", rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodPut,
		publicPath,
		`{"token":"plaintext-apns-token","appVersion":"1.0.0"}`,
		authHeaders(accountID),
	)
	replay := parseJSON(t, rec)
	if rec.Code != http.StatusOK || replay["idempotentReplay"] != true ||
		replay["version"] != first["version"] {
		t.Fatalf("自然幂等 replay 错误: status=%d body=%s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodPut,
		publicPath,
		`{"token":"rotated-apns-token","appVersion":"1.1.0"}`,
		authHeaders(accountID),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("token rotate: status=%d body=%s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodPut,
		"/user/devices/"+deviceID+"/push-endpoints/fcm",
		`{"token":"plaintext-fcm-token","appVersion":"1.1.0"}`,
		authHeaders(accountID),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("dual fcm upsert: status=%d body=%s", rec.Code, rec.Body)
	}
	fcm := parseJSON(t, rec)
	fcmRef, _ := fcm["endpointRef"].(string)

	var (
		ciphertext    string
		fingerprint   string
		endpointCount int
	)
	if err := pgPool.QueryRow(context.Background(), `
SELECT token_ciphertext, token_fingerprint
FROM device_push_endpoints
WHERE endpoint_ref=$1`,
		endpointRef,
	).Scan(&ciphertext, &fingerprint); err != nil {
		t.Fatalf("读取真实 PG endpoint: %v", err)
	}
	if ciphertext == "" || fingerprint == "" ||
		strings.Contains(ciphertext, "rotated-apns-token") {
		t.Fatalf("真实 PG 只能保存密文/fingerprint: ciphertext=%q", ciphertext)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT COUNT(*) FROM device_push_endpoints
WHERE account_id=$1 AND device_id=$2 AND status='active'`,
		accountID,
		deviceID,
	).Scan(&endpointCount); err != nil || endpointCount != 2 {
		t.Fatalf("双 endpoint PG 行错误: count=%d err=%v", endpointCount, err)
	}
	createTestProfile(t, "device-push-other", "other device push owner")
	rec = doRequest(
		t,
		http.MethodPut,
		"/user/devices/other-device/push-endpoints/apns_voip",
		`{"token":"rotated-apns-token","appVersion":"1.0.0"}`,
		authHeaders("device-push-other"),
	)
	if rec.Code != http.StatusConflict ||
		parseJSON(t, rec)["code"] != "USER.DEVICE_PUSH.token_conflict" {
		t.Fatalf("active fingerprint 唯一约束未生效: %d %s", rec.Code, rec.Body)
	}
	var rolledBackParentCount int
	if err := pgPool.QueryRow(context.Background(), `
SELECT COUNT(*) FROM user_devices
WHERE account_id='device-push-other' AND device_id='other-device'`,
	).Scan(&rolledBackParentCount); err != nil || rolledBackParentCount != 0 {
		t.Fatalf("token 冲突事务未完整回滚: count=%d err=%v", rolledBackParentCount, err)
	}

	destinationPath := "/internal/user/personas/" + personaID + "/push-destinations"
	rec = doRequest(t, http.MethodGet, destinationPath, "", authHeaders(accountID))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("account principal 不得读取内部 destinations: %d %s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodGet,
		destinationPath,
		"",
		serviceHeaders("user.push_destination.read"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("service destination reader: %d %s", rec.Code, rec.Body)
	}
	if strings.Contains(rec.Body.String(), "token") ||
		strings.Contains(rec.Body.String(), "cipher") ||
		strings.Contains(rec.Body.String(), "fingerprint") {
		t.Fatalf("destination refs 泄露 token material: %s", rec.Body)
	}
	var destinationBody struct {
		Destinations []struct {
			EndpointRef  string `json:"endpointRef"`
			DeviceID     string `json:"deviceId"`
			EndpointKind string `json:"endpointKind"`
		} `json:"destinations"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &destinationBody); err != nil ||
		len(destinationBody.Destinations) != 2 {
		t.Fatalf("typed destination slice 错误: body=%s err=%v", rec.Body, err)
	}

	secretPath := "/internal/user/push-endpoints/" + endpointRef + "/secret"
	rec = doRequest(
		t,
		http.MethodGet,
		secretPath,
		"",
		serviceHeaders("user.push_destination.read"),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("错误 scope 不得读 secret: %d %s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodGet,
		secretPath,
		"",
		serviceHeadersFor(
			"service:notification-service",
			"user.push_endpoint.secret.read",
		),
	)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("非 integration-service 即使持有 scope 也不得读 secret: %d %s", rec.Code, rec.Body)
	}
	rec = doRequest(
		t,
		http.MethodGet,
		secretPath,
		"",
		serviceHeaders("user.push_endpoint.secret.read"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("secret reader: %d %s", rec.Code, rec.Body)
	}
	secret := parseJSON(t, rec)
	if secret["endpointKind"] != "apns_voip" ||
		secret["token"] != "rotated-apns-token" ||
		!strings.Contains(rec.Header().Get("Cache-Control"), "no-store") {
		t.Fatalf("secret DTO/no-store 错误: headers=%v body=%s", rec.Header(), rec.Body)
	}

	invalidatePath := "/internal/user/push-endpoints/" + fcmRef + "/invalidate"
	rec = doRequest(
		t,
		http.MethodPost,
		invalidatePath,
		`{"reason":"provider_unregistered"}`,
		serviceHeaders("user.push_endpoint.invalidate"),
	)
	if rec.Code != http.StatusOK || parseJSON(t, rec)["status"] != "stale" {
		t.Fatalf("provider invalidation: %d %s", rec.Code, rec.Body)
	}
	var staleCiphertext, staleFingerprint *string
	if err := pgPool.QueryRow(context.Background(), `
SELECT token_ciphertext, token_fingerprint
FROM device_push_endpoints WHERE endpoint_ref=$1`,
		fcmRef,
	).Scan(&staleCiphertext, &staleFingerprint); err != nil {
		t.Fatal(err)
	}
	if staleCiphertext != nil || staleFingerprint != nil {
		t.Fatal("stale endpoint 必须清除 token material")
	}
	rec = doRequest(
		t,
		http.MethodGet,
		"/internal/user/push-endpoints/"+fcmRef+"/secret",
		"",
		serviceHeaders("user.push_endpoint.secret.read"),
	)
	if rec.Code != http.StatusConflict ||
		parseJSON(t, rec)["code"] != "USER.DEVICE_PUSH.endpoint_not_active" {
		t.Fatalf("stale secret 必须拒绝: %d %s", rec.Code, rec.Body)
	}

	rec = doRequest(
		t,
		http.MethodDelete,
		publicPath,
		"",
		authHeaders("device-push-other"),
	)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("其他 account 不得撤销 owner endpoint: %d %s", rec.Code, rec.Body)
	}
	var originalStatus string
	if err := pgPool.QueryRow(context.Background(), `
SELECT status FROM device_push_endpoints WHERE endpoint_ref=$1`,
		endpointRef,
	).Scan(&originalStatus); err != nil || originalStatus != "active" {
		t.Fatalf("越权 DELETE 改写了 owner endpoint: status=%q err=%v", originalStatus, err)
	}

	rec = doRequest(
		t,
		http.MethodDelete,
		publicPath,
		"",
		authHeaders(accountID),
	)
	if rec.Code != http.StatusOK || parseJSON(t, rec)["status"] != "revoked" {
		t.Fatalf("public remove: %d %s", rec.Code, rec.Body)
	}
}

func serviceHeaders(scopes ...string) map[string]string {
	return serviceHeadersFor("service:integration-service", scopes...)
}

func serviceHeadersFor(accountID string, scopes ...string) map[string]string {
	token, err := testAccessSigner.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		Roles:     []string{"service"},
		Scopes:    scopes,
	})
	if err != nil {
		panic("sign integration-service principal: " + err.Error())
	}
	return map[string]string{"Authorization": "Bearer " + token}
}

func TestCredentialBindingCommitsSecurityOutboxAndLocksLastCredential(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const ownerID = "credential-packet-owner"
	createTestProfile(t, ownerID, "credential owner")

	// 两种凭证均经 store packet 绑定，产生安全审计事实。
	credentialStore, err := credentialpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("credential store: %v", err)
	}
	credentialCommands := credentialapp.NewCredentialCommandFacade(
		credentialStore,
	)
	if _, err := credentialCommands.BindVerifiedCredential(
		context.Background(),
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypePhone,
			CredentialKey:  "+8613800000001",
			DisplayLabel:   "phone",
		},
	); err != nil {
		t.Fatalf("bind phone: %v", err)
	}
	if _, err := credentialCommands.BindVerifiedCredential(
		context.Background(),
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypeFederatedSlotA,
			CredentialKey:  "federated-subject",
			DisplayLabel:   "federated",
		},
	); err != nil {
		t.Fatalf("bind wechat: %v", err)
	}
	var boundEvents int
	if err := pgPool.QueryRow(context.Background(), `
SELECT COUNT(*) FROM credential_bindings_outbox
WHERE event_type='CredentialBound'`,
	).Scan(&boundEvents); err != nil {
		t.Fatalf("count bound outbox: %v", err)
	}
	if boundEvents != 2 {
		t.Fatalf("bound events=%d, want 2", boundEvents)
	}

	actorContext := operation.WithContext(context.Background(), operation.Context{
		OperationID: "user.credential_binding.UnbindCredential",
		Actor: operation.ActorContext{
			AccountID: ownerID,
		},
	})
	if _, err := credentialCommands.UnbindCredential(
		actorContext,
		credentialapp.UnbindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypeFederatedSlotA,
		},
	); err != nil {
		t.Fatalf("revoke secondary credential: %v", err)
	}
	var revokedEvents int
	if err := pgPool.QueryRow(context.Background(), `
SELECT COUNT(*) FROM credential_bindings_outbox
WHERE event_type='CredentialRevoked'`,
	).Scan(&revokedEvents); err != nil {
		t.Fatalf("count revoked outbox: %v", err)
	}
	if revokedEvents != 1 {
		t.Fatalf("revoked events=%d, want 1", revokedEvents)
	}
	if _, err := credentialCommands.UnbindCredential(
		actorContext,
		credentialapp.UnbindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypePhone,
		},
	); err == nil {
		t.Fatal("last recoverable credential must not be revoked")
	}
}
