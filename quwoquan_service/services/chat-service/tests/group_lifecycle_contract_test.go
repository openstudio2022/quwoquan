package tests

import (
	"net/http"
	"testing"
)

func TestCreateConversation_WithInitialMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"初始成员测试","maxGroupSize":500,"initialMemberIds":["user_test_002","user_test_003"]}`,
	)
	convID := created["_id"].(string)
	if created["memberCount"] != float64(3) {
		t.Fatalf("expected memberCount=3, got %v", created["memberCount"])
	}

	code, result := doGet(t, "/v1/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok || len(items) != 3 {
		t.Fatalf("expected 3 members, got %v", result["items"])
	}
}

func TestTransferOwnership(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"转让测试","maxGroupSize":500,"initialMemberIds":["user_test_002"]}`,
	)
	convID := created["_id"].(string)

	code, _ := doPatch(
		t,
		"/v1/chat/conversations/"+convID+"/owner",
		`{"newOwnerId":"user_test_002"}`,
		"user_test_001",
	)
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/v1/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
	items := result["items"].([]any)
	roles := map[string]string{}
	for _, raw := range items {
		member := raw.(map[string]any)
		roles[member["userId"].(string)] = member["role"].(string)
	}
	if roles["user_test_001"] != "member" {
		t.Fatalf("expected creator to become member, got %q", roles["user_test_001"])
	}
	if roles["user_test_002"] != "owner" {
		t.Fatalf("expected new owner role, got %q", roles["user_test_002"])
	}
}

func TestUpdateGroupAdmins(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"管理员测试","maxGroupSize":500,"initialMemberIds":["user_test_002","user_test_003"]}`,
	)
	convID := created["_id"].(string)

	code, _ := doPut(
		t,
		"/v1/chat/conversations/"+convID+"/admins",
		`{"adminIds":["user_test_002"]}`,
		"user_test_001",
	)
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/v1/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
	items := result["items"].([]any)
	roles := map[string]string{}
	for _, raw := range items {
		member := raw.(map[string]any)
		roles[member["userId"].(string)] = member["role"].(string)
	}
	if roles["user_test_002"] != "admin" {
		t.Fatalf("expected admin role, got %q", roles["user_test_002"])
	}
	if roles["user_test_003"] != "member" {
		t.Fatalf("expected member role, got %q", roles["user_test_003"])
	}
}

func TestDissolveConversation_RemovesFromList(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"group","title":"解散测试","maxGroupSize":500}`)
	convID := created["_id"].(string)

	code, _ := doDelete(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/v1/chat/conversations?limit=20", "user_test_001")
	items := result["items"].([]any)
	for _, raw := range items {
		conversation := raw.(map[string]any)
		if conversation["_id"] == convID {
			t.Fatalf("expected dissolved conversation %s to be absent from list", convID)
		}
	}
}

func TestDissolveCircleConversation_Forbidden(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"圈子群","circleId":"circle_001","circleGroupId":"circle_group_default_001","maxGroupSize":500}`,
	)
	convID := created["_id"].(string)
	if created["type"] != "group" {
		t.Fatalf("expected circle-bound conversation to expose type=group, got %v", created["type"])
	}
	if created["circleGroupId"] != "circle_group_default_001" {
		t.Fatalf("expected circleGroupId to round-trip, got %v", created["circleGroupId"])
	}
	if created["bindingType"] != "circle_group" {
		t.Fatalf("expected circle group bindingType, got %v", created["bindingType"])
	}
	if created["lifecyclePolicy"] != "bound_to_circle" {
		t.Fatalf("expected bound_to_circle lifecycle, got %v", created["lifecyclePolicy"])
	}

	code, _ := doDelete(t, "/v1/chat/conversations/"+convID, "user_test_001")
	if code != 403 {
		t.Fatalf("expected 403, got %d", code)
	}
}

func TestCreateConversation_RejectsLegacyCircleType(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	doPost(
		t,
		"/v1/chat/conversations",
		`{"type":"circle","title":"旧圈子会话","circleId":"circle_legacy","maxGroupSize":500}`,
		"user_test_001",
		http.StatusBadRequest,
	)
}

func TestCreateConversation_GroupSemanticsRoundTrip(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"班级群","circleId":"school_circle_001","circleGroupId":"classroom_group_001","originType":"organization_node_group","bindingType":"organization_node","lifecyclePolicy":"bound_to_organization_node","maxGroupSize":500,"initialMemberIds":["user_test_002"]}`,
	)
	if created["type"] != "group" {
		t.Fatalf("expected type group, got %v", created["type"])
	}
	if created["circleId"] != "school_circle_001" {
		t.Fatalf("expected circleId round-trip, got %v", created["circleId"])
	}
	if created["circleGroupId"] != "classroom_group_001" {
		t.Fatalf("expected circleGroupId round-trip, got %v", created["circleGroupId"])
	}
	if created["originType"] != "organization_node_group" {
		t.Fatalf("expected organization_node_group origin, got %v", created["originType"])
	}
	if created["bindingType"] != "organization_node" {
		t.Fatalf("expected organization_node binding, got %v", created["bindingType"])
	}
	if created["lifecyclePolicy"] != "bound_to_organization_node" {
		t.Fatalf("expected bound_to_organization_node lifecycle, got %v", created["lifecyclePolicy"])
	}
}
