package application

import (
	"context"

	toolpkg "quwoquan_service/services/assistant-service/internal/application/tool"
)

func testCloudToolRegistry() toolpkg.Registry {
	registry := toolpkg.BaseRegistry()
	registry.Register(toolpkg.WebSearchMetadata(), func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{Output: map[string]any{
			"provider":   "test_web_provider",
			"summary":    "测试网络检索结果",
			"references": []map[string]any{},
		}}, nil
	})
	registry.Register(toolpkg.AppSearchMetadata(), func(
		context.Context,
		toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{Output: map[string]any{
			"provider":  "test_search_service",
			"summary":   "测试站内检索结果",
			"results":   []map[string]any{},
			"citations": []map[string]any{},
			"provenance": map[string]any{
				"provider": "test_search_service",
			},
		}}, nil
	})
	return registry
}
