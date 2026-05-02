package tool

import (
	"context"
	"fmt"
	"strings"
)

type Request struct {
	ToolName string
	Input    map[string]any
	History  []string
}

type Result struct {
	Output map[string]any
}

type Handler func(context.Context, Request) (Result, error)

type Registry struct {
	metadata map[string]Metadata
	handlers map[string]Handler
}

func NewRegistry() Registry {
	return Registry{metadata: map[string]Metadata{}, handlers: map[string]Handler{}}
}

func (r Registry) IsZero() bool {
	return len(r.metadata) == 0 && len(r.handlers) == 0
}

func (r Registry) Metadata(toolName string) (Metadata, bool) {
	meta, ok := r.metadata[strings.TrimSpace(toolName)]
	return meta, ok
}

func (r Registry) ValidateInput(toolName string, input map[string]any) error {
	meta, ok := r.Metadata(toolName)
	if !ok {
		return fmt.Errorf("tool %q is not registered", toolName)
	}
	return validateKeys(input, meta.RequiredInputKeys, "input")
}

func (r *Registry) Register(meta Metadata, handler Handler) {
	if r.metadata == nil {
		r.metadata = map[string]Metadata{}
	}
	if r.handlers == nil {
		r.handlers = map[string]Handler{}
	}
	r.metadata[meta.ToolName] = meta
	r.handlers[meta.ToolName] = handler
}

func (r Registry) Execute(ctx context.Context, req Request) (Result, error) {
	meta, ok := r.metadata[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q is not registered", req.ToolName)
	}
	if err := validateKeys(req.Input, meta.RequiredInputKeys, "input"); err != nil {
		return Result{}, err
	}
	if err := detectLoop(req.ToolName, req.History, meta.Resilience.LoopDetectionWindow); err != nil {
		return Result{}, err
	}
	handler, ok := r.handlers[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q has no handler", req.ToolName)
	}
	result, err := handler(ctx, req)
	if err != nil {
		return Result{}, err
	}
	if err := validateKeys(result.Output, meta.RequiredOutputKeys, "output"); err != nil {
		return Result{}, err
	}
	return result, nil
}

func validateKeys(values map[string]any, keys []string, label string) error {
	for _, key := range keys {
		if _, ok := values[key]; !ok {
			return fmt.Errorf("tool %s missing required key %q", label, key)
		}
	}
	return nil
}

func detectLoop(toolName string, history []string, window int) error {
	if window <= 0 || len(history) < window {
		return nil
	}
	count := 0
	for i := len(history) - 1; i >= 0 && len(history)-i <= window; i-- {
		if history[i] == toolName {
			count++
		}
	}
	if count >= window {
		return fmt.Errorf("tool %q loop detected", toolName)
	}
	return nil
}

