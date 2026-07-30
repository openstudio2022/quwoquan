package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestCreateConversation_WithInitialMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(
		t,
		`{"type":"group","title":"初始成员测试","maxGroupSize":500,"initialMemberIds":["user_test_002","user_test_003"]}`,
	)
	convID := created["id"].(string)
	if created["memberCount"] != float64(3) {
		t.Fatalf("expected memberCount=3, got %v", created["memberCount"])
	}

	code, result := doGet(t, "/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
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
	convID := created["id"].(string)

	code, _ := doPatch(
		t,
		"/chat/conversations/"+convID+"/owner",
		`{"newOwnerId":"user_test_002"}`,
		"user_test_001",
	)
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
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
	convID := created["id"].(string)

	code, _ := doPut(
		t,
		"/chat/conversations/"+convID+"/admins",
		`{"adminIds":["user_test_002"]}`,
		"user_test_001",
	)
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/chat/conversations/"+convID+"/members?limit=10", "user_test_001")
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
	convID := created["id"].(string)

	code, _ := doDelete(t, "/chat/conversations/"+convID, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	_, result := doGet(t, "/chat/conversations?limit=20", "user_test_001")
	items := result["items"].([]any)
	for _, raw := range items {
		conversation := raw.(map[string]any)
		if conversation["id"] == convID {
			t.Fatalf("expected dissolved conversation %s to be absent from list", convID)
		}
	}
}

func TestCreateConversationRejectsClientSuppliedCircleBinding(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	rejected := doPost(
		t,
		"/chat/conversations",
		`{"type":"group","title":"圈子群","circleId":"circle_001","circleGroupId":"circle_group_default_001","maxGroupSize":500}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if rejected["code"] != "CHAT.USER.circle_group_binding_write_forbidden" {
		t.Fatalf("client circle binding must return dedicated rejection, got %#v", rejected)
	}
	if count, err := mongoDB.Collection("conversations").CountDocuments(context.Background(), bson.M{}); err != nil || count != 0 {
		t.Fatalf("rejected binding must not create a conversation: count=%d err=%v", count, err)
	}
}

func TestCreateConversation_RejectsRetiredCircleType(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	doPost(
		t,
		"/chat/conversations",
		`{"type":"circle","title":"旧圈子会话","maxGroupSize":500}`,
		"user_test_001",
		http.StatusBadRequest,
	)
}

func TestCreateConversationRejectsClientSuppliedOriginFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	rejected := doPost(
		t,
		"/chat/conversations",
		`{"type":"group","title":"班级群","circleId":"school_circle_001","circleGroupId":"classroom_group_001","originType":"circle_group","bindingType":"organization_node","lifecyclePolicy":"bound_to_organization_node","maxGroupSize":500,"initialMemberIds":["user_test_002"]}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if rejected["code"] != "CHAT.USER.circle_group_binding_write_forbidden" {
		t.Fatalf("client origin fields must return dedicated rejection, got %#v", rejected)
	}
}

func TestCreateConversationRejectsRetiredOriginValues(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	for _, retired := range []string{
		"circle_default_group",
		"circle_self_built_group",
		"organization_node_group",
		"homepage_related_group",
		"assistant_invited",
	} {
		rejected := doPost(
			t,
			"/chat/conversations",
			fmt.Sprintf(
				`{"type":"group","title":"退役来源拒绝","originType":%q,"maxGroupSize":500}`,
				retired,
			),
			"user_test_001",
			http.StatusBadRequest,
		)
		if rejected["code"] != "CHAT.USER.circle_group_binding_write_forbidden" {
			t.Fatalf("retired originType %q must be rejected: %#v", retired, rejected)
		}
	}
}
