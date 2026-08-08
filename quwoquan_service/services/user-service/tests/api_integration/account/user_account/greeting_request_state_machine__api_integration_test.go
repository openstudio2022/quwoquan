// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003
package api_integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
)

func waitForGreetingStreamEvent(
	t *testing.T,
	eventID string,
) map[string]string {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cursor := "0-0"
	for ctx.Err() == nil {
		messages, err := redisClient.XRead(
			ctx,
			map[string]string{mq.GreetingEventStream: cursor},
			100,
			100*time.Millisecond,
		)
		if err != nil {
			t.Fatalf("read GreetingRequest stream: %v", err)
		}
		for _, message := range messages {
			cursor = message.ID
			if message.Values["eventId"] == eventID {
				return message.Values
			}
		}
	}
	t.Fatalf("GreetingRequest stream event %q was not published", eventID)
	return nil
}

func TestGreeting_SendReplyIgnoreCancel(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "gr_req", "req")
	createTestProfile(t, "gr_tgt", "tgt")
	createTestPersonaFull(t, "gr_req_p", "gr_req", "sa_gr_req", "req", "default", true)
	createTestPersonaFull(t, "gr_tgt_p", "gr_tgt", "sa_gr_tgt", "tgt", "default", true)

	sendRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr_tgt","requestMessage":"hello","source":"profile"}`,
		authHeadersForPersona("gr_req", "sa_gr_req"),
	)
	if sendRec.Code != http.StatusCreated {
		t.Fatalf("send greeting: expected 201, got %d: %s", sendRec.Code, sendRec.Body.String())
	}
	sendBody := parseJSON(t, sendRec)
	requestID, _ := sendBody["id"].(string)
	if requestID == "" {
		t.Fatalf("expected greeting id, got %#v", sendBody)
	}
	streamEvent := waitForGreetingStreamEvent(
		t,
		"greeting:"+requestID+":GreetingRequestSent",
	)
	if streamEvent["targetPersonaId"] != "sa_gr_tgt" ||
		streamEvent["recipientAccountId"] != "gr_tgt" ||
		streamEvent["recipientAccountId"] == streamEvent["targetPersonaId"] {
		t.Fatalf("GreetingRequest recipient identity drifted: %+v", streamEvent)
	}

	for _, listing := range []struct {
		path    string
		headers map[string]string
	}{
		{path: "/user/greeting-request/inbox", headers: authHeadersForPersona("gr_tgt", "sa_gr_tgt")},
		{path: "/user/greeting-request/outbox", headers: authHeadersForPersona("gr_req", "sa_gr_req")},
	} {
		listRec := doRequest(t, http.MethodGet, listing.path, "", listing.headers)
		if listRec.Code != http.StatusOK {
			t.Fatalf("list %s: expected 200, got %d: %s", listing.path, listRec.Code, listRec.Body.String())
		}
		listBody := parseJSON(t, listRec)
		if len(listBody) != 2 || listBody["items"] == nil {
			t.Fatalf("list %s must return exact GreetingRequestSlice: %#v", listing.path, listBody)
		}
		if _, retired := listBody["cursor"]; retired {
			t.Fatalf("list %s retains retired cursor response key: %#v", listing.path, listBody)
		}
		if _, exists := listBody["nextCursor"]; !exists {
			t.Fatalf("list %s missing canonical nextCursor: %#v", listing.path, listBody)
		}
	}

	dupRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr_tgt","requestMessage":"again","source":"profile"}`,
		authHeadersForPersona("gr_req", "sa_gr_req"),
	)
	if dupRec.Code != http.StatusConflict {
		t.Fatalf("duplicate pending greeting: expected 409, got %d: %s", dupRec.Code, dupRec.Body.String())
	}

	replyRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request/"+requestID+"/reply",
		"",
		authHeadersForPersona("gr_tgt", "sa_gr_tgt"),
	)
	if replyRec.Code != http.StatusOK {
		t.Fatalf("reply greeting: expected 200, got %d: %s", replyRec.Code, replyRec.Body.String())
	}
	replyBody := parseJSON(t, replyRec)
	if replyBody["status"] != "replied" {
		t.Fatalf("expected status=replied, got %#v", replyBody)
	}
	if replyBody["promotedConversationId"] == "" {
		t.Fatalf("expected promotedConversationId, got %#v", replyBody)
	}

	capRec := doRequest(
		t,
		http.MethodGet,
		"/user/personas/sa_gr_tgt/relationship/capability",
		"",
		authHeadersForPersona("gr_req", "sa_gr_req"),
	)
	cap := parseJSON(t, capRec)
	if cap["hasFormalConversation"] != true {
		t.Fatalf("expected hasFormalConversation=true after reply, got %#v", cap)
	}
}

