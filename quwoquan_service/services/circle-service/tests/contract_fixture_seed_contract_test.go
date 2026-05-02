package tests

import (
	"net/http"
	"testing"
)

func TestContractFixtureSeed_CircleAlphaReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanCollections(t) })
	evidence := seedCircleContractFixture(t, "circle_core")
	if evidence.InsertedCount < 8 {
		t.Fatalf("expected seeded circle records, got %d", evidence.InsertedCount)
	}

	listRec := doRequest(t, http.MethodGet, "/v1/circles?limit=20", nil)
	if listRec.Code != http.StatusOK {
		t.Fatalf("circle list expected 200, got %d: %s", listRec.Code, listRec.Body.String())
	}
	listBody := decodeBody(t, listRec)
	assertItemsContainID(t, listBody["items"], "fixture_circle_photo")
	assertItemsContainID(t, listBody["items"], "fixture_circle_travel")

	detailRec := doRequest(t, http.MethodGet, "/v1/circles/fixture_circle_photo", nil)
	if detailRec.Code != http.StatusOK {
		t.Fatalf("circle detail expected 200, got %d: %s", detailRec.Code, detailRec.Body.String())
	}
	detailBody := decodeBody(t, detailRec)
	data, ok := detailBody["data"].(map[string]any)
	if !ok || data["_id"] != "fixture_circle_photo" {
		t.Fatalf("unexpected circle detail: %+v", detailBody)
	}

	groupRec := doRequest(t, http.MethodGet, "/v1/circles/fixture_circle_photo/groups?limit=20", nil)
	if groupRec.Code != http.StatusOK {
		t.Fatalf("circle groups expected 200, got %d: %s", groupRec.Code, groupRec.Body.String())
	}
	groupBody := decodeBody(t, groupRec)
	assertItemsContainID(t, groupBody["items"], "fixture_group_photo_public")

	memberRec := doRequest(t, http.MethodGet, "/v1/circles/fixture_circle_photo/members?limit=20", nil)
	if memberRec.Code != http.StatusOK {
		t.Fatalf("circle members expected 200, got %d: %s", memberRec.Code, memberRec.Body.String())
	}
	memberBody := decodeBody(t, memberRec)
	assertItemsContainUserID(t, memberBody["items"], "fixture_user_owner")
	assertItemsContainUserID(t, memberBody["items"], "fixture_user_current")

	fileRec := doRequest(t, http.MethodGet, "/v1/circles/fixture_circle_photo/files?limit=20", nil)
	if fileRec.Code != http.StatusOK {
		t.Fatalf("circle files expected 200, got %d: %s", fileRec.Code, fileRec.Body.String())
	}
	fileBody := decodeBody(t, fileRec)
	assertItemsContainID(t, fileBody["items"], "fixture_file_photo_guide")
}

func assertItemsContainID(t *testing.T, raw any, id string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if obj["id"] == id || obj["_id"] == id || obj["circleId"] == id || obj["groupId"] == id {
			return
		}
	}
	t.Fatalf("items did not contain id %s: %+v", id, items)
}

func assertItemsContainUserID(t *testing.T, raw any, userID string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if ok && obj["userId"] == userID {
			return
		}
	}
	t.Fatalf("items did not contain user %s: %+v", userID, items)
}
