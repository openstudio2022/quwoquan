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

	// 创建分身
	rec := doRequest(t, http.MethodPost, "/v1/user/personas",
		`{"displayName":"匿名分身","isolationLevel":"strict"}`,
		authHeaders("sub_owner_1"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("create persona: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	subAccountID, _ := result["subAccountId"].(string)
	if subAccountID == "" {
		t.Fatal("expected non-empty subAccountId in response")
	}

	// 列出分身
	rec = doRequest(t, http.MethodGet, "/v1/user/personas", "", authHeaders("sub_owner_1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list personas: expected 200, got %d", rec.Code)
	}
	list := parseJSON(t, rec)
	accounts, _ := list["items"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one persona")
	}
}

func TestSubAccount_ActivateSwitchesExclusively(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_2", "sub_owner2")
	createTestPersonaFull(t, "sub_a", "sub_owner_2", "sa_id_a", "SubA", "open", true, true)
	createTestPersonaFull(t, "sub_b", "sub_owner_2", "sa_id_b", "SubB", "open", false, false)

	// 激活 sub_b
	rec := doRequest(t, http.MethodPost, "/v1/user/personas/sa_id_b/activate", "", authHeaders("sub_owner_2"))
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

	var activeSubAccountID string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT sub_account_id FROM personas WHERE user_id = $1 AND is_active = true`,
		"sub_owner_2").Scan(&activeSubAccountID)
	if activeSubAccountID != "sa_id_b" {
		t.Errorf("expected sa_id_b to be active, got %s", activeSubAccountID)
	}
}

func TestSubAccount_DeleteForbidsLast(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sub_owner_3", "sub_owner3")
	createTestPersonaFull(t, "only_sub", "sub_owner_3", "sa_only", "OnlySub", "open", true, true)

	// 删除唯一的分身应该被拒绝
	rec := doRequest(t, http.MethodDelete, "/v1/user/personas/sa_only/delete-empty", "", authHeaders("sub_owner_3"))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 when deleting the last persona, got %d: %s", rec.Code, rec.Body.String())
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

	rec := doRequest(t, http.MethodGet, "/v1/user/personas", "", authHeaders("leaktest_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list personas: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	accounts, _ := result["items"].([]any)
	if len(accounts) == 0 {
		t.Fatal("expected at least one persona")
	}

	// purposeHint 属于私有管理字段，不应出现在列表响应
	for _, acc := range accounts {
		am, _ := acc.(map[string]any)
		if _, has := am["purposeHint"]; has {
			t.Error("purposeHint is a private field and should NOT appear in persona list response")
		}
	}
}
