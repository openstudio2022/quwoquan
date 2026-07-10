package application

import (
	"testing"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

// app_search 命中的站内内容类目应汇总为去重的 Topic 维度路径制 tagRef，
// 供 turn.completed 下发并由端侧合成 assistant_interest 行为回流。
func TestCollectEmergedTagsFromAppSearchResults(t *testing.T) {
	result := ReactResult{
		Steps: []ReactStepResult{
			{Tool: ToolExecution{Completed: assistant.ToolUse{Result: map[string]any{
				"results": []any{
					map[string]any{"categoryId": "旅行", "subCategory": "景区"},
					map[string]any{"categoryId": "旅行", "subCategory": "古镇"},
				},
			}}}},
			{Tool: ToolExecution{Completed: assistant.ToolUse{Result: map[string]any{
				"results": []map[string]any{
					{"categoryId": "美食", "subCategory": ""},
				},
			}}}},
		},
	}
	tags := collectEmergedTags(result)
	want := []string{"Topic/旅行", "Topic/景区", "Topic/古镇", "Topic/美食"}
	if len(tags) != len(want) {
		t.Fatalf("emergedTags=%v want %v", tags, want)
	}
	for i := range want {
		if tags[i] != want[i] {
			t.Fatalf("emergedTags[%d]=%q want %q (all=%v)", i, tags[i], want[i], tags)
		}
	}
}

// 没有 app_search results 时不得伪造 emergedTags。
func TestCollectEmergedTagsEmptyWhenNoResults(t *testing.T) {
	result := ReactResult{
		Steps: []ReactStepResult{
			{Tool: ToolExecution{Completed: assistant.ToolUse{Result: map[string]any{
				"summary": "no results key",
			}}}},
		},
	}
	if tags := collectEmergedTags(result); len(tags) != 0 {
		t.Fatalf("expected empty emergedTags, got %v", tags)
	}
}
