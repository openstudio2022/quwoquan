package tests

import (
	"context"
	"net/http"
	"testing"
)

// T3 SubAccount 隔离防护契约测试

func TestSubAccount_CreateAndList(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_1", "sub_owner1")
	createTestCredential(t, "cred1", "sub_owner_1", "phone", "hash_13800000001")

	// 创建子账号
	rec := doRequest(t, http.MethodPost, "/v1/user/sub-accounts",
		`{"displayName":"匿名账号","isolationLevel":"strict"}`,
		authHeaders("sub_owner_1"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("create sub-account: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	subAccountID, _ := result["subAccountId"].(string)
	if subAccountID == "" {
		t.Fatal("expected non-empty subAccountId in response")
	}

	// 列出子账号
	rec = doRequest(t, http.MethodGet, "/v1/user/sub-accounts", "", authHeaders("sub_owner_1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list sub-accounts: expected 200, got %d", rec.Code)
	}
	list := parseJSON(t, rec)
	accounts, _ := list["subAccounts"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one sub-account")
	}
}

func TestSubAccount_ActivateSwitchesExclusively(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_2", "sub_owner2")
	createTestPersonaFull(t, "sub_a", "sub_owner_2", "sa_id_a", "SubA", "open", true, true)
	createTestPersonaFull(t, "sub_b", "sub_owner_2", "sa_id_b", "SubB", "open", false, false)

	// 激活 sub_b
	rec := doRequest(t, http.MethodPost, "/v1/user/sub-accounts/sa_id_b/activate", "", authHeaders("sub_owner_2"))
	if rec.Code != http.StatusOK {
		t.Fatalf("activate sub-account: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// 验证 DB：只有一个激活的子账号
	var activeCount int
	err := pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM personas WHERE user_id = $1 AND is_active = true`,
		"sub_owner_2").Scan(&activeCount)
	if err != nil {
		t.Fatalf("query active count: %v", err)
	}
	if activeCount != 1 {
		t.Errorf("expected exactly 1 active sub-account, got %d", activeCount)
	}

	var activePersonaID string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT id FROM personas WHERE user_id = $1 AND is_active = true`,
		"sub_owner_2").Scan(&activePersonaID)
	if activePersonaID != "sub_b" {
		t.Errorf("expected sub_b to be active, got %s", activePersonaID)
	}
}

func TestSubAccount_DeleteForbidsLast(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_3", "sub_owner3")
	createTestPersonaFull(t, "only_sub", "sub_owner_3", "sa_only", "OnlySub", "open", true, true)

	// 删除唯一的子账号应该被拒绝
	rec := doRequest(t, http.MethodDelete, "/v1/user/sub-accounts/sa_only", "", authHeaders("sub_owner_3"))
	if rec.Code == http.StatusOK {
		t.Fatal("expected error when deleting the last sub-account")
	}
}

func TestSubAccount_StrictIsolationHidesFromContactDiscovery(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 用户 A 拥有 strict 隔离子账号
	createTestProfile(t, "strict_owner", "strict_user")
	createTestPersonaFull(t, "strict_persona", "strict_owner", "sa_strict", "Strict", "strict", true, true)
	// A 有手机号凭证
	createTestCredential(t, "cred_strict", "strict_owner", "phone", "hash_strict_phone")

	// 用户 B 发起通讯录发现，包含 A 的手机号哈希
	createTestProfile(t, "discover_owner", "discover_user")
	rec := doRequest(t, http.MethodPost, "/v1/user/contact-discovery",
		`{"hashedPhones":["hash_strict_phone"]}`,
		authHeaders("discover_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate contact discovery: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	// strict 隔离用户不应出现在匹配结果中
	matchedRaw, _ := result["matchedSubAccountIds"].([]any)
	for _, m := range matchedRaw {
		if s, ok := m.(string); ok && s == "sa_strict" {
			t.Error("strict isolation sub-account should NOT appear in contact discovery results")
		}
	}
}

func TestSubAccount_ListDoesNotLeakPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "leaktest_owner", "leaktest_user")
	createTestPersonaFull(t, "lk_persona", "leaktest_owner", "sa_lktest", "LeakTest", "open", true, true)

	rec := doRequest(t, http.MethodGet, "/v1/user/sub-accounts", "", authHeaders("leaktest_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list sub-accounts: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	accounts, _ := result["subAccounts"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one sub-account")
	}

	// purposeHint has json:"-" tag in the model and should never appear
	for _, acc := range accounts {
		am, _ := acc.(map[string]any)
		if _, has := am["purposeHint"]; has {
			t.Error("purposeHint is a private field and should NOT appear in sub-account list response")
		}
	}
}
