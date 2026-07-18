package api_integration

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

	listRec := doRequest(t, http.MethodGet, "/circles?limit=100", nil)
	if listRec.Code != http.StatusOK {
		t.Fatalf("circle list expected 200, got %d: %s", listRec.Code, listRec.Body.String())
	}
	listBody := decodeBody(t, listRec)
	assertItemsContainID(t, listBody["items"], "fixture_circle_photo")
	assertItemsContainID(t, listBody["items"], "fixture_circle_travel")

	detailRec := doRequest(t, http.MethodGet, "/circles/fixture_circle_photo", nil)
	if detailRec.Code != http.StatusOK {
		t.Fatalf("circle detail expected 200, got %d: %s", detailRec.Code, detailRec.Body.String())
	}
	detailBody := decodeBody(t, detailRec)
	data, ok := detailBody["data"].(map[string]any)
	if !ok || data["id"] != "fixture_circle_photo" {
		t.Fatalf("unexpected circle detail: %+v", detailBody)
	}

	groupRec := executeGroupQuery(t, "/circles/fixture_circle_photo/groups?limit=20", "fixture_user_owner", "ListCircleGroups")
	if groupRec.Code != http.StatusOK {
		t.Fatalf("circle groups expected 200, got %d: %s", groupRec.Code, groupRec.Body.String())
	}
	groupBody := decodeBody(t, groupRec)
	assertItemsContainID(t, groupBody["items"], "fixture_group_photo_public")

	memberRec := doRequest(t, http.MethodGet, "/circles/fixture_circle_photo/memberships?limit=20", nil)
	if memberRec.Code != http.StatusOK {
		t.Fatalf("circle members expected 200, got %d: %s", memberRec.Code, memberRec.Body.String())
	}
	memberBody := decodeBody(t, memberRec)
	assertItemsContainPersonaID(t, memberBody["items"], "fixture_user_owner")
	assertItemsContainPersonaID(t, memberBody["items"], "fixture_user_photo")

	fileRec := executeFileQuery(t, "/circles/fixture_circle_photo/files?groupId=fixture_group_photo_public&limit=20", "fixture_user_owner", "ListCircleFiles")
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
		if obj["id"] == id || obj["fileId"] == id || obj["circleId"] == id || obj["groupId"] == id {
			return
		}
	}
	t.Fatalf("items did not contain id %s: %+v", id, items)
}

func assertItemsContainPersonaID(t *testing.T, raw any, personaID string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if ok && obj["personaId"] == personaID {
			return
		}
	}
	t.Fatalf("items did not contain Persona %s: %+v", personaID, items)
}
