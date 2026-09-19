package main

import (
	"fmt"
	"go/token"
	"reflect"
	"sort"
	"strings"
	"unicode"

	"gopkg.in/yaml.v3"
)

// 契约允许共享列表声明及对象局部 {values: [...]} 声明。
type enumDefinitions map[string][]string

func (definitions *enumDefinitions) UnmarshalYAML(node *yaml.Node) error {
	var declarations map[string]yaml.Node
	if err := node.Decode(&declarations); err != nil {
		return err
	}
	result := enumDefinitions{}
	for name, declaration := range declarations {
		var values []string
		if declaration.Kind == yaml.MappingNode {
			var definition struct {
				Values []string `yaml:"values"`
			}
			if err := declaration.Decode(&definition); err != nil {
				return err
			}
			values = definition.Values
		} else if err := declaration.Decode(&values); err != nil {
			return err
		}
		result[name] = values
	}
	*definitions = result
	return nil
}

// 共享枚举仍以契约为唯一来源；只合并声明，不引入手写类型登记表。
func mergeSharedEnums(fields, shared *fieldsFile) error {
	if fields.Enums == nil {
		fields.Enums = map[string][]string{}
	}
	for name, values := range shared.Enums {
		if local, ok := fields.Enums[name]; ok && !reflect.DeepEqual(local, values) {
			return fmt.Errorf("CONTRACT.CODEGEN.ENUM_CONFLICT: %s", name)
		}
		fields.Enums[name] = values
	}
	return nil
}

// 固定输出根也必须遍历共享依赖，但继续忽略原先不输出的缺席根。
func resolveNamedTransportClosure(fields *fieldsFile, names []string) ([]string, error) {
	ops := &operationsFile{}
	for _, name := range names {
		if _, exists := fields.Entities[name]; exists {
			ops.APIRoutes = append(ops.APIRoutes, routeDef{RequestEntity: name})
		}
	}
	if len(ops.APIRoutes) == 0 {
		fields.Order = []string{}
		return fields.Order, nil
	}
	return resolveTransportClosure(fields, fields.Shared, ops)
}

func transportTypeNames(fields *fieldsFile) map[string]bool {
	names := map[string]bool{}
	for name := range fields.Entities {
		names[name] = true
	}
	for name := range fields.Enums {
		names[name] = true
	}
	return names
}

func visitTransportField(fields *fieldsFile, shared map[string]entityDef, field fieldDef, visit func(string) error) error {
	if err := validateEnumReference(fields, shared, field); err != nil {
		return err
	}
	return visit(field.Type)
}

func inlineEnumValues(field fieldDef) bool {
	return field.Type == "enum" && field.EnumRef == "" && len(field.Values) > 0
}

func writeGoEnumImports(b *strings.Builder, fields *fieldsFile, names []string) {
	if len(transportEnums(fields, names)) > 0 {
		b.WriteString("\nimport (\"encoding/json\"; \"fmt\")\n")
	}
}

func enumFieldType(field fieldDef) string {
	if field.EnumRef == "" {
		return field.Type
	}
	return strings.ReplaceAll(field.Type, "enum", field.EnumRef)
}

func validateEnumReference(fields *fieldsFile, shared map[string]entityDef, field fieldDef) error {
	if field.EnumRef == "" {
		return nil
	}
	if base := strings.TrimLeft(strings.TrimSpace(field.Type), "[]"); base != "enum" {
		return fmt.Errorf("CONTRACT.CODEGEN.ENUM_TYPE_INVALID: %s", field.EnumRef)
	}
	values, ok := fields.Enums[field.EnumRef]
	if !ok || len(values) == 0 {
		return fmt.Errorf("CONTRACT.CODEGEN.ENUM_MISSING: %s", field.EnumRef)
	}
	if !token.IsIdentifier(field.EnumRef) || token.Lookup(field.EnumRef).IsKeyword() {
		return fmt.Errorf("CONTRACT.CODEGEN.ENUM_NAME_INVALID: %s", field.EnumRef)
	}
	_, localType := fields.Entities[field.EnumRef]
	_, sharedType := shared[field.EnumRef]
	if localType || sharedType {
		return fmt.Errorf("CONTRACT.CODEGEN.TYPE_CONFLICT: %s", field.EnumRef)
	}
	seen := map[string]bool{}
	for _, value := range values {
		if seen[value] {
			return fmt.Errorf("CONTRACT.CODEGEN.ENUM_VALUE_DUPLICATE: %s", field.EnumRef)
		}
		seen[value] = true
	}
	if len(field.Values) > 0 && !reflect.DeepEqual(field.Values, values) {
		return fmt.Errorf("CONTRACT.CODEGEN.ENUM_CONFLICT: %s", field.EnumRef)
	}
	return nil
}

