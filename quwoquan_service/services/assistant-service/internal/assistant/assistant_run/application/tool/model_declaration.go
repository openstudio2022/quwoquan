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

// ModelDeclarations 只为 Skill 显式允许且已绑定到当前运行时的工具生成声明。
//
// 空 allowedToolNames 表示工具集为空，不得退化为 Registry 全量开放。当
// Skill package 声明了当前 Registry 未绑定的工具时，保留最小占位交由
// AgentLoop 在首次模型调用前 fail closed；不从全局 canonical catalog 把“已定义”
// 误冒充为“当前运行时可用”。
func (r Registry) ModelDeclarations(allowedToolNames []string) []ModelToolDeclaration {
	if len(allowedToolNames) == 0 {
		return nil
	}
	names := allowedToolNames
	declarations := make([]ModelToolDeclaration, 0, len(names))
	seen := map[string]bool{}
	for _, name := range names {
		if seen[name] {
			continue
		}
		seen[name] = true
		meta, ok := r.Metadata(name)
		if !ok {
			declarations = append(declarations, ModelToolDeclaration{
				Name:       name,
				Parameters: ObjectSchema(nil),
			})
			continue
		}
		declarations = append(declarations, ModelDeclarationFor(meta))
	}
	return declarations
}

// ModelDeclarationFor projects one runtime-bound metadata snapshot into the
// provider-neutral model declaration. Callers must establish runtime
// availability before invoking it; this function never looks up the canonical
// catalog or turns a catalog entry into a runtime binding.
func ModelDeclarationFor(metadata Metadata) ModelToolDeclaration {
	description := metadata.Description
	if description == "" {
		description = metadata.DisplayName
	}
	parameters := modelInputSchema(metadata)
	if parameters == nil {
		parameters = ObjectSchema(nil)
	}
	return ModelToolDeclaration{
		Name:        metadata.ToolName,
		Description: description,
		Parameters:  parameters,
	}
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
