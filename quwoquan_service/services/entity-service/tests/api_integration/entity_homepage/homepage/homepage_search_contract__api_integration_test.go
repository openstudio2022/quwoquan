// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-003
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
)

// 真实 Mongo 读端的 /homepages/search 走 $text 全文索引；拼音首字母与同义词
// 扩展信号只存在于 rtsearch（memory reader / 搜索投影链路），不属于本端点的
// 真实存储行为，因此这里只断言真实可证的全文命中与 published 过滤。
func TestHomepageSearchFindsPublishedHomepageByTitleText(t *testing.T) {
	service := newRealMongoHomepageService(t, "entity_homepage_search_contract_it")
	server := httptest.NewServer(httpadapter.NewHandler(service).Routes())
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

	// 未发布候选不得进入公开搜索结果。
	search := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query=四川旅游主页&status=published",
		nil,
		http.StatusOK,
	)
	if items := sliceField(t, search, "items"); len(items) != 0 {
		t.Fatalf("candidate must not appear in published search, got %#v", items)
	}

	requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages/candidates/"+homepageID+":publish",
		nil,
		http.StatusOK,
	)

	search = requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query=四川旅游主页&status=published",
		nil,
		http.StatusOK,
	)
	items := sliceField(t, search, "items")
	if len(items) == 0 {
		t.Fatalf("expected published homepage text hit")
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("expected object item, got %T", items[0])
	}
	if first["homepageId"] != homepageID {
		t.Fatalf("expected homepage %s, got %#v", homepageID, first)
	}
}
