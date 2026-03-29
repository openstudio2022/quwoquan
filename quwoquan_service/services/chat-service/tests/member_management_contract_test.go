package tests

import (
	"testing"
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
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_b","user_c"]}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
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
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_to_remove"]}`, "user_test_001", 200)

	code, _ := doDelete(t, "/v1/chat/conversations/"+convId+"/members/user_to_remove", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
}

func TestListMembers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"list member test"}`)
	convId := conv["_id"].(string)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
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
}

func TestInviteAssistant(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assistant test"}`)
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/assistant",
		`{"skillId":"general"}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
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

	conv := createConversation(t, `{"type":"group","title":"rm assistant test"}`)
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/assistant",
		`{"skillId":"general"}`, "user_test_001", 200)

	code, _ := doDelete(t, "/v1/chat/conversations/"+convId+"/assistant", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
}

func TestListMembers_SortJoinedAsc(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"sort joined"}`)
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_join_second","user_join_third"]}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50&sort=joined_asc", "user_test_001")
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
	convId := conv["_id"].(string)

	// Join order: zebra then apple — display_name_asc should still order apple before zebra.
	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_zebra","user_apple"]}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50&sort=display_name_asc", "user_test_001")
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
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_dn_check"]}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
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
	convId := conv["_id"].(string)

	code, c0 := doGet(t, "/v1/chat/conversations/"+convId, "user_test_001")
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

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_rev_bump"]}`, "user_test_001", 200)

	code, c1 := doGet(t, "/v1/chat/conversations/"+convId, "user_test_001")
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
