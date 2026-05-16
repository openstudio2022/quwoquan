package tests

import (
	"context"
	"net/http"
	"testing"
)

// T3 InviteRecord 归因防护契约测试

func TestInvite_GenerateAndGetByCode(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "inv_owner", "inv_user")
	createTestPersonaFull(t, "inv_persona", "inv_owner", "sa_inv", "InvSub", "open", true, true)

	rec := doRequest(t, http.MethodPost, "/v1/user/invites",
		`{"subAccountId":"sa_inv","channel":"direct","inviteePhone":"hash_invitee_phone"}`,
		authHeaders("inv_owner"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("generate invite: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	linkCode, _ := result["linkCode"].(string)
	if linkCode == "" {
		t.Fatal("expected linkCode in response")
	}

	// 通过 linkCode 获取邀请
	rec = doRequest(t, http.MethodGet, "/v1/invites/"+linkCode, "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("get invite by code: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	inv := parseJSON(t, rec)

	// 公开接口绝不暴露 inviterOwnerAccountId
	if _, hasOwner := inv["inviterOwnerAccountId"]; hasOwner {
		t.Error("inviterOwnerAccountId should NOT be exposed in public invite endpoint")
	}
	// 也不暴露 inviteePhoneHash
	if _, hasPhone := inv["inviteePhoneHash"]; hasPhone {
		t.Error("inviteePhoneHash should NOT be exposed in public invite endpoint")
	}
}

func TestInvite_Idempotent_SameKeyReturnsSameCode(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "idem_owner", "idem_user")
	createTestPersonaFull(t, "idem_persona", "idem_owner", "sa_idem", "IdemSub", "open", true, true)

	body := `{"subAccountId":"sa_idem","channel":"direct","inviteePhone":"hash_idem_phone"}`

	// 第一次生成
	rec1 := doRequest(t, http.MethodPost, "/v1/user/invites", body, authHeaders("idem_owner"))
	if rec1.Code != http.StatusCreated {
		t.Fatalf("first generate: expected 201, got %d: %s", rec1.Code, rec1.Body.String())
	}
	code1, _ := parseJSON(t, rec1)["linkCode"].(string)

	// 相同参数再次生成
	rec2 := doRequest(t, http.MethodPost, "/v1/user/invites", body, authHeaders("idem_owner"))
	if rec2.Code != http.StatusCreated {
		t.Fatalf("second generate: expected 201, got %d: %s", rec2.Code, rec2.Body.String())
	}
	code2, _ := parseJSON(t, rec2)["linkCode"].(string)

	if code1 != code2 {
		t.Errorf("idempotent invite should return same linkCode: got %s and %s", code1, code2)
	}

	// DB 中只有一条记录
	var count int
	_ = pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM invite_records WHERE inviter_sub_account_id = 'sa_idem' AND channel = 'direct'`).Scan(&count)
	if count != 1 {
		t.Errorf("expected exactly 1 invite record, got %d", count)
	}
}

func TestInvite_AcceptUpdatesStatus(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "accept_owner", "accept_user")
	createTestPersonaFull(t, "accept_persona", "accept_owner", "sa_accept", "AcceptSub", "open", true, true)

	// 生成邀请
	rec := doRequest(t, http.MethodPost, "/v1/user/invites",
		`{"subAccountId":"sa_accept","channel":"direct"}`,
		authHeaders("accept_owner"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("generate: %d: %s", rec.Code, rec.Body.String())
	}
	linkCode, _ := parseJSON(t, rec)["linkCode"].(string)

	// 接受邀请
	rec = doRequest(t, http.MethodPost, "/v1/invites/"+linkCode+"/accept", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("accept invite: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	// DB 验证：状态变为 accepted
	var status string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT status FROM invite_records WHERE link_code = $1`, linkCode).Scan(&status)
	if status != "accepted" {
		t.Errorf("expected status=accepted, got %s", status)
	}
}

func TestInvite_AttributionToSubAccount_NotOwner(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "attrib_owner", "attrib_user")
	createTestPersonaFull(t, "attrib_persona", "attrib_owner", "sa_attrib", "AttribSub", "open", true, true)

	rec := doRequest(t, http.MethodPost, "/v1/user/invites",
		`{"subAccountId":"sa_attrib","channel":"social"}`,
		authHeaders("attrib_owner"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("generate: %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	// 归因到 sub-account 级别，返回 inviterSubAccountId
	inviterSub, _ := result["inviterSubAccountId"].(string)
	if inviterSub != "sa_attrib" {
		t.Errorf("expected inviterSubAccountId=sa_attrib, got %s", inviterSub)
	}

	// DB 验证：inviter_owner_account_id 已存储（仅后台审计）
	var storedOwnerID string
	_ = pgPool.QueryRow(context.Background(),
		`SELECT inviter_owner_account_id FROM invite_records WHERE inviter_sub_account_id = 'sa_attrib'`).Scan(&storedOwnerID)
	if storedOwnerID != "attrib_owner" {
		t.Errorf("inviter_owner_account_id should be stored for audit, got %s", storedOwnerID)
	}

	// 公开 API 不暴露 owner
	if _, hasOwner := result["inviterOwnerAccountId"]; hasOwner {
		t.Error("inviterOwnerAccountId must NOT be in API response")
	}
}

func TestInvite_ListByInviter(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "list_inv_owner", "list_inv_user")
	createTestPersonaFull(t, "list_inv_p", "list_inv_owner", "sa_list_inv", "ListSub", "open", true, true)

	// 生成三个邀请
	for i := range 3 {
		_ = i
		doRequest(t, http.MethodPost, "/v1/user/invites",
			`{"subAccountId":"sa_list_inv","channel":"direct"}`,
			authHeaders("list_inv_owner"))
	}

	rec := doRequest(t, http.MethodGet, "/v1/user/invites?subAccountId=sa_list_inv", "", authHeaders("list_inv_owner"))
	if rec.Code != http.StatusOK {
		t.Fatalf("list invites: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	invites, _ := result["invites"].([]any)
	// 因为 idempotent 无 inviteePhone，每次生成都是新的 link_code
	if len(invites) < 1 {
		t.Errorf("expected at least 1 invite, got %d", len(invites))
	}
}

func TestInvite_LegacyIdentityFieldRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "alias_owner", "alias_user")
	createTestPersonaFull(t, "alias_persona", "alias_owner", "sa_alias", "AliasSub", "open", true)

	rec := doRequest(t, http.MethodPost, "/v1/user/invites",
		`{"legacyIdentityId":"sa_alias","channel":"direct"}`,
		authHeaders("alias_owner"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("generate with legacy identity field: expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}
