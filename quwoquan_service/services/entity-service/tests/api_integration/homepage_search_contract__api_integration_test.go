package api_integration

import (
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/testsupport"
)

func TestHomepageSearchUsesCanonicalSearchSignals(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(testsupport.NewFixtureHomepageService()).Routes(),
	)
	defer server.Close()

	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":        "四川旅游主页",
		"subtitle":     "川西旅行露营攻略和实体信息",
		"homepageType": "sight",
		"city":         "成都",
		"address":      "川西环线",
		"categoryTags": []string{"旅行", "露营", "攻略"},
	}, http.StatusCreated)
	homepageID := stringField(t, candidate, "homepageId")
	requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
	)

	search := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query=scly&status=published",
		nil,
		http.StatusOK,
	)
	items := sliceField(t, search, "items")
	if len(items) == 0 {
		t.Fatalf("expected pinyin-initial homepage hit")
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("expected object item, got %T", items[0])
	}
	if first["homepageId"] != homepageID {
		t.Fatalf("expected homepage %s, got %#v", homepageID, first)
	}

	search = requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query=出行&status=published",
		nil,
		http.StatusOK,
	)
	if len(sliceField(t, search, "items")) == 0 {
		t.Fatalf("expected synonym homepage hit for 出行")
	}
}