// names 已是所选根的类型闭包；每个模块只输出可达枚举一次。
func transportEnums(fields *fieldsFile, names []string) []string {
	seen := map[string]bool{}
	for _, name := range names {
		for _, field := range fields.Entities[name].Fields {
			if field.EnumRef != "" {
				seen[field.EnumRef] = true
			}
		}
	}
	result := make([]string, 0, len(seen))
	for name := range seen {
		result = append(result, name)
	}
	sort.Strings(result)
	return result
}

// 常规 wire 值生成可读常量；归一化碰撞时整组改用无歧义编码。
func enumMemberNames(name string, values []string, python bool) []string {
	result := make([]string, len(values))
	seen := map[string]bool{}
	collision := false
	for i, value := range values {
		parts := strings.FieldsFunc(value, func(r rune) bool { return !unicode.IsLetter(r) && !unicode.IsDigit(r) })
		member := name
		for _, part := range parts {
			runes := []rune(part)
			runes[0] = unicode.ToUpper(runes[0])
			member += string(runes)
		}
		if python {
			member = "VALUE_" + strings.ToUpper(strings.Join(parts, "_"))
		}
		collision = collision || len(parts) == 0 || seen[member]
		seen[member] = true
		result[i] = member
	}
	if collision {
		for i, value := range values {
			result[i] = fmt.Sprintf("%sValue%x", name, []byte(value))
			if python {
				result[i] = fmt.Sprintf("VALUE_%x", []byte(value))
			}
		}
	}
	return result
}

func writeGoTransportEnums(b *strings.Builder, fields *fieldsFile, names []string) {
	for _, name := range transportEnums(fields, names) {
		fmt.Fprintf(b, "\ntype %s string\n", name)
		b.WriteString("const (\n")
		members := enumMemberNames(name, fields.Enums[name], false)
		for i, value := range fields.Enums[name] {
			fmt.Fprintf(b, "%s %s = %q\n", members[i], name, value)
		}
		b.WriteString(")\n")
		fmt.Fprintf(b, "func (v %s) Validate() error {\nswitch v {\ncase ", name)
		values := make([]string, len(fields.Enums[name]))
		for i, value := range fields.Enums[name] {
			values[i] = fmt.Sprintf("%q", value)
		}
		b.WriteString(strings.Join(values, ", "))
		fmt.Fprintf(b, ":\nreturn nil\n}\nreturn fmt.Errorf(\"invalid %s\")\n}\n", name)
		fmt.Fprintf(b, "func (v %s) MarshalJSON() ([]byte, error) {\nif err := v.Validate(); err != nil { return nil, err }; return json.Marshal(string(v))\n}\n", name)
		fmt.Fprintf(b, "func (v *%s) UnmarshalJSON(data []byte) error {\nvar wire *string\nif err := json.Unmarshal(data, &wire); err != nil { return err }; if wire == nil { return fmt.Errorf(\"invalid %s\") }; next := %s(*wire); if err := next.Validate(); err != nil { return err }; *v = next; return nil\n}\n", name, name, name)
	}
}

func writePythonTransportEnums(b *strings.Builder, fields *fieldsFile, names []string) {
	if len(transportEnums(fields, names)) == 0 {
		return
	}
	b.WriteString(`from enum import Enum
from pydantic_core import core_schema


class _ContractEnum(str, Enum):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_before_validator_function(
            cls._validate_wire,
            handler(source_type),
            serialization=core_schema.plain_serializer_function_ser_schema(cls._serialize_wire),
        )

    @classmethod
    def _serialize_wire(cls, value):
        return cls._validate_wire(value).value

    @classmethod
    def _validate_wire(cls, value):
        if isinstance(value, cls):
            return value
        if type(value) is not str:
            raise ValueError("enum wire value must be a string")
        return cls(value)
`)
	for _, name := range transportEnums(fields, names) {
		fmt.Fprintf(b, "\n\nclass %s(_ContractEnum):\n", name)
		members := enumMemberNames(name, fields.Enums[name], true)
		for i, value := range fields.Enums[name] {
			fmt.Fprintf(b, "    %s = %q\n", members[i], value)
		}
	}
}
