// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/member-add-remove-policy/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func memberItemsUserIDs(t *testing.T, items []any) []string {
	t.Helper()
	out := make([]string, 0, len(items))
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			t.Fatal("item not object")
		}
		uid, ok := m["userId"].(string)
		if !ok {
			t.Fatalf("userId missing or not string: %v", m["userId"])
		}
		out = append(out, uid)
	}
	return out
}

func TestAddMembersUpdatesCount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"member test","maxGroupSize":100}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_b","user_c"]}`, "user_test_001", 200)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	if len(items) < 3 {
		t.Errorf("expected >=3 members (owner + 2 added), got %d", len(items))
	}
}

func TestRemoveMember(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"remove test"}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_to_remove"]}`, "user_test_001", 200)

	code, _ := doDelete(t, "/chat/conversations/"+convId+"/members/user_to_remove", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
}

func TestListMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"list member test"}`)
	convId := conv["id"].(string)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	if len(items) < 1 {
		t.Error("expected at least 1 member (owner)")
	}
	for _, raw := range items {
		item := raw.(map[string]any)
		if item["memberType"] == "assistant" {
			continue
		}
		userID, _ := item["userId"].(string)
		if item["userHandle"] != "handle_"+userID {
			t.Fatalf("member must expose canonical userHandle: %#v", item)
		}
	}
}

func TestListMembersHidesSuspendedMemberAndRestoresVisibility(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conversation := createConversation(
		t,
		`{"type":"group","title":"account restriction roster"}`,
	)
	conversationID := conversation["id"].(string)
	doPost(
		t,
		"/chat/conversations/"+conversationID+"/members",
		`{"userIds":["user_restricted_member"]}`,
		"user_test_001",
		200,
	)
	if _, err := requireMongoDB(t).Collection("conversation_memberships").UpdateOne(
		t.Context(),
		bson.M{
			"conversationId": conversationID,
			"userId":         "user_restricted_member",
		},
		bson.M{"$set": bson.M{
			"accountRestricted":         true,
			"accountRestrictionVersion": int64(7),
		}},
	); err != nil {
		t.Fatal(err)
	}

	code, result := doGet(
		t,
		"/chat/conversations/"+conversationID+"/members?limit=50",
		"user_test_001",
	)
	if code != http.StatusOK {
		t.Fatalf("restricted roster status=%d result=%v", code, result)
	}
	for _, userID := range memberItemsUserIDs(t, result["items"].([]any)) {
		if userID == "user_restricted_member" {
			t.Fatal("suspended member leaked into visible roster")
		}
	}
	if _, err := requireMongoDB(t).Collection("conversation_memberships").UpdateOne(
		t.Context(),
		bson.M{
			"conversationId": conversationID,
			"userId":         "user_restricted_member",
		},
		bson.M{"$set": bson.M{
			"accountRestricted":         false,
			"accountRestrictionVersion": int64(8),
		}},
	); err != nil {
		t.Fatal(err)
	}
	code, result = doGet(
		t,
		"/chat/conversations/"+conversationID+"/members?limit=50",
		"user_test_001",
	)
	if code != http.StatusOK {
		t.Fatalf("restored roster status=%d result=%v", code, result)
	}
	found := false
	for _, userID := range memberItemsUserIDs(t, result["items"].([]any)) {
		found = found || userID == "user_restricted_member"
	}
	if !found {
		t.Fatal("restored member did not return to visible roster")
	}
}

func TestInviteAssistant(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assistant test"}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/assistant",
		`{"skillId":"general"}`, "user_test_001", 200)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}

	hasAssistant := false
	for _, item := range items {
		m, _ := item.(map[string]any)
		if m["memberType"] == "assistant" {
			hasAssistant = true
			break
		}
	}
	if !hasAssistant {
		t.Error("expected assistant member after invite")
	}
}

func TestRemoveAssistant(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	convId := "fixture_remove_assistant_conv"
	seedConversationWithAssistantMember(t, convId, "user_test_001", "rm assistant test")

	code, _ := doDelete(t, "/chat/conversations/"+convId+"/assistant", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
}

func TestCircleGroupBoundConversationRejectsAssistantMutations(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"circle managed assistant"}`)
	convID := conv["id"].(string)
	if _, err := requireMongoDB(t).Collection("conversations").UpdateOne(
		context.Background(),
		bson.M{"_id": convID},
		bson.M{"$set": bson.M{"circleId": "circle-assistant", "circleGroupId": "group-assistant"}},
	); err != nil {
		t.Fatalf("seed circle-bound conversation: %v", err)
	}

	invite := doPost(
		t,
		"/chat/conversations/"+convID+"/assistant",
		`{"skillId":"general"}`,
		"user_test_001",
		409,
	)
	if invite["code"] != "CHAT.USER.source_managed_conversation" {
		t.Fatalf("invite must be delegated to CircleGroup, got %#v", invite)
	}
	removeCode, remove := doDelete(
		t,
		"/chat/conversations/"+convID+"/assistant",
		"user_test_001",
	)
	if removeCode != 409 || remove["code"] != "CHAT.USER.source_managed_conversation" {
		t.Fatalf("remove must be delegated to CircleGroup: status=%d body=%#v", removeCode, remove)
	}
}

