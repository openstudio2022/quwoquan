package api_integration

import (
	"context"
	"net/http"
	"testing"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/phonematch"
)

// ContactDiscovery 隐私隔离 + 端云一致哈希契约测试。
//
// 端云一致：credential_key 存规范化明文手机号，服务端经 phonematch.Hash 派生哈希
// 与发起者上传的哈希比对；测试上传 phonematch.Hash(phone) 复刻客户端行为。

const (
	cdOpenPhone   = "13800138001"
	cdSemiPhone   = "13800138002"
	cdStrictPhone = "13800138003"
	cdHiddenPhone = "13800138009"
)

func TestContactDiscovery_InitiateAndGetLatest(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "cd_owner", "cd_user")

	// 发起通讯录发现（无注册命中）
	rec := doRequest(t, http.MethodPost, "/owner/contact-discovery",
		`{"hashedPhones":["`+phonematch.Hash(cdOpenPhone)+`"]}`,
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
	rec = doRequest(t, http.MethodGet, "/owner/contact-discovery/latest", "", authHeaders("cd_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("get latest: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestContactDiscovery_MatchesOnlyOpenPersonas(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 注册三个用户：open、semi、strict 隔离级别（credential_key 存明文手机号）
	createTestProfile(t, "target_open", "target_open_user")
	createTestPersonaFull(t, "p_open", "target_open", "sa_open", "OpenSub", "open", true, true)
	createTestCredential(t, "c_open", "target_open", "phone", cdOpenPhone)

	createTestProfile(t, "target_semi", "target_semi_user")
	createTestPersonaFull(t, "p_semi", "target_semi", "sa_semi", "SemiSub", "semi", true, true)
	createTestCredential(t, "c_semi", "target_semi", "phone", cdSemiPhone)

	createTestProfile(t, "target_strict", "target_strict_user")
	createTestPersonaFull(t, "p_strict", "target_strict", "sa_strict", "StrictSub", "strict", true, true)
	createTestCredential(t, "c_strict", "target_strict", "phone", cdStrictPhone)

	// 发起者上传三个手机号哈希（与客户端同一算法）
	createTestProfile(t, "initiator", "initiator_user")
	rec := doRequest(t, http.MethodPost, "/owner/contact-discovery",
		`{"hashedPhones":["`+phonematch.Hash(cdOpenPhone)+`","`+phonematch.Hash(cdSemiPhone)+`","`+phonematch.Hash(cdStrictPhone)+`"]}`,
		authHeaders("initiator"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	matched, _ := result["matchedPersonaIds"].([]any)
	matchedSet := make(map[string]bool)
	for _, m := range matched {
		if s, ok := m.(string); ok {
			matchedSet[s] = true
		}
	}

	// open Persona必须匹配到
	if !matchedSet["sa_open"] {
		t.Errorf("open isolation persona should appear in matches; got %v", matched)
	}
	// strict Persona绝不能出现
	if matchedSet["sa_strict"] {
		t.Error("strict isolation persona must NOT appear in contact discovery matches")
	}

	// matches[] 富化投影：回显发起者自己上传的 hashedPhone + 关系能力位
	matches, _ := result["matches"].([]any)
	var openMatch map[string]any
	for _, raw := range matches {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if item["personaId"] == "sa_open" {
			openMatch = item
		}
	}
	if openMatch == nil {
		t.Fatalf("expected matches[] to contain sa_open projection; got %v", matches)
	}
	if openMatch["hashedPhone"] != phonematch.Hash(cdOpenPhone) {
		t.Errorf("matches[].hashedPhone must echo initiator's uploaded hash, got %v", openMatch["hashedPhone"])
	}
	if _, ok := openMatch["relationshipCapability"].(map[string]any); !ok {
		t.Errorf("matches[] must carry relationshipCapability to drive 添加/已添加")
	}
}

func TestContactDiscovery_Dismiss(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "dismiss_owner", "dismiss_user")

	// 发起
	rec := doRequest(t, http.MethodPost, "/owner/contact-discovery",
		`{"hashedPhones":["`+phonematch.Hash(cdHiddenPhone)+`"]}`,
		authHeaders("dismiss_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: %d", rec.Code)
	}
	result := parseJSON(t, rec)
	recordID, _ := result["id"].(string)

	// 关闭
	rec = doRequest(t, http.MethodDelete, "/owner/contact-discovery/"+recordID, "", authHeaders("dismiss_owner"))
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
	createTestCredential(t, "hidden_cred", "hidden_owner", "phone", cdHiddenPhone)

	// 发现方
	createTestProfile(t, "finder_owner", "finder_user")
	rec := doRequest(t, http.MethodPost, "/owner/contact-discovery",
		`{"hashedPhones":["`+phonematch.Hash(cdHiddenPhone)+`"]}`, authHeaders("finder_owner"))
	if rec.Code != http.StatusAccepted {
		t.Fatalf("initiate: %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	// 只有 personaId 应该暴露，绝不是 ownerId/userId
	if _, ok := result["ownerAccountId"]; ok {
		t.Error("ownerAccountId must NOT appear in contact discovery response")
	}
	matched, _ := result["matchedPersonaIds"].([]any)
	if len(matched) == 0 {
		t.Error("expected hidden_owner's open persona to be discovered")
	}
	for _, m := range matched {
		if s, ok := m.(string); ok && s == "hidden_owner" {
			t.Error("owner ID (hidden_owner) must NOT be in matchedPersonaIds")
		}
	}
}
