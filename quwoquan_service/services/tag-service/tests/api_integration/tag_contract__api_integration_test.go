package api_integration

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
		tagNode("Topic/旅行", "旅行", "Travel"),
		tagNode("Topic/摄影", "摄影", "Photography"),
		tagNode("Topic/美食餐饮", "美食餐饮", "Food"),
		tagNode("Entity/机构/学校/北京大学", "北京大学", "Peking University"),
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

func tagNode(tagRef, label, labelEn string) *model.TagNode {
	parentTagRef := ""
	parts := bytes.Split([]byte(tagRef), []byte("/"))
	if len(parts) > 1 {
		parentTagRef = string(bytes.Join(parts[:len(parts)-1], []byte("/")))
	}
	return &model.TagNode{
		TagRef:          tagRef,
		Group:           string(parts[0]),
		Label:           label,
		DisplayLabel:    label,
		LabelEn:         labelEn,
		ParentTagRef:    parentTagRef,
		Depth:           len(parts) - 1,
		ReleaseID:       "test-release",
		LifecycleStatus: "active",
	}
}

func seedAdminRegionSubset(t *testing.T) {
	t.Helper()
	cleanCollections(t)
	ctx := context.Background()
	nodes := []*model.TagNode{
		tagNode("Topic/地理", "地理", "Geography"),
		tagNode("Topic/地理/行政区", "行政区", "Administrative Region"),
		tagNode("Topic/地理/行政区/中国", "中国", "China"),
	}
	for _, label := range []string{
		"北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省",
		"上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省",
		"湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省", "重庆市", "四川省", "贵州省",
		"云南省", "西藏自治区", "陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
		"香港特别行政区", "澳门特别行政区", "台湾省",
	} {
		n := tagNode("Topic/地理/行政区/中国/"+label, label, "")
		n.DisplayLabel = displayLabelForTest(label)
		nodes = append(nodes, n)
	}
	for _, label := range []string{
		"广州市", "深圳市", "珠海市", "汕头市", "佛山市", "韶关市", "湛江市", "肇庆市", "江门市", "茂名市",
		"惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市", "东莞市", "中山市", "潮州市", "揭阳市", "云浮市",
	} {
		n := tagNode("Topic/地理/行政区/中国/广东省/"+label, label, "")
		n.DisplayLabel = displayLabelForTest(label)
		nodes = append(nodes, n)
	}
	for _, label := range []string{
		"东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "门头沟区", "房山区",
		"通州区", "顺义区", "昌平区", "大兴区", "怀柔区", "平谷区", "密云区", "延庆区",
	} {
		n := tagNode("Topic/地理/行政区/中国/北京市/"+label, label, "")
		n.DisplayLabel = displayLabelForTest(label)
		nodes = append(nodes, n)
	}
	for _, n := range nodes {
		if _, err := tagNodeStore.Create(ctx, n); err != nil {
			t.Fatalf("seed admin tag_node %s: %v", n.TagRef, err)
		}
	}
}

