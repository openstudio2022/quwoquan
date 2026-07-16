package api_integration

import (
	"context"
	"net/http"
	"testing"

	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

// T3 CredentialBinding 全场景契约测试

func TestUnsupportedFutureLoginMethodsAreNotPublic(t *testing.T) {
	for _, route := range []string{
		"/v1/auth/login/apple",
		"/v1/auth/login/passkey",
	} {
		rec := doRequest(t, http.MethodPost, route, `{"credential":"must-not-be-accepted"}`, nil)
		if rec.Code != http.StatusNotFound {
			t.Fatalf(
				"%s is out of scope and must not be publicly routable: got %d: %s",
				route,
				rec.Code,
				rec.Body.String(),
			)
		}
	}
}

func TestLoginWithSocialProvider_FirstSyncSeedsAvatarVersion(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithExternalAuthProviderClient(externalProviderRuntime.client),
		application.WithAccessTokenSigner(testAccessSigner),
	)

	result, err := authService.LoginWithSocialProvider(
		context.Background(),
		"wechat",
		"sandbox-wechat-avatar-001",
		"device-social-1",
		"ios",
		"1.0.0",
	)
	if err != nil {
		t.Fatalf("social login first sync: %v", err)
	}
	if result.OwnerID == "" {
		t.Fatal("expected ownerId from social login")
	}

	var profileAvatarURL string
	var profileAvatarVersion int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COALESCE(avatar_url, ''), avatar_version FROM user_profiles WHERE user_id = $1`,
		result.OwnerID,
	).Scan(&profileAvatarURL, &profileAvatarVersion); err != nil {
		t.Fatalf("query profile avatar version: %v", err)
	}
	if profileAvatarURL == "" {
		t.Fatal("expected social login to seed avatar_url")
	}
	if profileAvatarVersion != 1 {
		t.Fatalf("expected social login to seed avatar_version=1, got %d", profileAvatarVersion)
	}

	var personaAvatarURL string
	var personaAvatarVersion int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COALESCE(avatar_url, ''), avatar_version FROM personas WHERE user_id = $1`,
		result.OwnerID,
	).Scan(&personaAvatarURL, &personaAvatarVersion); err != nil {
		t.Fatalf("query persona avatar version: %v", err)
	}
	if personaAvatarURL != profileAvatarURL {
		t.Fatalf("expected default persona avatar_url to inherit profile avatar, got %q vs %q", personaAvatarURL, profileAvatarURL)
	}
	if personaAvatarVersion != profileAvatarVersion {
		t.Fatalf("expected default persona avatar_version=%d, got %d", profileAvatarVersion, personaAvatarVersion)
	}
}

func TestLogin_ExistingCredentialReturnsOwner(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	authService := application.NewAuthService(
		persistence.NewPgProfileStore(pgPool),
		persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB),
		persistence.NewPgCredentialBindingStore(pgPool),
		persistence.NewPgAnonymousDeviceBindingStore(pgPool),
		shardDirectory,
		application.WithExternalAuthProviderClient(externalProviderRuntime.client),
		application.WithAccessTokenSigner(testAccessSigner),
	)
	firstLogin, err := authService.LoginWithSocialProvider(
		context.Background(),
		"wechat",
		"sandbox-wechat-existing",
		"device-existing",
		"ios",
		"1.0.0",
	)
	if err != nil {
		t.Fatalf("first WeChat credential login failed: %v", err)
	}
	secondLogin, err := authService.LoginWithSocialProvider(
		context.Background(),
		"wechat",
		"sandbox-wechat-existing",
		"device-existing",
		"ios",
		"1.0.0",
	)
	if err != nil {
		t.Fatalf("second WeChat credential login failed: %v", err)
	}
	if secondLogin.OwnerID != firstLogin.OwnerID {
		t.Errorf(
			"expected existing credential ownerId=%s, got %s",
			firstLogin.OwnerID,
			secondLogin.OwnerID,
		)
	}
}

func TestBindCredential_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "bind_owner", "bind_user")
	createTestCredential(t, "cred_phone", "bind_owner", "phone", "hash_phone_bind")

	rec := doRequest(t, http.MethodPost, "/v1/user/credentials",
		`{"credentialType":"wechat","credentialKey":"wx_union_id_123","displayLabel":"微信账号"}`,
		authHeaders("bind_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("bind credential: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// DB 验证
	var count int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND credential_type = 'wechat'`,
		"bind_owner").Scan(&count)
	if count != 1 {
		t.Errorf("expected wechat credential in DB, got count=%d", count)
	}
}

func TestUnbindCredential_LastCredentialForbidden(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "unbind_owner", "unbind_user")
	createTestCredential(t, "cred_only", "unbind_owner", "phone", "hash_only_phone")

	// 尝试解绑唯一凭证应被拒绝
	rec := doRequest(t, http.MethodDelete, "/v1/user/credentials/phone", "", authHeaders("unbind_owner"))
	if rec.Code == http.StatusOK {
		t.Fatal("expected error when unbinding the last credential")
	}
}

func TestUnbindCredential_KeepsRemaining(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "multi_cred_owner", "multi_cred_user")
	createTestCredential(t, "c_phone", "multi_cred_owner", "phone", "hash_multi_phone")
	createTestCredential(t, "c_wechat", "multi_cred_owner", "wechat", "wx_union_multi")

	// 解绑微信（还有手机号剩余）
	rec := doRequest(t, http.MethodDelete, "/v1/user/credentials/wechat", "", authHeaders("multi_cred_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("unbind wechat: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// DB 验证：手机号仍存在
	var phoneCount int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND credential_type = 'phone' AND is_active = true`,
		"multi_cred_owner").Scan(&phoneCount)
	if phoneCount != 1 {
		t.Errorf("phone credential should remain after unbinding wechat, got count=%d", phoneCount)
	}
}

func TestListCredentials(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "list_cred_owner", "list_cred_user")
	createTestCredential(t, "lc1", "list_cred_owner", "phone", "hash_lc_phone")
	createTestCredential(t, "lc2", "list_cred_owner", "apple", "apple_subject_123")

	rec := doRequest(t, http.MethodGet, "/v1/user/credentials", "", authHeaders("list_cred_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list credentials: expected 200, got %d", rec.Code)
	}
	result := parseJSON(t, rec)
	creds, _ := result["credentials"].([]any)
	if len(creds) != 2 {
		t.Errorf("expected 2 credentials, got %d", len(creds))
	}
	// 验证 SECRET 字段 credentialKey 不在响应中
	for _, c := range creds {
		cm, _ := c.(map[string]any)
		if _, hasKey := cm["credentialKey"]; hasKey {
			t.Error("credentialKey (SECRET) should NOT be exposed in list response")
		}
	}
}
