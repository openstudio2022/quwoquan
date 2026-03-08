package tests

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestSendAudioMessageWithMedia(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"audio test"}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaUrl": "https://cdn.example.com/media/voice_001.m4a",
		"media": {
			"url": "https://cdn.example.com/media/voice_001.m4a",
			"mimeType": "audio/mp4",
			"fileSizeBytes": 48000,
			"durationMs": 5200,
			"waveform": [0.1, 0.3, 0.7, 0.5, 0.2],
			"codec": "aac"
		},
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

	conv := createConversation(t, `{"type":"direct","title":"audio persist test"}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"mediaUrl": "https://cdn.example.com/media/voice_002.m4a",
		"media": {
			"url": "https://cdn.example.com/media/voice_002.m4a",
			"mimeType": "audio/mp4",
			"fileSizeBytes": 96000,
			"durationMs": 10500,
			"waveform": [0.2, 0.5, 0.8, 0.4, 0.1],
			"codec": "aac"
		},
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
	if msg["mediaUrl"] != "https://cdn.example.com/media/voice_002.m4a" {
		t.Errorf("expected mediaUrl preserved, got %v", msg["mediaUrl"])
	}

	media, ok := msg["media"].(map[string]any)
	if !ok {
		t.Fatal("expected media field to be a map")
	}
	if media["mimeType"] != "audio/mp4" {
		t.Errorf("expected media.mimeType=audio/mp4, got %v", media["mimeType"])
	}
	if durationMs, ok := media["durationMs"].(float64); !ok || int(durationMs) != 10500 {
		t.Errorf("expected media.durationMs=10500, got %v", media["durationMs"])
	}
}

func TestSendAudioMessageUpdatesConversationPreview(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"preview test"}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"media": {"url": "https://cdn.example.com/voice.m4a", "durationMs": 3000},
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

	conv := createConversation(t, `{"type":"direct","title":"audio dedup test"}`)
	convId := conv["_id"].(string)

	payload := `{
		"type": "audio",
		"content": "",
		"media": {"url": "https://cdn.example.com/voice.m4a", "durationMs": 5000},
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

	conv := createConversation(t, `{"type":"direct","title":"audio sync test"}`)
	convId := conv["_id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"sync-text-1"}`)

	payload := `{
		"type": "audio",
		"content": "",
		"media": {"url": "https://cdn.example.com/voice.m4a", "durationMs": 7000, "codec": "aac"},
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
			media, ok := msg["media"].(map[string]any)
			if !ok {
				t.Error("synced audio message missing media field")
			} else {
				if media["codec"] != "aac" {
					t.Errorf("expected codec=aac, got %v", media["codec"])
				}
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
	sendMessage(t, convId, `{"type":"audio","content":"","media":{"url":"https://cdn.example.com/v.m4a","durationMs":3000},"clientMsgId":"mix-2"}`)
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

func TestSendAudioMessage_MediaFieldBackwardCompatibility(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"compat test"}`)
	convId := conv["_id"].(string)

	// Old-style: only mediaUrl, no media field
	sendMessage(t, convId, `{"type":"audio","content":"","mediaUrl":"https://cdn.example.com/old.m4a","clientMsgId":"compat-1"}`)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items := result["items"].([]any)
	msg := items[0].(map[string]any)

	if msg["mediaUrl"] != "https://cdn.example.com/old.m4a" {
		t.Errorf("old-style mediaUrl should be preserved, got %v", msg["mediaUrl"])
	}

	mediaBytes, _ := json.Marshal(msg["media"])
	if string(mediaBytes) != "null" && string(mediaBytes) != "" {
		t.Logf("media field present on old-style message (acceptable): %s", string(mediaBytes))
	}
}
