package api_integration

import (
	"context"
	"net/http"
	"net/url"
	"testing"
)

func TestCallHistoryStorageFacetFiltersBeforeCursorPagination(t *testing.T) {
	cleanAll(t)
	t.Cleanup(func() { cleanAll(t) })

	missedResponse := createTestCall(t, "history_missed_caller")
	missedCallID := extractSessionID(t, missedResponse)
	doPost(
		t,
		"/rtc/calls/"+missedCallID+"/cancel",
		`{}`,
		"history_missed_caller",
		http.StatusOK,
	)

	normalResponse := createTestCall(t, "history_normal_caller")
	normalCallID := extractSessionID(t, normalResponse)
	doPost(t, "/rtc/calls/"+normalCallID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+normalCallID+"/connected", `{}`, "history_normal_caller", http.StatusOK)
	doPost(t, "/rtc/calls/"+normalCallID+"/connected", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+normalCallID+"/hangup", `{}`, "history_normal_caller", http.StatusOK)

	ringingResponse := createTestCall(t, "history_ringing_caller")
	ringingCallID := extractSessionID(t, ringingResponse)

	code, missedPage := doGet(
		t,
		"/rtc/calls?missed=true&limit=1",
		"user_invitee_001",
	)
	if code != http.StatusOK {
		t.Fatalf("missed page status = %d", code)
	}
	missedItems := historyItems(t, missedPage)
	if len(missedItems) != 1 || missedItems[0]["callId"] != missedCallID {
		t.Fatalf("missed items = %#v, want only %s", missedItems, missedCallID)
	}
	if missedPage["nextCursor"] != "" {
		t.Fatalf("terminal filtered page emitted cursor %v", missedPage["nextCursor"])
	}

	code, firstEndedPage := doGet(
		t,
		"/rtc/calls?status=ended&limit=1",
		"user_invitee_001",
	)
	if code != http.StatusOK {
		t.Fatalf("first ended page status = %d", code)
	}
	firstItems := historyItems(t, firstEndedPage)
	if len(firstItems) != 1 {
		t.Fatalf("first ended page items = %d, want 1", len(firstItems))
	}
	cursor, _ := firstEndedPage["nextCursor"].(string)
	if cursor == "" {
		t.Fatal("first ended page must emit a continuation cursor")
	}
	if firstItems[0]["callId"] == ringingCallID {
		t.Fatal("status filter was applied after pagination")
	}

	code, secondEndedPage := doGet(
		t,
		"/rtc/calls?status=ended&limit=1&cursor="+url.QueryEscape(cursor),
		"user_invitee_001",
	)
	if code != http.StatusOK {
		t.Fatalf("second ended page status = %d", code)
	}
	secondItems := historyItems(t, secondEndedPage)
	if len(secondItems) != 1 {
		t.Fatalf("second ended page items = %d, want 1", len(secondItems))
	}
	if secondItems[0]["callId"] == firstItems[0]["callId"] {
		t.Fatalf("cursor repeated call %v", firstItems[0]["callId"])
	}
	if secondItems[0]["callId"] == ringingCallID {
		t.Fatal("second page included a non-ended call")
	}
	if secondEndedPage["nextCursor"] != "" {
		t.Fatalf("terminal ended page emitted cursor %v", secondEndedPage["nextCursor"])
	}
}

func TestCallSessionStorageFacetCreatesEveryDeclaredIndex(t *testing.T) {
	expected := map[string][]string{
		"call_sessions": {
			"idx_cs_initiator_created",
			"idx_cs_status",
			"idx_cs_conv_created",
			"idx_cs_circle_created",
			"idx_cs_room",
			"idx_cs_participant_user",
			"idx_cs_ended_reason",
			"idx_cs_version",
		},
		"call_session_command_receipts": {
			"idx_cs_receipts_aggregate",
			"idx_cs_receipts_expire",
		},
		"call_session_outbox": {
			"idx_cs_outbox_replay",
			"idx_cs_outbox_aggregate_version",
		},
	}

	for collectionName, names := range expected {
		collectionName := collectionName
		names := names
		t.Run(collectionName, func(t *testing.T) {
			cursor, err := mongoDB.Collection(collectionName).Indexes().List(context.Background())
			if err != nil {
				t.Fatalf("list %s indexes: %v", collectionName, err)
			}
			defer cursor.Close(context.Background())
			var documents []struct {
				Name string `bson:"name"`
			}
			if err := cursor.All(context.Background(), &documents); err != nil {
				t.Fatalf("decode %s indexes: %v", collectionName, err)
			}
			actual := make(map[string]struct{}, len(documents))
			for _, document := range documents {
				actual[document.Name] = struct{}{}
			}
			for _, name := range names {
				if _, found := actual[name]; !found {
					t.Errorf("%s missing declared index %s; actual=%v", collectionName, name, actual)
				}
			}
		})
	}
}

func historyItems(t *testing.T, page map[string]any) []map[string]any {
	t.Helper()
	raw, ok := page["items"].([]any)
	if !ok {
		t.Fatalf("history response missing items: %#v", page)
	}
	items := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		typed, ok := item.(map[string]any)
		if !ok {
			t.Fatalf("history item has type %T", item)
		}
		items = append(items, typed)
	}
	return items
}
