// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001
package api_integration

import (
	"net/http"
	"net/url"
	"testing"
)

func TestContactRelationshipLifecycle_SearchMutualBlockUnblock(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "contact_lifecycle_viewer", "查看者")
	createTestProfile(t, "contact_lifecycle_target", "目标联系人")
	createTestPersonaFull(
		t,
		"contact_lifecycle_viewer_persona",
		"contact_lifecycle_viewer",
		"sa_contact_lifecycle_viewer",
		"查看者",
		"open",
		true,
	)
	createTestPersonaFull(
		t,
		"contact_lifecycle_target_persona",
		"contact_lifecycle_target",
		"sa_contact_lifecycle_target",
		"目标联系人",
		"open",
		true,
	)

	viewerHeaders := authHeadersForPersona(
		"contact_lifecycle_viewer",
		"sa_contact_lifecycle_viewer",
	)
	targetHeaders := authHeadersForPersona(
		"contact_lifecycle_target",
		"sa_contact_lifecycle_target",
	)

	search := doRequest(
		t,
		http.MethodGet,
		"/user/search/social-relations?query="+url.QueryEscape("目标联系人"),
		"",
		viewerHeaders,
	)
	if search.Code != http.StatusOK {
		t.Fatalf("search contact: expected 200, got %d: %s", search.Code, search.Body.String())
	}
	assertSearchItemsContainSubAccount(
		t,
		parseJSON(t, search),
		"sa_contact_lifecycle_target",
	)

	follow := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/sa_contact_lifecycle_target/follow",
		`{"source":"search","clientRequestId":"contact-life-follow-a"}`,
		viewerHeaders,
	)
	if follow.Code != http.StatusOK {
		t.Fatalf("viewer follow: expected 200, got %d: %s", follow.Code, follow.Body.String())
	}
	followBack := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/sa_contact_lifecycle_viewer/follow",
		`{"source":"followers","clientRequestId":"contact-life-follow-b"}`,
		targetHeaders,
	)
	if followBack.Code != http.StatusOK {
		t.Fatalf("target follow back: expected 200, got %d: %s", followBack.Code, followBack.Body.String())
	}

	capability := contactLifecycleCapability(
		t,
		"sa_contact_lifecycle_target",
		viewerHeaders,
	)
	if capability["relationState"] != "mutual" ||
		capability["canCreateDirectConversation"] != true {
		t.Fatalf("expected mutual direct-conversation capability, got %#v", capability)
	}

	block := doRequest(
		t,
		http.MethodPost,
		"/user/sub-accounts/sa_contact_lifecycle_target/block",
		"",
		viewerHeaders,
	)
	if block.Code != http.StatusOK {
		t.Fatalf("block contact: expected 200, got %d: %s", block.Code, block.Body.String())
	}
	blockedCapability := contactLifecycleCapability(
		t,
		"sa_contact_lifecycle_target",
		viewerHeaders,
	)
	if blockedCapability["isBlocked"] != true ||
		blockedCapability["canSendMessage"] == true {
		t.Fatalf("expected blocked contact gate, got %#v", blockedCapability)
	}

	unblock := doRequest(
		t,
		http.MethodDelete,
		"/user/sub-accounts/sa_contact_lifecycle_target/block",
		"",
		viewerHeaders,
	)
	if unblock.Code != http.StatusOK {
		t.Fatalf("unblock contact: expected 200, got %d: %s", unblock.Code, unblock.Body.String())
	}
	restored := contactLifecycleCapability(
		t,
		"sa_contact_lifecycle_target",
		viewerHeaders,
	)
	if restored["isBlocked"] == true || restored["relationState"] != "not_following" {
		t.Fatalf("unblock must not restore follow edges, got %#v", restored)
	}
}

func contactLifecycleCapability(
	t *testing.T,
	targetSubAccountID string,
	headers map[string]string,
) map[string]any {
	t.Helper()
	recorder := doRequest(
		t,
		http.MethodGet,
		"/user/sub-accounts/"+targetSubAccountID+"/relationship/capability",
		"",
		headers,
	)
	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"get relationship capability: expected 200, got %d: %s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
	return parseJSON(t, recorder)
}