func TestGreeting_IgnoreAndCancel(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "gr2_req", "req2")
	createTestProfile(t, "gr2_tgt", "tgt2")
	createTestPersonaFull(t, "gr2_req_p", "gr2_req", "sa_gr2_req", "req2", "default", true)
	createTestPersonaFull(t, "gr2_tgt_p", "gr2_tgt", "sa_gr2_tgt", "tgt2", "default", true)

	sendRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr2_tgt","requestMessage":"ping","source":"profile"}`,
		authHeadersForPersona("gr2_req", "sa_gr2_req"),
	)
	sendBody := parseJSON(t, sendRec)
	requestID, _ := sendBody["id"].(string)

	ignoreRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request/"+requestID+"/ignore",
		"",
		authHeadersForPersona("gr2_tgt", "sa_gr2_tgt"),
	)
	if ignoreRec.Code != http.StatusOK {
		t.Fatalf("ignore greeting: expected 200, got %d", ignoreRec.Code)
	}
	ignoreBody := parseJSON(t, ignoreRec)
	if ignoreBody["status"] != "ignored" {
		t.Fatalf("expected ignored status, got %#v", ignoreBody)
	}

	sendRec2 := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr2_tgt","requestMessage":"again","source":"profile"}`,
		authHeadersForPersona("gr2_req", "sa_gr2_req"),
	)
	if sendRec2.Code != http.StatusCreated {
		t.Fatalf("resend after ignore: expected 201, got %d", sendRec2.Code)
	}
	cancelBody := parseJSON(t, sendRec2)
	cancelID, _ := cancelBody["id"].(string)

	cancelRec := doRequest(
		t,
		http.MethodDelete,
		"/user/greeting-request/"+cancelID,
		"",
		authHeadersForPersona("gr2_req", "sa_gr2_req"),
	)
	if cancelRec.Code != http.StatusOK {
		t.Fatalf("cancel greeting: expected 200, got %d", cancelRec.Code)
	}
	cancelResult := parseJSON(t, cancelRec)
	if cancelResult["status"] != "cancelled" {
		t.Fatalf("expected cancelled status, got %#v", cancelResult)
	}

	var count int
	err := pgPool.QueryRow(context.Background(), `
		SELECT COUNT(*) FROM greeting_requests
		WHERE requester_persona_id = $1 AND target_persona_id = $2 AND status = 'pending'`,
		"sa_gr2_req", "sa_gr2_tgt").Scan(&count)
	if err != nil {
		t.Fatalf("count pending: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected no pending greeting, got %d", count)
	}
}

func TestGreeting_MutualSenderRejected(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "gr4_req", "req4")
	createTestProfile(t, "gr4_tgt", "tgt4")
	createTestPersonaFull(t, "gr4_req_p", "gr4_req", "sa_gr4_req", "req4", "default", true)
	createTestPersonaFull(t, "gr4_tgt_p", "gr4_tgt", "sa_gr4_tgt", "tgt4", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/personas/sa_gr4_tgt/follow",
		"",
		authHeadersForPersona("gr4_req", "sa_gr4_req"),
	)
	doRequest(
		t,
		http.MethodPost,
		"/user/personas/sa_gr4_req/follow",
		"",
		authHeadersForPersona("gr4_tgt", "sa_gr4_tgt"),
	)

	sendRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr4_tgt","requestMessage":"mutual","source":"profile"}`,
		authHeadersForPersona("gr4_req", "sa_gr4_req"),
	)
	if sendRec.Code != http.StatusConflict {
		t.Fatalf("mutual greeting should be rejected, got %d: %s", sendRec.Code, sendRec.Body.String())
	}
	body := parseJSON(t, sendRec)
	if body["code"] != "USER.GREETING.already_contact" {
		t.Fatalf("expected mutual greeting code, got %#v", body)
	}
}

func TestGreeting_BlockedSenderRejected(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "gr3_req", "req3")
	createTestProfile(t, "gr3_tgt", "tgt3")
	createTestPersonaFull(t, "gr3_req_p", "gr3_req", "sa_gr3_req", "req3", "default", true)
	createTestPersonaFull(t, "gr3_tgt_p", "gr3_tgt", "sa_gr3_tgt", "tgt3", "default", true)

	doRequest(
		t,
		http.MethodPost,
		"/user/personas/sa_gr3_req/block",
		"",
		authHeadersForPersona("gr3_tgt", "sa_gr3_tgt"),
	)

	sendRec := doRequest(
		t,
		http.MethodPost,
		"/user/greeting-request",
		`{"targetPersonaId":"sa_gr3_tgt","requestMessage":"blocked","source":"profile"}`,
		authHeadersForPersona("gr3_req", "sa_gr3_req"),
	)
	if sendRec.Code != http.StatusForbidden {
		t.Fatalf("blocked greeting should be rejected, got %d: %s", sendRec.Code, sendRec.Body.String())
	}
	body := parseJSON(t, sendRec)
	if body["code"] != "USER.GREETING.target_blocked_sender" {
		t.Fatalf("expected blocked greeting code, got %#v", body)
	}

	var count int
	err := pgPool.QueryRow(context.Background(), `
		SELECT COUNT(*) FROM greeting_requests
		WHERE requester_persona_id = $1 AND target_persona_id = $2`,
		"sa_gr3_req", "sa_gr3_tgt").Scan(&count)
	if err != nil {
		t.Fatalf("query greeting: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected no greeting row, got %d", count)
	}
}
