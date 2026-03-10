package tests

import (
	"context"
	"net/http"
	"testing"
)

// T3 CredentialBinding 全场景契约测试

func TestLogin_CreatesOwnerAccountOnFirstUse(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	rec := doRequest(t, http.MethodPost, "/v1/auth/login",
		`{"credentialType":"phone","credentialKey":"hash_new_phone","displayLabel":"13900000001"}`,
		nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("login: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	ownerID, _ := result["ownerId"].(string)
	if ownerID == "" {
		t.Fatal("expected ownerId in login response")
	}
	token, _ := result["accessToken"].(string)
	if token == "" {
		t.Fatal("expected accessToken in login response")
	}

	// DB 验证：owner_account 和 credential_binding 均已创建
	var profileCount int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM user_profiles WHERE user_id = $1`, ownerID).Scan(&profileCount)
	if profileCount != 1 {
		t.Errorf("expected user_profile to be created, got count=%d", profileCount)
	}

	var credCount int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND credential_type = 'phone'`,
		ownerID).Scan(&credCount)
	if credCount != 1 {
		t.Errorf("expected credential_binding to be created, got count=%d", credCount)
	}

	// DB 验证：同时创建了默认子账号
	var personaCount int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM personas WHERE user_id = $1`, ownerID).Scan(&personaCount)
	if personaCount != 1 {
		t.Errorf("expected default persona to be created, got count=%d", personaCount)
	}
}

func TestLogin_ExistingCredentialReturnsOwner(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "existing_owner", "existing_user")
	createTestCredential(t, "cred_existing", "existing_owner", "phone", "hash_existing_phone")

	// 第一次登录
	rec := doRequest(t, http.MethodPost, "/v1/auth/login",
		`{"credentialType":"phone","credentialKey":"hash_existing_phone"}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("login: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	ownerID, _ := result["ownerId"].(string)
	if ownerID != "existing_owner" {
		t.Errorf("expected ownerId=existing_owner, got %s", ownerID)
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
