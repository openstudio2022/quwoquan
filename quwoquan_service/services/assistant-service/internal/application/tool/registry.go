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

// BaseRegistry 只登记无需外部数据源的设备动作 proposal。
//
// 检索类工具必须由 composition root 显式绑定真实 adapter；这里不得提供合成文档、
// fixture 或失败后伪成功，否则引用会把测试数据冒充为事实。
func BaseRegistry() Registry {
	registry := NewRegistry()
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
