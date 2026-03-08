package tests

import (
	"testing"
)

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