func TestListMembers_SortJoinedAsc(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"sort joined"}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_join_second","user_join_third"]}`, "user_test_001", 200)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50&sort=joined_asc", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	ids := memberItemsUserIDs(t, items)
	want := []string{"user_test_001", "user_join_second", "user_join_third"}
	if len(ids) != len(want) {
		t.Fatalf("got %d members, want %d: %v", len(ids), len(want), ids)
	}
	for i := range want {
		if ids[i] != want[i] {
			t.Errorf("joined_asc position %d: got %q want %q (full %v)", i, ids[i], want[i], ids)
		}
	}
}

func TestListMembers_SortDisplayNameAsc(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"sort display"}`)
	convId := conv["id"].(string)

	// Join order: zebra then apple — display_name_asc should still order apple before zebra.
	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_zebra","user_apple"]}`, "user_test_001", 200)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50&sort=display_name_asc", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	ids := memberItemsUserIDs(t, items)
	// Display_user_apple < Display_user_test_001 < Display_user_zebra
	want := []string{"user_apple", "user_test_001", "user_zebra"}
	if len(ids) != len(want) {
		t.Fatalf("got %d members, want %d: %v", len(ids), len(want), ids)
	}
	for i := range want {
		if ids[i] != want[i] {
			t.Errorf("display_name_asc position %d: got %q want %q (full %v)", i, ids[i], want[i], ids)
		}
	}
}

func TestListMembers_DisplayNameFromResolver(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"resolver dn"}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_dn_check"]}`, "user_test_001", 200)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	for _, it := range items {
		m := it.(map[string]any)
		if m["userId"] == "user_dn_check" {
			if m["displayName"] != "Display_user_dn_check" {
				t.Errorf("displayName: got %v want Display_user_dn_check", m["displayName"])
			}
			return
		}
	}
	t.Error("user_dn_check not found in members")
}

func TestMembersRosterRevision_BumpsOnAdd(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"revision bump"}`)
	convId := conv["id"].(string)

	code, c0 := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("get conversation: %d", code)
	}
	rev0, ok := c0["membersRosterRevision"].(float64)
	if !ok {
		t.Fatalf("membersRosterRevision type %T", c0["membersRosterRevision"])
	}
	if rev0 != 1 {
		t.Fatalf("expected initial revision 1, got %v", rev0)
	}

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_rev_bump"]}`, "user_test_001", 200)

	code, c1 := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("get conversation after add: %d", code)
	}
	rev1, ok := c1["membersRosterRevision"].(float64)
	if !ok {
		t.Fatalf("membersRosterRevision type %T", c1["membersRosterRevision"])
	}
	if rev1 != 2 {
		t.Fatalf("expected revision 2 after add, got %v", rev1)
	}
}
