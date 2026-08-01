package tool

import (
	"encoding/json"
	"sort"
)

// ModelToolDeclaration 是工具注册表向模型层暴露的最小形状。它不引用 application 包，
// 避免 application 与其子包互相依赖。
type ModelToolDeclaration struct {
	Name        string
	Description string
	Parameters  map[string]any
}

// Names 返回注册表已登记的工具名，按字典序稳定输出。
func (r Registry) Names() []string {
	names := make([]string, 0, len(r.metadata))
	for name := range r.metadata {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// ModelDeclarations 只为允许集合内且已登记的工具生成声明。未登记的工具名被静默丢弃，
// 保证模型看到的工具一定可执行。
func (r Registry) ModelDeclarations(allowedToolNames []string) []ModelToolDeclaration {
	names := allowedToolNames
	if len(names) == 0 {
		names = r.Names()
	}
	declarations := make([]ModelToolDeclaration, 0, len(names))
	seen := map[string]bool{}
	for _, name := range names {
		if seen[name] {
			continue
		}
		meta, ok := r.Metadata(name)
		if !ok {
			continue
		}
		seen[name] = true
		description := meta.Description
		if description == "" {
			description = meta.DisplayName
		}
		parameters := modelInputSchema(meta)
		if parameters == nil {
			parameters = ObjectSchema(nil)
		}
		declarations = append(declarations, ModelToolDeclaration{
			Name:        meta.ToolName,
			Description: description,
			Parameters:  parameters,
		})
	}
	return declarations
}

func modelInputSchema(metadata Metadata) map[string]any {
	payload, err := json.Marshal(metadata.InputSchema)
	if err != nil {
		panic("encode generated assistant tool input schema: " + err.Error())
	}
	var schema map[string]any
	if err := json.Unmarshal(payload, &schema); err != nil {
		panic("clone generated assistant tool input schema: " + err.Error())
	}
	properties, _ := schema["properties"].(map[string]any)
	removed := map[string]bool{}
	for _, field := range metadata.ServerInjectedInputs {
		delete(properties, field)
		removed[field] = true
	}
	required, _ := schema["required"].([]any)
	filtered := make([]any, 0, len(required))
	for _, value := range required {
		field, _ := value.(string)
		if !removed[field] {
			filtered = append(filtered, value)
		}
	}
	schema["required"] = filtered
	return schema
}
