// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
// spec_ref: specs/feature-tree/assistant-run-learning/spec.md
package assistant_run

import (
	"context"
	"errors"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
)

// intersection.read_mine domain_reader 契约：
// - readiness 由真实 binding 决定：未就绪时工具留在 unavailable 侧（fail-closed）；
// - handler 只透传云侧主句与授权范围内交集事实，输出字段与 canonical
//   outputSchema 闭集一致；
// - persona 缺失 / limit 非法 / 上游失败一律结构化失败，禁止空列表冒充成功。

type recordingMyIntersectionsReader struct {
	lastPersona string
	lastQuery   tool.MyIntersectionsQuery
	items       []tool.MyIntersectionItem
	err         error
}

func (r *recordingMyIntersectionsReader) ListMyIntersections(
	_ context.Context,
	personaID string,
	query tool.MyIntersectionsQuery,
) ([]tool.MyIntersectionItem, error) {
	r.lastPersona = personaID
	r.lastQuery = query
	if r.err != nil {
		return nil, r.err
	}
	return r.items, nil
}

func TestReadMineStaysUnavailableWithoutRealBinding(t *testing.T) {
	unavailable := tool.UnavailableCanonicalBindings(tool.RuntimeAvailability{})
	binding, found := unavailable["intersection.read_mine"]
	if !found {
		t.Fatal("read_mine must stay unavailable without a real binding")
	}
	if binding.BindingKind != "domain_reader" ||
		!strings.Contains(binding.Reason, "intersection_reader_binding_not_ready") {
		t.Fatalf("unexpected unavailable binding: %+v", binding)
	}

	ready := tool.UnavailableCanonicalBindings(tool.RuntimeAvailability{
		IntersectionReaderReady: true,
	})
	if _, still := ready["intersection.read_mine"]; still {
		t.Fatal("ready binding must remove read_mine from the unavailable side")
	}
}

func TestReadMineHandlerProjectsAuthorizedIntersections(t *testing.T) {
	reader := &recordingMyIntersectionsReader{
		items: []tool.MyIntersectionItem{{
			IntersectionID:    "ix-1",
			IntersectionClass: "fact",
			Kind:              "coWishlisted",
			Dimension:         "place",
			ObjectKind:        "person",
			DisplayName:       "林清越",
			PrimaryText:       "你和林清越都想去顶峰公园",
			Strength:          0.8,
			FreshAt:           "2026-08-10T00:00:00Z",
			ActionKeys:        []string{"start_gathering"},
		}},
	}
	handler, err := tool.NewIntersectionReadMineHandler(reader)
	if err != nil {
		t.Fatalf("handler: %v", err)
	}
	result, err := handler(context.Background(), tool.Request{
		ToolName:  "intersection.read_mine",
		PersonaID: "persona-me",
		Input: map[string]any{
			"limit":     float64(10),
			"dimension": "place",
		},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if reader.lastPersona != "persona-me" {
		t.Fatalf("reader must receive the run persona: %q", reader.lastPersona)
	}
	if reader.lastQuery.Limit != 10 || reader.lastQuery.Dimension != "place" {
		t.Fatalf("query must pass through: %+v", reader.lastQuery)
	}
	intersections, ok := result.Output["intersections"].([]map[string]any)
	if !ok || len(intersections) != 1 {
		t.Fatalf("unexpected output shape: %+v", result.Output)
	}
	item := intersections[0]
	if item["primaryText"] != "你和林清越都想去顶峰公园" ||
		item["objectKind"] != "person" ||
		item["intersectionId"] != "ix-1" {
		t.Fatalf("projection must transparently carry cloud facts: %+v", item)
	}
	keys, ok := item["actionKeys"].([]string)
	if !ok || len(keys) != 1 || keys[0] != "start_gathering" {
		t.Fatalf("action keys must project: %+v", item["actionKeys"])
	}
}

func TestReadMineHandlerFailsClosed(t *testing.T) {
	reader := &recordingMyIntersectionsReader{}
	handler, err := tool.NewIntersectionReadMineHandler(reader)
	if err != nil {
		t.Fatalf("handler: %v", err)
	}

	// persona 缺失。
	if _, err := handler(context.Background(), tool.Request{
		Input: map[string]any{"limit": float64(5)},
	}); err == nil || !strings.Contains(err.Error(), "run_unauthorized") {
		t.Fatalf("missing persona must fail closed: %v", err)
	}

	// limit 缺失与越界。
	for _, input := range []map[string]any{
		{},
		{"limit": float64(0)},
		{"limit": float64(51)},
		{"limit": "ten"},
	} {
		if _, err := handler(context.Background(), tool.Request{
			PersonaID: "persona-me",
			Input:     input,
		}); err == nil || !strings.Contains(err.Error(), "run_invalid_argument") {
			t.Fatalf("invalid limit %v must fail closed: %v", input, err)
		}
	}

	// 上游失败结构化不可用，不返回空列表成功。
	reader.err = errors.New("content unavailable")
	if _, err := handler(context.Background(), tool.Request{
		PersonaID: "persona-me",
		Input:     map[string]any{"limit": float64(5)},
	}); err == nil ||
		!errors.Is(err, tool.ErrIntersectionReadMineUnavailable) {
		t.Fatalf("upstream failure must map to structured unavailable: %v", err)
	}

	// nil reader 是装配错误。
	if _, err := tool.NewIntersectionReadMineHandler(nil); err == nil {
		t.Fatal("nil reader must be a composition error")
	}
}
