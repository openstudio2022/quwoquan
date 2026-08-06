// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// readiness_case: resolve-tag-api
// readiness_case: list-tag-children-api
// readiness_case: shared-tags-api
// readiness_case: inverted-objects-api
// readiness_case: list-dimensions-api
// readiness_case: suggest-tags-api
// readiness_case: validate-tag-refs-api
// readiness_case: search-tags-api
// readiness_case: related-tags-api
// readiness_case: search-by-tags-api
// readiness_case: tag-cooccurrence-api
// readiness_case: related-objects-api
package api_integration // TagNodeView HTTP contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	indexmodel "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/model"
	indexports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

// seedLaunchSubset 导入首发（校园+旅游）只读子集，对齐 operations.yaml contract_test。
func seedLaunchSubset(t *testing.T) {
	t.Helper()
	cleanCollections(t)
	ctx := context.Background()
	nodes := []*model.TagNode{
		tagNode("Topic", "主题", "Topic"),
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
	activateReleaseForSeed(t, "test-release", len(nodes))
	objs := []*indexmodel.ObjectTagIndex{
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

func seedDimensionSnapshot(t *testing.T) {
	t.Helper()
	cleanCollections(t)
	ctx := context.Background()
	nodes := []*model.TagNode{
		{
			TagRef:          "Entity/机构",
			Group:           "Entity",
			NodeKind:        "dimension",
			Label:           "机构",
			DisplayLabel:    "机构",
			LabelEn:         "Organization",
			ParentTagRef:    "Entity",
			Depth:           1,
			MaxDepth:        2,
			PathPolicy:      "any-depth",
			ReleaseID:       "dimension-release",
			LifecycleStatus: "active",
		},
		{
			TagRef:          "Topic/主题",
			Group:           "Topic",
			NodeKind:        "dimension",
			Label:           "主题垂类",
			DisplayLabel:    "主题垂类",
			LabelEn:         "Topic Vertical",
			ParentTagRef:    "Topic",
			Depth:           1,
			MaxDepth:        4,
			PathPolicy:      "any-depth",
			ReleaseID:       "dimension-release",
			LifecycleStatus: "active",
		},
	}
	for _, node := range nodes {
		if _, err := tagNodeStore.Create(ctx, node); err != nil {
			t.Fatalf("seed dimension %s: %v", node.TagRef, err)
		}
	}
	activateReleaseForSeed(t, "dimension-release", len(nodes))
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
	activateReleaseForSeed(t, "test-release", len(nodes))
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
	req := httptest.NewRequest(http.MethodGet, "/tag/resolve?tagRef=Topic/旅行", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/tag/resolve?tagRef=Topic/不存在", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown tagRef, got %d", rec.Code)
	}
}

func TestListDimensions(t *testing.T) {
	seedDimensionSnapshot(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/tag/dimensions", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var dims []struct {
		Group       string `json:"group"`
		DimensionID string `json:"dimensionId"`
		MaxDepth    int    `json:"maxDepth"`
		PathPolicy  string `json:"pathPolicy"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &dims); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(dims) != 2 {
		t.Fatalf("expected dimensions from active snapshot, got %d", len(dims))
	}
	byID := make(map[string]struct {
		Group       string
		DimensionID string
		MaxDepth    int
		PathPolicy  string
	}, len(dims))
	for _, dimension := range dims {
		byID[dimension.DimensionID] = struct {
			Group       string
			DimensionID string
			MaxDepth    int
			PathPolicy  string
		}{
			Group:       dimension.Group,
			DimensionID: dimension.DimensionID,
			MaxDepth:    dimension.MaxDepth,
			PathPolicy:  dimension.PathPolicy,
		}
	}
	if got, ok := byID["Topic/主题"]; !ok ||
		got.Group != "Topic" || got.MaxDepth != 4 || got.PathPolicy != "any-depth" {
		t.Fatalf("missing Topic dimension from active snapshot: %+v", dims)
	}
	if got, ok := byID["Entity/机构"]; !ok ||
		got.Group != "Entity" || got.MaxDepth != 2 || got.PathPolicy != "any-depth" {
		t.Fatalf("missing Entity dimension from active snapshot: %+v", dims)
	}
}

func TestListTagChildrenReturnsDirectAdminRegionChildren(t *testing.T) {
	seedAdminRegionSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/tag/children?parentTagRef=Topic/地理/行政区/中国&limit=500", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var response struct {
		Items []struct {
			TagRef       string `json:"tagRef"`
			DisplayLabel string `json:"displayLabel"`
			Depth        int    `json:"depth"`
			HasChildren  bool   `json:"hasChildren"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode: %v", err)
	}
	provinces := response.Items
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
			req := httptest.NewRequest(http.MethodGet, "/tag/children?parentTagRef="+tc.parentRef+"&limit=500", nil)
			testHandler.ServeHTTP(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
			}
			var response struct {
				Items []struct {
					TagRef       string `json:"tagRef"`
					DisplayLabel string `json:"displayLabel"`
					ParentTagRef string `json:"parentTagRef"`
				} `json:"items"`
			}
			if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
				t.Fatalf("decode: %v", err)
			}
			children := response.Items
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
	req := httptest.NewRequest(http.MethodGet, "/tag/children?parentTagRef=Topic/地理/行政区/中国/不存在", nil)
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown parent, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestSuggestTags(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/tag/suggest?q=旅", nil)
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
	req := httptest.NewRequest(http.MethodPost, "/tag/validate", bytes.NewBufferString(`{"expectedTaxonomyReleaseId":"test-release","tagRefs":["Topic/旅行","Topic/不存在"]}`))
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var view struct {
		TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
		Valid             []string `json:"valid"`
		Invalid           []string `json:"invalid"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(view.Valid) != 1 || view.Valid[0] != "Topic/旅行" {
		t.Fatalf("unexpected valid set: %+v", view.Valid)
	}
	if view.TaxonomyReleaseID != "test-release" {
		t.Fatalf("taxonomy release = %q, want test-release", view.TaxonomyReleaseID)
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
		"/internal/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/internal/tag/inverted?tagRef=Topic/摄影", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/internal/tag/inverted?tagRef=Topic/旅行&objectType=post", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/tag/search?q=旅", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/internal/tag/related?tagRef=Topic/摄影", nil)
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
	req := httptest.NewRequest(http.MethodPost, "/internal/tag/search-by-tags",
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

func TestObjectTagQueriesPreserveCompositeObjectIdentity(t *testing.T) {
	seedLaunchSubset(t)
	if _, err := objStore.Create(t.Context(), &indexmodel.ObjectTagIndex{
		ObjectID:   "u1",
		ObjectType: "post",
		TagRefs: []string{
			"Topic/摄影",
			"Entity/机构/学校/北京大学",
		},
	}); err != nil {
		t.Fatal(err)
	}

	searchRecorder := httptest.NewRecorder()
	searchRequest := httptest.NewRequest(
		http.MethodPost,
		"/internal/tag/search-by-tags",
		bytes.NewBufferString(
			`{"tagRefs":["Topic/摄影","Entity/机构/学校/北京大学"]}`,
		),
	)
	testHandler.ServeHTTP(searchRecorder, searchRequest)
	if searchRecorder.Code != http.StatusOK {
		t.Fatalf(
			"search status=%d body=%s",
			searchRecorder.Code,
			searchRecorder.Body.String(),
		)
	}
	var matches []struct {
		ObjectID   string `json:"objectId"`
		ObjectType string `json:"objectType"`
	}
	if err := json.Unmarshal(searchRecorder.Body.Bytes(), &matches); err != nil {
		t.Fatal(err)
	}
	identities := map[string]bool{}
	for _, match := range matches {
		identities[match.ObjectType+"\x00"+match.ObjectID] = true
	}
	if !identities["user\x00u1"] || !identities["post\x00u1"] {
		t.Fatalf("composite identities collapsed: %#v", matches)
	}

	relatedRecorder := httptest.NewRecorder()
	relatedRequest := httptest.NewRequest(
		http.MethodGet,
		"/internal/tag/related-objects?objectId=u1&objectType=user",
		nil,
	)
	testHandler.ServeHTTP(relatedRecorder, relatedRequest)
	if relatedRecorder.Code != http.StatusOK {
		t.Fatalf(
			"related status=%d body=%s",
			relatedRecorder.Code,
			relatedRecorder.Body.String(),
		)
	}
	var related []struct {
		ObjectID   string `json:"objectId"`
		ObjectType string `json:"objectType"`
	}
	if err := json.Unmarshal(relatedRecorder.Body.Bytes(), &related); err != nil {
		t.Fatal(err)
	}
	foundPostWithSameID := false
	for _, object := range related {
		if object.ObjectID == "u1" && object.ObjectType == "post" {
			foundPostWithSameID = true
		}
	}
	if !foundPostWithSameID {
		t.Fatalf("related objects dropped post/u1: %#v", related)
	}
}

func TestObjectTagReleaseImportReconcilesWithoutRewritingIdentity(t *testing.T) {
	cleanCollections(t)
	ctx := t.Context()
	for _, objectID := range []string{"keep", "remove"} {
		if err := objStore.UpsertObjectTagsFromRelease(
			ctx,
			objectID,
			"post",
			[]string{"Topic/旅行"},
			"release-1",
			"data-pipeline",
		); err != nil {
			t.Fatal(err)
		}
	}
	if err := objStore.UpsertObjectTagsFromRelease(
		ctx,
		"keep",
		"post",
		[]string{"Topic/摄影"},
		"release-2",
		"data-pipeline",
	); err != nil {
		t.Fatal(err)
	}
	deleted, err := objStore.DeleteSupersededReleaseObjects(
		ctx,
		"data-pipeline",
		"release-2",
	)
	if err != nil || deleted != 1 {
		t.Fatalf("deleted=%d err=%v", deleted, err)
	}
	if removed, err := objStore.FindByObject(ctx, "remove", "post"); err != nil ||
		removed != nil {
		t.Fatalf("superseded object=%#v err=%v", removed, err)
	}

	err = objStore.UpsertObjectTagsFromRelease(
		ctx,
		"keep",
		"post",
		[]string{"Topic/旅行"},
		"release-2",
		"data-pipeline",
	)
	if !errors.Is(err, indexpersistence.ErrReleaseProjectionConflict) {
		t.Fatalf("same release payload rewrite err=%v", err)
	}
	err = objStore.UpsertObjectTagsFromRelease(
		ctx,
		"keep",
		"post",
		[]string{"Topic/摄影"},
		"release-3",
		"another-owner",
	)
	if !errors.Is(err, indexpersistence.ErrReleaseProjectionConflict) {
		t.Fatalf("cross-owner takeover err=%v", err)
	}
}

// T3：cooccurrence 共现图谱（>= minCount）。
func TestTagCooccurrence(t *testing.T) {
	seedLaunchSubset(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/internal/tag/graph/cooccurrence?tagRef=Topic/摄影&minCount=2", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/internal/tag/related-objects?objectId=u1&objectType=user", nil)
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

func TestObjectTagReleaseUpsertKeepsFirstVisibleRelease(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	if err := objStore.UpsertObjectTagsFromRelease(
		ctx,
		"user-release",
		"user",
		[]string{"Topic/摄影"},
		"release-1",
		"qwq_data",
	); err != nil {
		t.Fatalf("upsert first release: %v", err)
	}
	if err := objStore.UpsertObjectTagsFromRelease(
		ctx,
		"user-release",
		"user",
		[]string{"Topic/旅行"},
		"release-2",
		"qwq_data",
	); err != nil {
		t.Fatalf("upsert second release: %v", err)
	}

	index, err := objStore.FindByObject(ctx, "user-release", "user")
	if err != nil {
		t.Fatalf("load release projection: %v", err)
	}
	if index == nil {
		t.Fatal("release projection must exist")
	}
	if index.ReleaseID != "release-2" ||
		index.VisibleFromReleaseID != "release-1" ||
		index.SourceOwner != "qwq_data" ||
		index.LifecycleStatus != "active" {
		t.Fatalf("unexpected release provenance: %+v", index)
	}
	if len(index.TagRefs) != 1 || index.TagRefs[0] != "Topic/旅行" {
		t.Fatalf("latest tags must replace the prior projection: %+v", index.TagRefs)
	}
}

func TestUserProfileTagProjectionConvergesOnHighestSourceVersion(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	occurredAt := time.Date(2026, 7, 24, 10, 0, 0, 0, time.UTC)
	applied, err := objStore.ApplyUserProfileTagProjection(
		ctx,
		indexports.UserProfileTagProjection{
			EventID:           "profile-tags-newer",
			UserID:            "projection-user",
			TagRefs:           []string{"Audience/用户/兴趣偏好/科技/AI"},
			TaxonomyReleaseID: "taxonomy-release-2",
			ProfileVersion:    2,
			OccurredAt:        occurredAt,
		},
	)
	if err != nil || !applied {
		t.Fatalf("apply version 2: applied=%v err=%v", applied, err)
	}
	applied, err = objStore.ApplyUserProfileTagProjection(
		ctx,
		indexports.UserProfileTagProjection{
			EventID:           "profile-tags-stale",
			UserID:            "projection-user",
			TagRefs:           []string{"Audience/用户/兴趣偏好/生活/咖啡"},
			TaxonomyReleaseID: "taxonomy-release-1",
			ProfileVersion:    1,
			OccurredAt:        occurredAt.Add(-time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("replay stale version: %v", err)
	}
	if applied {
		t.Fatal("stale source version must not overwrite the projection")
	}
	var stored struct {
		TagRefs                []string `bson:"tagRefs"`
		TaxonomyReleaseID      string   `bson:"taxonomyReleaseId"`
		SourceAggregateVersion int64    `bson:"sourceAggregateVersion"`
	}
	if err := mongoDB.Collection("object_tag_index").FindOne(
		ctx,
		map[string]any{
			"objectId":   "projection-user",
			"objectType": "user",
		},
	).Decode(&stored); err != nil {
		t.Fatalf("read user profile tag projection: %v", err)
	}
	if stored.SourceAggregateVersion != 2 ||
		stored.TaxonomyReleaseID != "taxonomy-release-2" ||
		len(stored.TagRefs) != 1 ||
		stored.TagRefs[0] != "Audience/用户/兴趣偏好/科技/AI" {
		t.Fatalf("unexpected converged projection: %#v", stored)
	}
}
