package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// seedLaunchSubset 导入首发（校园+旅游）只读子集，对齐 service.yaml contract_test。
func seedLaunchSubset(t *testing.T) {
	t.Helper()
	cleanCollections(t)
	ctx := context.Background()
	nodes := []*model.TagNode{
		{TagRef: "Topic/旅行", Group: "Topic", Label: "旅行", LabelEn: "Travel"},
		{TagRef: "Topic/摄影", Group: "Topic", Label: "摄影", LabelEn: "Photography"},
		{TagRef: "Topic/美食餐饮", Group: "Topic", Label: "美食餐饮", LabelEn: "Food"},
		{TagRef: "Entity/机构/学校/北京大学", Group: "Entity", Label: "北京大学", LabelEn: "Peking University"},
	}
	for _, n := range nodes {
		if _, err := tagNodeStore.Create(ctx, n); err != nil {
			t.Fatalf("seed tag_node %s: %v", n.TagRef, err)
		}
	}
	objs := []*model.ObjectTagIndex{
		{ObjectID: "u1", ObjectType: "user", TagRefs: []string{"Topic/旅行", "Topic/摄影", "Entity/机构/学校/北京大学"}},
		{ObjectID: "u2", ObjectType: "user", TagRefs: []string{"Topic/摄影", "Entity/机构/学校/北京大学"}},
		{ObjectID: "p1", ObjectType: "post", TagRefs: []string{"Topic/旅行"}},
	}
	for _, o := range objs {
		if _, err := objStore.Create(ctx, o); err != nil {
			t.Fatalf("seed object_tag_index %s: %v", o.ObjectID, err)
		}
	}
}

// T3：resolve 返回首发子集 tagRef 定义（tagref_resolvable）。
func TestResolveReturnsDefinition(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/resolve?tagRef=Topic/旅行", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var view struct {
		TagRef string `json:"tagRef"`
		Label  string `json:"label"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if view.TagRef != "Topic/旅行" || view.Label == "" {
		t.Fatalf("expected resolvable Topic/旅行 with label, got %+v", view)
	}
}

func TestResolveUnknownReturns404(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/resolve?tagRef=Topic/不存在", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown tagRef, got %d", rec.Code)
	}
}

func TestListDimensions(t *testing.T) {
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/dimensions", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var dims []struct {
		Group       string `json:"group"`
		DimensionID string `json:"dimensionId"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &dims); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(dims) != 18 {
		t.Fatalf("expected 18 dimensions, got %d", len(dims))
	}
	if dims[0].Group != "Topic" || dims[0].DimensionID != "Topic/主题" {
		t.Fatalf("unexpected first dimension: %+v", dims[0])
	}
}

func TestSuggestTags(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/suggest?q=旅", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var suggestions []struct {
		TagRef     string `json:"tagRef"`
		Label      string `json:"label"`
		MatchField string `json:"matchField"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &suggestions); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(suggestions) != 1 {
		t.Fatalf("expected 1 suggestion, got %d: %+v", len(suggestions), suggestions)
	}
	if suggestions[0].TagRef != "Topic/旅行" || suggestions[0].MatchField != "label" {
		t.Fatalf("unexpected suggestion: %+v", suggestions[0])
	}
}

func TestValidateTagRefs(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/tag/validate", bytes.NewBufferString(`{"tagRefs":["Topic/旅行","Topic/不存在"]}`))
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var view struct {
		Valid   []string `json:"valid"`
		Invalid []string `json:"invalid"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(view.Valid) != 1 || view.Valid[0] != "Topic/旅行" {
		t.Fatalf("unexpected valid set: %+v", view.Valid)
	}
	if len(view.Invalid) != 1 || view.Invalid[0] != "Topic/不存在" {
		t.Fatalf("unexpected invalid set: %+v", view.Invalid)
	}
}

// T3：shared-tags 交集正确性（shared ⊆ both objects' tagRefs，可 resolve）。
func TestSharedTagsTwoObjects(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet,
		"/v1/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var shared []struct {
		TagRef string `json:"tagRef"`
		Label  string `json:"label"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &shared); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// u1∩u2 = {摄影, 北京大学}
	if len(shared) != 2 {
		t.Fatalf("expected 2 shared, got %d: %+v", len(shared), shared)
	}
	for _, s := range shared {
		if s.Label == "" {
			t.Fatalf("shared tag %s not enriched (resolvable)", s.TagRef)
		}
	}
}

// T3：inverted 返回引用某 tagRef 的对象。
func TestInvertedObjects(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/inverted?tagRef=Topic/摄影", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var view struct {
		TagRef      string   `json:"tagRef"`
		ObjectCount int      `json:"objectCount"`
		ObjectIds   []string `json:"objectIds"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if view.ObjectCount != 2 {
		t.Fatalf("expected 2 objects referencing Topic/摄影, got %d: %+v", view.ObjectCount, view.ObjectIds)
	}
}

// inverted 按 objectType 过滤。
func TestInvertedFilterByType(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/inverted?tagRef=Topic/旅行&objectType=post", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var view struct {
		ObjectCount int      `json:"objectCount"`
		ObjectIds   []string `json:"objectIds"`
	}
	json.Unmarshal(rec.Body.Bytes(), &view)
	if view.ObjectCount != 1 || view.ObjectIds[0] != "p1" {
		t.Fatalf("expected only p1 for Topic/旅行 post, got %+v", view.ObjectIds)
	}
}

// 保留契约端点显式 501（不留静默 404）。
func TestReservedEndpointsReturn501(t *testing.T) {
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/search?q=旅", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("expected 501 for reserved endpoint, got %d", rec.Code)
	}
}
