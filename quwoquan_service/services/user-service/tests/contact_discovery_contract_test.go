package tests

import (
	"context"
	"net/http"
	"testing"
)

// T3 ContactDiscovery 隐私隔离契约测试

func TestContactDiscovery_InitiateAndGetLatest(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "cd_owner", "cd_user")

	// 发起通讯录发现
	rec := doRequest(t, http.MethodPost, "/v1/user/contact-discovery",
		`{"hashedPhones":["hash_p1","hash_p2","hash_p3"]}`,
		authHeaders("cd_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	recordID, _ := result["id"].(string)
	if recordID == "" {
		t.Fatal("expected record id in response")
	}

	// DB 验证：记录已创建
	var count int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM contact_discovery_records WHERE owner_account_id = $1`,
		"cd_owner").Scan(&count)
	if count != 1 {
		t.Errorf("expected 1 discovery record in DB, got %d", count)
	}

	// 响应中不暴露 ownerAccountId 和 hashedPhones
	if _, hasOwner := result["ownerAccountId"]; hasOwner {
		t.Error("ownerAccountId should NOT be exposed in contact discovery response")
	}
	if _, hasPhones := result["hashedPhones"]; hasPhones {
		t.Error("hashedPhones should NOT be exposed in contact discovery response")
	}

	// 获取最新记录
	rec = doRequest(t, http.MethodGet, "/v1/user/contact-discovery/latest", "", authHeaders("cd_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("get latest: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestContactDiscovery_MatchesOnlyOpenSubAccounts(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 注册三个用户：open、semi、strict 隔离级别
	createTestProfile(t, "target_open", "target_open_user")
	createTestPersonaFull(t, "p_open", "target_open", "sa_open", "OpenSub", "open", true, true)
	createTestCredential(t, "c_open", "target_open", "phone", "hash_open_phone")

	createTestProfile(t, "target_semi", "target_semi_user")
	createTestPersonaFull(t, "p_semi", "target_semi", "sa_semi", "SemiSub", "semi", true, true)
	createTestCredential(t, "c_semi", "target_semi", "phone", "hash_semi_phone")

	createTestProfile(t, "target_strict", "target_strict_user")
	createTestPersonaFull(t, "p_strict", "target_strict", "sa_strict", "StrictSub", "strict", true, true)
	createTestCredential(t, "c_strict", "target_strict", "phone", "hash_strict_phone")

	// 发起者上传三个手机号哈希
	createTestProfile(t, "initiator", "initiator_user")
	rec := doRequest(t, http.MethodPost, "/v1/user/contact-discovery",
		`{"hashedPhones":["hash_open_phone","hash_semi_phone","hash_strict_phone"]}`,
		authHeaders("initiator"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	matched, _ := result["matchedSubAccountIds"].([]any)
	matchedSet := make(map[string]bool)
	for _, m := range matched {
		if s, ok := m.(string); ok {
			matchedSet[s] = true
		}
	}

	// open 子账号必须匹配到
	if !matchedSet["sa_open"] {
		t.Error("open isolation sub-account should appear in contact discovery matches")
	}
	// strict 子账号绝不能出现
	if matchedSet["sa_strict"] {
		t.Error("strict isolation sub-account must NOT appear in contact discovery matches")
	}
}

func TestContactDiscovery_Dismiss(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "dismiss_owner", "dismiss_user")

	// 发起
	rec := doRequest(t, http.MethodPost, "/v1/user/contact-discovery",
		`{"hashedPhones":["hash_dismiss_p"]}`,
		authHeaders("dismiss_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: %d", rec.Code)
	}
	result := parseJSON(t, rec)
	recordID, _ := result["id"].(string)

	// 关闭
	rec = doRequest(t, http.MethodDelete, "/v1/user/contact-discovery/"+recordID, "", authHeaders("dismiss_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("dismiss: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// DB 验证：状态变为 dismissed
	var status string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT status FROM contact_discovery_records WHERE id = $1`, recordID).Scan(&status)
	if status != "dismissed" {
		t.Errorf("expected status=dismissed, got %s", status)
	}
}

func TestContactDiscovery_NeverExposesOwnerAccountId(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 被发现方
	createTestProfile(t, "hidden_owner", "hidden_user")
	createTestPersonaFull(t, "hidden_p", "hidden_owner", "sa_hidden", "HiddenSub", "open", true, true)
	createTestCredential(t, "hidden_cred", "hidden_owner", "phone", "hash_hidden_phone")

	// 发现方
	createTestProfile(t, "finder_owner", "finder_user")
	rec := doRequest(t, http.MethodPost, "/v1/user/contact-discovery",
		`{"hashedPhones":["hash_hidden_phone"]}`, authHeaders("finder_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	// 只有 subAccountId 应该暴露，绝不是 ownerId/userId
	if _, ok := result["ownerAccountId"]; ok {
		t.Error("ownerAccountId must NOT appear in contact discovery response")
	}
	matched, _ := result["matchedSubAccountIds"].([]any)
	for _, m := range matched {
		// 确认匹配到的是 subAccountId（sa_hidden），不是 owner ID
		if s, ok := m.(string); ok && s == "hidden_owner" {
			t.Error("owner ID (hidden_owner) must NOT be in matchedSubAccountIds")
		}
	}
}
