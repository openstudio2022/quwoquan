package api_integration

import (
	"net/http"
	"testing"
)

func TestChatMediaUploadContract(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	initResp := doPost(
		t,
		"/v1/chat/media/uploads:init",
		`{"mediaType":"video","ownerId":"user_test_001","fileName":"clip.mp4","contentType":"video/mp4","fileSize":4,"assetScope":"draft","sourceKind":"chat_attachment"}`,
		"user_test_001",
		http.StatusOK,
	)
	sessionID, _ := initResp["sessionId"].(string)
	if sessionID == "" {
		t.Fatalf("expected sessionId in init response: %+v", initResp)
	}
	if uploadURL, _ := initResp["uploadUrl"].(string); uploadURL == "" {
		t.Fatalf("expected uploadUrl in init response: %+v", initResp)
	}

	completeResp := doPost(
		t,
		"/v1/chat/media/uploads:complete",
		`{"sessionId":"`+sessionID+`"}`,
		"user_test_001",
		http.StatusOK,
	)
	if completeResp["status"] != "ready" {
		t.Fatalf("expected ready status, got %+v", completeResp)
	}
	if cdnURL, _ := completeResp["cdnUrl"].(string); cdnURL == "" {
		t.Fatalf("expected cdnUrl in complete response: %+v", completeResp)
	}

	abortResp := doPost(
		t,
		"/v1/chat/media/uploads:abort",
		`{"sessionId":"`+sessionID+`"}`,
		"user_test_001",
		http.StatusOK,
	)
	if abortResp["status"] != "aborted" {
		t.Fatalf("expected aborted status, got %+v", abortResp)
	}
}
