package skill

import (
	"context"
	"fmt"
	"sync"
)

// ToolHandler is the actual function behind a tool.
type ToolHandler func(ctx context.Context, input map[string]any) (map[string]any, error)

// ToolRegistry manages tool definitions and their handlers.
type ToolRegistry struct {
	mu       sync.RWMutex
	tools    map[string]Tool
	handlers map[string]ToolHandler
}

func NewToolRegistry() *ToolRegistry {
	return &ToolRegistry{
		tools:    make(map[string]Tool),
		handlers: make(map[string]ToolHandler),
	}
}

// RegisterTool adds a tool definition with its handler.
func (r *ToolRegistry) RegisterTool(tool Tool, handler ToolHandler) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tools[tool.ID] = tool
	r.handlers[tool.ID] = handler
}

// GetTool returns a tool by ID.
func (r *ToolRegistry) GetTool(id string) (Tool, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	t, ok := r.tools[id]
	return t, ok
}

// AvailableForPage returns tools applicable to a given page type.
func (r *ToolRegistry) AvailableForPage(pageType string) []Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var result []Tool
	for _, t := range r.tools {
		if len(t.PageTypes) == 0 || containsStr(t.PageTypes, pageType) {
			result = append(result, t)
		}
	}
	return result
}

// Call invokes a tool's handler.
func (r *ToolRegistry) Call(ctx context.Context, toolID string, input map[string]any) (map[string]any, error) {
	r.mu.RLock()
	handler, ok := r.handlers[toolID]
	r.mu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("tool %q not registered", toolID)
	}
	return handler(ctx, input)
}

// AllTools returns all registered tools.
func (r *ToolRegistry) AllTools() []Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	result := make([]Tool, 0, len(r.tools))
	for _, t := range r.tools {
		result = append(result, t)
	}
	return result
}

// guardedToolProxy enforces DataClassMax when a skill calls tools.
type guardedToolProxy struct {
	registry     *ToolRegistry
	dataClassMax DataClass
	pageType     string
}

func (g *guardedToolProxy) Call(ctx context.Context, toolID string, input map[string]any) (map[string]any, error) {
	tool, ok := g.registry.GetTool(toolID)
	if !ok {
		return nil, fmt.Errorf("tool %q not found", toolID)
	}

	if !dataClassAllowed(g.dataClassMax, tool.DataClassMax) {
		return nil, fmt.Errorf("%w: skill max=%s, tool requires=%s", ErrDataClassDenied, g.dataClassMax, tool.DataClassMax)
	}

	return g.registry.Call(ctx, toolID, input)
}

func (g *guardedToolProxy) Available(ctx context.Context, pageType string) []Tool {
	all := g.registry.AvailableForPage(pageType)
	var allowed []Tool
	for _, t := range all {
		if dataClassAllowed(g.dataClassMax, t.DataClassMax) {
			allowed = append(allowed, t)
		}
	}
	return allowed
}

var classLevel = map[DataClass]int{
	DataClassPublic:    1,
	DataClassPII:       2,
	DataClassSensitive: 3,
}

// dataClassAllowed checks if skillMax >= toolRequired.
func dataClassAllowed(skillMax, toolRequired DataClass) bool {
	return classLevel[skillMax] >= classLevel[toolRequired]
}