func displayLabelForTest(label string) string {
	switch label {
	case "北京市":
		return "北京"
	case "广东省":
		return "广东"
	}
	for _, suffix := range []string{"市", "区", "省"} {
		if bytes.HasSuffix([]byte(label), []byte(suffix)) {
			return string(bytes.TrimSuffix([]byte(label), []byte(suffix)))
		}
	}
	return label
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

func TestListTagChildrenReturnsDirectAdminRegionChildren(t *testing.T) {
	seedAdminRegionSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/children?parentTagRef=Topic/地理/行政区/中国&limit=500", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var provinces []struct {
		TagRef       string `json:"tagRef"`
		DisplayLabel string `json:"displayLabel"`
		Depth        int    `json:"depth"`
		HasChildren  bool   `json:"hasChildren"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &provinces); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(provinces) != 34 {
		t.Fatalf("expected 34 provincial nodes, got %d", len(provinces))
	}
	foundGuangdong := false
	for _, province := range provinces {
		if province.TagRef == "Topic/地理/行政区/中国/广东省" {
			foundGuangdong = province.DisplayLabel == "广东" && province.Depth == 4 && province.HasChildren
		}
	}
	if !foundGuangdong {
		t.Fatalf("expected Guangdong province child with displayLabel and hasChildren, got %+v", provinces)
	}
}

func TestListTagChildrenGuangdongAndBeijingAreCompleteDirectLevel(t *testing.T) {
	seedAdminRegionSubset(t)
	for _, tc := range []struct {
		name      string
		parentRef string
		wantCount int
		wantRef   string
		wantLabel string
	}{
		{
			name:      "guangdong prefecture cities",
			parentRef: "Topic/地理/行政区/中国/广东省",
			wantCount: 21,
			wantRef:   "Topic/地理/行政区/中国/广东省/深圳市",
			wantLabel: "深圳",
		},
		{
			name:      "beijing districts",
			parentRef: "Topic/地理/行政区/中国/北京市",
			wantCount: 16,
			wantRef:   "Topic/地理/行政区/中国/北京市/朝阳区",
			wantLabel: "朝阳",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, "/v1/tag/children?parentTagRef="+tc.parentRef+"&limit=500", nil)
			testHandler.ServeHTTP(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
			}
			var children []struct {
				TagRef       string `json:"tagRef"`
				DisplayLabel string `json:"displayLabel"`
				ParentTagRef string `json:"parentTagRef"`
			}
			if err := json.Unmarshal(rec.Body.Bytes(), &children); err != nil {
				t.Fatalf("decode: %v", err)
			}
			if len(children) != tc.wantCount {
				t.Fatalf("expected %d children, got %d", tc.wantCount, len(children))
			}
			found := false
			for _, child := range children {
				if child.ParentTagRef != tc.parentRef {
					t.Fatalf("expected direct child parent %s, got %+v", tc.parentRef, child)
				}
				if child.TagRef == tc.wantRef && child.DisplayLabel == tc.wantLabel {
					found = true
				}
			}
			if !found {
				t.Fatalf("expected child %s with label %s, got %+v", tc.wantRef, tc.wantLabel, children)
			}
		})
	}
}

func TestListTagChildrenUnknownParentReturns404(t *testing.T) {
	seedAdminRegionSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/children?parentTagRef=Topic/地理/行政区/中国/不存在", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown parent, got %d: %s", rec.Code, rec.Body.String())
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

// T3：search 全文搜索，命中首发子集并带 score。
func TestSearchTags(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/search?q=旅", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var results []struct {
		TagRef string  `json:"tagRef"`
		Label  string  `json:"label"`
		Score  float64 `json:"score"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &results); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(results) != 1 || results[0].TagRef != "Topic/旅行" {
		t.Fatalf("expected single Topic/旅行 result, got %+v", results)
	}
	if results[0].Score <= 0 {
		t.Fatalf("expected positive score, got %v", results[0].Score)
	}
}

// T3：related 共现度最高的相关标签（u1∩u2 维度）。
func TestRelatedTags(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/related?tagRef=Topic/摄影", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var related []struct {
		TagRef       string `json:"tagRef"`
		Label        string `json:"label"`
		CooccurCount int    `json:"cooccurCount"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &related); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// 摄影出现在 u1{旅行,北大}、u2{北大} → 共现: 北大=2, 旅行=1。
	if len(related) != 2 || related[0].TagRef != "Entity/机构/学校/北京大学" || related[0].CooccurCount != 2 {
		t.Fatalf("expected 北京大学(2) ranked first, got %+v", related)
	}
}

// T3：search-by-tags 多标签联合搜索对象。
func TestSearchByTags(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/tag/search-by-tags",
		bytes.NewBufferString(`{"tagRefs":["Topic/摄影","Entity/机构/学校/北京大学"]}`))
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var matches []struct {
		ObjectID    string   `json:"objectId"`
		MatchedTags []string `json:"matchedTags"`
		Score       float64  `json:"score"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &matches); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// u1、u2 都含两标签 → score=1.0。
	if len(matches) != 2 {
		t.Fatalf("expected 2 matched objects, got %d: %+v", len(matches), matches)
	}
	if matches[0].Score != 1.0 || len(matches[0].MatchedTags) != 2 {
		t.Fatalf("expected full match score 1.0, got %+v", matches[0])
	}
}

// T3：cooccurrence 共现图谱（>= minCount）。
func TestTagCooccurrence(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/graph/cooccurrence?tagRef=Topic/摄影&minCount=2", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var pairs []struct {
		TagA         string `json:"tagA"`
		TagB         string `json:"tagB"`
		CooccurCount int    `json:"cooccurCount"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &pairs); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// minCount=2 → 只有 (摄影, 北大, 2)。
	if len(pairs) != 1 || pairs[0].TagB != "Entity/机构/学校/北京大学" || pairs[0].CooccurCount != 2 {
		t.Fatalf("expected single (摄影,北大,2) pair, got %+v", pairs)
	}
}

// T3：related-objects 通过共享标签查找相关对象。
func TestRelatedObjects(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tag/related-objects?objectId=u1&objectType=user", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var related []struct {
		ObjectID    string   `json:"objectId"`
		SharedTags  []string `json:"sharedTags"`
		SharedCount int      `json:"sharedCount"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &related); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// u1{旅行,摄影,北大} → u2 共享{摄影,北大}=2, p1 共享{旅行}=1。
	if len(related) != 2 || related[0].ObjectID != "u2" || related[0].SharedCount != 2 {
		t.Fatalf("expected u2 shared(2) ranked first, got %+v", related)
	}
}
