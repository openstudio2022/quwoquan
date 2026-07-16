package api_integration

import (
	"fmt"
	"net/http"
	"testing"
)

func TestSendAudioMessageWithMedia(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"audio test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaAssetId": "asset-audio-001",
		"clientMsgId": "audio-uuid-1"
	}`

	msg := sendMessage(t, convId, payload)

	if msg["messageId"] == nil {
		t.Error("response missing messageId")
	}
	if msg["seq"] == nil {
		t.Error("response missing seq")
	}
	if msg["timestamp"] == nil {
		t.Error("response missing timestamp")
	}
}

func TestSendAudioMessagePersistsMediaField(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"audio persist test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaAssetId": "asset-audio-002",
		"clientMsgId": "audio-uuid-2"
	}`

	sendMessage(t, convId, payload)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatal("expected at least 1 message")
	}

	msg := items[0].(map[string]any)
	if msg["type"] != "audio" {
		t.Errorf("expected type=audio, got %v", msg["type"])
	}
	if msg["mediaAssetId"] != "asset-audio-002" {
		t.Errorf("expected mediaAssetId preserved, got %v", msg["mediaAssetId"])
	}
	if msg["mediaDeliveryUrl"] != "https://media.test/asset-audio-002" {
		t.Errorf("expected MediaAsset Reader delivery URL, got %v", msg["mediaDeliveryUrl"])
	}
	if msg["mediaType"] != "audio" || msg["mediaContentType"] != "audio/test" {
		t.Errorf("expected typed media projection, got %#v", msg)
	}
	if msg["mediaFileSizeBytes"] != float64(2048) {
		t.Errorf("expected mediaFileSizeBytes=2048, got %v", msg["mediaFileSizeBytes"])
	}
}

func TestSendAudioMessageUpdatesConversationPreview(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"preview test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaAssetId": "asset-audio-preview",
		"clientMsgId": "audio-uuid-3"
	}`
	sendMessage(t, convId, payload)

	code, convResult := doGet(t, "/v1/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	preview := convResult["lastMessagePreview"]
	if preview != "[语音消息]" {
		t.Errorf("expected lastMessagePreview=[语音消息], got %v", preview)
	}
}

func TestSendAudioMessageDedup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"audio dedup test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaAssetId": "asset-audio-dedup",
		"clientMsgId": "audio-dedup-1"
	}`

	msg1 := sendMessage(t, convId, payload)
	msg2 := sendMessage(t, convId, payload)

	if msg1["messageId"] != msg2["messageId"] {
		t.Errorf("dedup failed: different messageId: %v vs %v", msg1["messageId"], msg2["messageId"])
	}
}

func TestSendAudioMessageSyncIncludesMedia(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"audio sync test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"sync-text-1"}`)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaAssetId": "asset-audio-sync",
		"clientMsgId": "sync-audio-1"
	}`
	sendMessage(t, convId, payload)

	syncResult := doPost(t,
		"/v1/chat/conversations/"+convId+"/sync",
		`{"lastSeq": 0, "limit": 10}`,
		"user_test_001", 200)

	messages, ok := syncResult["messages"].([]any)
	if !ok {
		t.Fatal("sync response missing messages")
	}

	found := false
	for _, m := range messages {
		msg := m.(map[string]any)
		if msg["type"] == "audio" {
			found = true
			if msg["mediaAssetId"] != "asset-audio-sync" ||
				msg["mediaDeliveryUrl"] != "https://media.test/asset-audio-sync" {
				t.Errorf("synced audio message MediaAsset projection drift: %#v", msg)
			}
		}
	}
	if !found {
		t.Error("sync did not include audio message")
	}
}

func TestSendAudioMessage_MixedTypes(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"mixed type test"}`)
	convId := conv["_id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"before audio","clientMsgId":"mix-1"}`)
	sendMessage(t, convId, `{"type":"audio","content":"","mediaAssetId":"asset-audio-mixed","clientMsgId":"mix-2"}`)
	sendMessage(t, convId, `{"type":"text","content":"after audio","clientMsgId":"mix-3"}`)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items := result["items"].([]any)
	if len(items) != 3 {
		t.Errorf("expected 3 messages, got %d", len(items))
	}

	types := make([]string, len(items))
	for i, item := range items {
		msg := item.(map[string]any)
		types[i] = msg["type"].(string)
	}
	expected := "[text audio text]"
	actual := fmt.Sprintf("%v", types)
	if actual != expected {
		t.Errorf("expected types %s, got %s", expected, actual)
	}
}

func TestSendAudioMessageRejectsRemovedMediaURL(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"typed audio test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	failure := doPost(
		t,
		"/v1/chat/conversations/"+convId+"/messages",
		`{"type":"audio","content":"","mediaUrl":"https://cdn.example.com/old.m4a","clientMsgId":"removed-media-url"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if failure["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("removed mediaUrl must fail strict request decoding: %#v", failure)
	}
}

func TestSendAudioMessageRejectsMissingMediaAssetID(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conv := createConversation(t, `{"type":"direct","title":"missing asset","initialMemberIds":["user_test_002"]}`)
	convID := conv["_id"].(string)
	failure := doPost(
		t,
		"/v1/chat/conversations/"+convID+"/messages",
		`{"type":"audio","content":"","clientMsgId":"missing-media-asset"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if failure["code"] != "CHAT.USER.message_media_invalid" {
		t.Fatalf("missing mediaAssetId must fail with stable media error: %#v", failure)
	}
}

func TestSendAudioMessageRejectsWrongMediaAssetType(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conv := createConversation(t, `{"type":"direct","title":"wrong asset type","initialMemberIds":["user_test_002"]}`)
	convID := conv["_id"].(string)
	failure := doPost(
		t,
		"/v1/chat/conversations/"+convID+"/messages",
		`{"type":"audio","content":"","mediaAssetId":"asset-image-not-voice","clientMsgId":"wrong-media-type"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if failure["code"] != "CHAT.USER.message_media_invalid" {
		t.Fatalf("wrong MediaAsset type must fail with stable media error: %#v", failure)
	}
}