func DefaultRegistry() Registry {
	registry := NewRegistry()
	registry.Register(DefaultMetadata("mock_search"), func(_ context.Context, req Request) (Result, error) {
		return Result{Output: map[string]any{
			"summary": fmt.Sprintf("mock_search 已围绕“%v”返回 2 条模拟线索", req.Input["query"]),
			"items": []map[string]any{
				{"title": "模拟线索 A", "snippet": "用于验证云端 ReAct 工具观察。"},
				{"title": "模拟线索 B", "snippet": "用于验证最终回答可引用工具结果。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "web_search",
		DisplayName:        "网络搜索",
		Description:        "检索公开网络信息的云端工具。M6 使用稳定 fake adapter，不依赖真实外部网络。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "references"},
		Resilience:         DefaultMetadata("web_search").Resilience,
		Recovery:           DefaultMetadata("web_search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"provider": "fake_web_search",
			"summary":  fmt.Sprintf("web_search 已围绕“%s”返回公开信息摘要", query),
			"references": []map[string]any{
				{"title": "公开来源 A", "source": "example.news", "snippet": "用于验证 M6 云端搜索工具。"},
				{"title": "公开来源 B", "source": "example.report", "snippet": "用于验证工具输出 schema。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "search",
		DisplayName:        "统一搜索",
		Description:        "兼容端侧 search 工具的云端统一检索入口。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "references", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("search").Resilience,
		Recovery:           DefaultMetadata("search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"provider":       "fake_unified_search",
			"summary":        fmt.Sprintf("search 已围绕“%s”返回跨来源检索摘要", query),
			"coverage":       0.82,
			"confidence":     0.78,
			"freshnessHours": 12,
			"references": []map[string]any{
				{"title": "综合来源 A", "source": "example.search", "snippet": "用于验证统一搜索工具。"},
				{"title": "综合来源 B", "source": "example.index", "snippet": "用于验证多来源摘要。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "web_fetch",
		DisplayName:        "网页抓取",
		Description:        "抓取指定公开网页并返回可摘要正文。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"provider", "summary", "content", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("web_fetch").Resilience,
		Recovery:           DefaultMetadata("web_fetch").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"provider":       "fake_web_fetch",
			"summary":        fmt.Sprintf("web_fetch 已抓取“%s”的公开页面摘要", query),
			"content":        "模拟网页正文，用于云侧 ReAct 证据消化与引用。",
			"coverage":       0.74,
			"confidence":     0.72,
			"freshnessHours": 24,
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "memory_search",
		DisplayName:        "记忆检索",
		Description:        "检索用户授权范围内的助手记忆与最近上下文。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"summary", "memories", "coverage", "confidence", "freshnessHours"},
		Resilience:         DefaultMetadata("memory_search").Resilience,
		Recovery:           DefaultMetadata("memory_search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"summary":        fmt.Sprintf("memory_search 已围绕“%s”返回授权记忆摘要", query),
			"coverage":       0.68,
			"confidence":     0.7,
			"freshnessHours": 48,
			"memories": []map[string]any{
				{"memoryId": "mem_fake_1", "snippet": "最近关注天气、出行和工作安排。"},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:           "app_search",
		DisplayName:        "应用信息检索",
		Description:        "检索趣我圈站内内容、聊天、圈子和用户对象的云端工具 fake adapter。",
		Placement:          PlacementCloud,
		RequiredInputKeys:  []string{"query"},
		RequiredOutputKeys: []string{"summary", "results"},
		Resilience:         DefaultMetadata("app_search").Resilience,
		Recovery:           DefaultMetadata("app_search").Recovery,
	}, func(_ context.Context, req Request) (Result, error) {
		query := fmt.Sprint(req.Input["query"])
		return Result{Output: map[string]any{
			"summary": fmt.Sprintf("app_search 已围绕“%s”返回站内模拟结果", query),
			"results": []map[string]any{
				{"objectType": "content.post", "title": "站内内容线索", "score": 0.91},
				{"objectType": "circle.group", "title": "相关圈子线索", "score": 0.84},
			},
		}}, nil
	})
	registry.Register(Metadata{
		ToolName:             "app_action",
		DisplayName:          "应用操作",
		Description:          "向端侧提出应用动作 proposal，必须由端侧确认后执行。",
		Placement:            PlacementDeviceAction,
		RequiredInputKeys:    []string{"actionType"},
		RequiresConfirmation: true,
		Resilience:           DefaultMetadata("app_action").Resilience,
		Recovery: RecoveryPolicy{
			Action:             "request_confirmation",
			DisruptionLevel:    "permissionCard",
			UserVisibleSummary: "需要用户确认后执行本机动作",
		},
	}, nil)
	for _, meta := range []Metadata{
		deviceProposalMetadata("scheduler", "日程调度", "向端侧提出日程、待办或提醒 proposal。"),
		deviceProposalMetadata("deep_link", "深链跳转", "向端侧提出打开应用内或外部目标的 proposal。"),
		deviceProposalMetadata("intent_bridge", "意图桥接", "向端侧提出系统 intent 或平台能力 proposal。"),
	} {
		registry.Register(meta, nil)
	}
	return registry
}

func deviceProposalMetadata(toolName, displayName, description string) Metadata {
	meta := DefaultMetadata(toolName)
	meta.DisplayName = displayName
	meta.Description = description
	meta.Placement = PlacementDeviceAction
	meta.RequiredInputKeys = []string{"query"}
	meta.RequiredOutputKeys = nil
	meta.RequiresConfirmation = true
	meta.Recovery = RecoveryPolicy{
		Action:             "request_confirmation",
		DisruptionLevel:    "permissionCard",
		UserVisibleSummary: "需要用户确认后执行本机动作",
	}
	return meta
}
