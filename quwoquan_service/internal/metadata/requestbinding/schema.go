// Package requestbinding 从 ContractGraph 原始文档投影 JSON query 对象，不维护类型 registry。
package requestbinding

import (
	"encoding/json"
	"fmt"
	"path"
	"reflect"
	"strconv"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

type Schema struct {
	Type                 string             `json:"type" yaml:"type"`
	Pattern              string             `json:"pattern,omitempty" yaml:"pattern,omitempty"`
	Properties           map[string]*Schema `json:"properties,omitempty" yaml:"properties,omitempty"`
	Required             []string           `json:"required,omitempty" yaml:"required,omitempty"`
	AdditionalProperties *bool              `json:"additionalProperties,omitempty" yaml:"additionalProperties,omitempty"`
	Items                *Schema            `json:"items,omitempty" yaml:"items,omitempty"`
	Enum                 []string           `json:"enum,omitempty" yaml:"enum,omitempty"`
	Nullable             bool               `json:"nullable,omitempty" yaml:"nullable,omitempty"`
	MaxLength            *int               `json:"maxLength,omitempty" yaml:"maxLength,omitempty"`
	MinLength            *int               `json:"minLength,omitempty" yaml:"minLength,omitempty"`
	MaxItems             *int               `json:"maxItems,omitempty" yaml:"maxItems,omitempty"`
	MinItems             *int               `json:"minItems,omitempty" yaml:"minItems,omitempty"`
	Minimum              *int               `json:"minimum,omitempty" yaml:"minimum,omitempty"`
	Maximum              *int               `json:"maximum,omitempty" yaml:"maximum,omitempty"`
	MaxUTF8Bytes         *int               `json:"x-max-utf8-bytes,omitempty" yaml:"x-max-utf8-bytes,omitempty"`
	NotBlank             bool               `json:"x-not-blank,omitempty" yaml:"x-not-blank,omitempty"`
}

type field struct {
	Name             string   `json:"name"`
	Type             string   `json:"type"`
	WireName         string   `json:"client_wire_name"`
	EnumRef          string   `json:"enum_ref"`
	Values           []string `json:"values"`
	Constraints      []string `json:"constraints"`
	MaxUTF8Bytes     *int     `json:"max_utf8_bytes"`
	MaxItems         *int     `json:"max_items"`
	ItemMaxUTF8Bytes *int     `json:"item_max_utf8_bytes"`
	Format           string   `json:"format"`
	CoPresentWith    []string `json:"co_present_with"`
}
type entity struct {
	Fields []field `json:"fields"`
}
type document struct {
	Entity       string                     `json:"entity"`
	Fields       []field                    `json:"fields"`
	Types        map[string]entity          `json:"types"`
	Entities     map[string]entity          `json:"entities"`
	ValueObjects map[string]entity          `json:"value_objects"`
	Members      map[string]entity          `json:"members"`
	Enums        map[string]json.RawMessage `json:"enums"`
}

type sourceResolver struct {
	types    map[string][]entity
	enums    map[string][][]string
	visiting map[string]bool
}

// Resolve 只读取已接受图中的 object-local 与 shared 文档，字段位置不重复 author。
func Resolve(documents []ast.SourceDocument, operation ast.Operation, binding ast.RequestBinding) (*Schema, error) {
	if binding.Encoding != "json" || binding.MaxBytes <= 0 {
		return nil, fmt.Errorf("%s JSON query requires encoding=json and positive max_bytes", binding.Name)
	}
	resolver, err := newSourceResolver(documents, operation.SourcePath)
	if err != nil {
		return nil, err
	}
	request, err := resolver.resolveEntity(operation.RequestEntity)
	if err != nil {
		return nil, err
	}
	for _, value := range request.Fields {
		if value.Name != binding.Field {
			continue
		}
		schema, err := resolver.resolveField(value)
		if err != nil {
			return nil, fmt.Errorf("%s.%s: %w", operation.RequestEntity, value.Name, err)
		}
		if schema.Type != "object" {
			return nil, fmt.Errorf("JSON query %s must reference a typed object", binding.Name)
		}
		schema.Nullable = false // 缺省由 binding 控制，显式 null 永远非法。
		return schema, nil
	}
	return nil, fmt.Errorf("JSON query field %s absent from %s", binding.Field, operation.RequestEntity)
}

func newSourceResolver(documents []ast.SourceDocument, sourcePath string) (*sourceResolver, error) {
	resolver := &sourceResolver{types: map[string][]entity{}, enums: map[string][][]string{}, visiting: map[string]bool{}}
	owner := path.Dir(sourcePath)
	domain := strings.Split(sourcePath, "/")[0]
	for _, source := range documents {
		dir, base := path.Dir(source.Path), path.Base(source.Path)
		if dir != owner && dir != domain+"/_shared" && dir != "_shared" {
			continue
		}
		if base != "fields.yaml" && base != "types.yaml" && base != "enums.yaml" {
			continue
		}
		var doc document
		if err := json.Unmarshal(source.Content, &doc); err != nil {
			return nil, err
		}
		if err := resolver.addDocument(doc); err != nil {
			return nil, err
		}
	}
	return resolver, nil
}
func (resolver *sourceResolver) addDocument(doc document) error {
	catalogs := []map[string]entity{doc.Types, doc.Entities, doc.ValueObjects, doc.Members}
	if doc.Entity != "" {
		catalogs = append(catalogs, map[string]entity{doc.Entity: {Fields: doc.Fields}})
	}
	for _, catalog := range catalogs {
		for name, value := range catalog {
			resolver.types[name] = append(resolver.types[name], value)
		}
	}
	for name, raw := range doc.Enums {
		var values []string
		if json.Unmarshal(raw, &values) != nil {
			var def struct {
				Values []string `json:"values"`
			}
			if err := json.Unmarshal(raw, &def); err != nil {
				return err
			}
			values = def.Values
		}
		resolver.enums[name] = append(resolver.enums[name], values)
	}
	return nil
}

// 与 domain generator 的 canonical 合并规则一致：只合并相同 typed 定义，不按声明位置覆盖。
// 在可达边上检查，而非加载整个 catalog 时让无关类型阻断请求。
func selectReachableAuthority[T any](kind, name string, definitions []T) (T, error) {
	var zero T
	if len(definitions) == 0 {
		return zero, fmt.Errorf("JSON query %s %s not found", kind, name)
	}
	selected := definitions[0]
	for _, definition := range definitions[1:] {
		if !reflect.DeepEqual(selected, definition) {
			return zero, fmt.Errorf("ambiguous JSON query %s %s", kind, name)
		}
	}
	return selected, nil
}
func (resolver *sourceResolver) resolveEntity(name string) (entity, error) {
	return selectReachableAuthority("type", name, resolver.types[name])
}

func (resolver *sourceResolver) resolveField(value field) (*Schema, error) {
	if len(value.CoPresentWith) > 0 {
		return nil, fmt.Errorf("JSON query field %s has unsupported format or co-presence constraint", value.Name)
	}
	schema, err := resolver.resolveType(value)
	if err != nil {
		return nil, err
	}
	schema.MaxUTF8Bytes = value.MaxUTF8Bytes
	schema.MaxItems = value.MaxItems
	for _, constraint := range value.Constraints {
		if err := schema.applyConstraint(constraint); err != nil {
			return nil, err
		}
	}
	if err := schema.applyFormat(value.Format); err != nil {
		return nil, err
	}
	if err := schema.validateBounds(value.Name); err != nil {
		return nil, err
	}
	return schema, nil
}
func (resolver *sourceResolver) resolveType(value field) (*Schema, error) {
	kind := strings.TrimSpace(value.Type)
	if strings.HasPrefix(kind, "[]") {
		item := value
		item.Type = strings.TrimPrefix(kind, "[]")
		item.Constraints = nil
		item.MaxUTF8Bytes = value.ItemMaxUTF8Bytes
		item.MaxItems = nil
		item.ItemMaxUTF8Bytes = nil
		resolved, err := resolver.resolveField(item)
		return &Schema{Type: "array", Items: resolved}, err
	}
	if kind == "enum" || len(resolver.enums[kind]) > 0 {
		return resolver.resolveEnum(value)
	}
	switch kind {
	case "string", "ObjectId", "uuid":
		return &Schema{Type: "string"}, nil
	case "int", "int32", "int64", "long", "integer":
		return &Schema{Type: "integer"}, nil
	case "float", "float32", "float64", "double", "number":
		return &Schema{Type: "number"}, nil
	case "bool", "boolean":
		return &Schema{Type: "boolean"}, nil
	default:
		return resolver.resolveObject(kind)
	}
}
func (resolver *sourceResolver) resolveEnum(value field) (*Schema, error) {
	values := value.Values
	ref := value.EnumRef
	if ref == "" {
		ref = value.Type
	}
	if len(values) == 0 {
		var err error
		values, err = selectReachableAuthority("enum", ref, resolver.enums[ref])
		if err != nil {
			return nil, err
		}
	}
	if len(values) == 0 {
		return nil, fmt.Errorf("enum %s lacks closed values", ref)
	}
	return &Schema{Type: "string", Enum: values}, nil
}
func (resolver *sourceResolver) resolveObject(kind string) (*Schema, error) {
	definition, err := resolver.resolveEntity(kind)
	if err != nil {
		return nil, err
	}
	if len(definition.Fields) == 0 {
		return nil, fmt.Errorf("unsupported or unbounded JSON query type %s", kind)
	}
	if resolver.visiting[kind] {
		return nil, fmt.Errorf("recursive JSON query type %s", kind)
	}
	resolver.visiting[kind] = true
	defer delete(resolver.visiting, kind)
	no := false
	schema := &Schema{Type: "object", AdditionalProperties: &no, Properties: map[string]*Schema{}}
	for _, member := range definition.Fields {
		child, err := resolver.resolveField(member)
		if err != nil {
			return nil, fmt.Errorf("%s.%s: %w", kind, member.Name, err)
		}
		name := member.WireName
		if name == "" {
			name = member.Name
		}
		if _, exists := schema.Properties[name]; exists {
			return nil, fmt.Errorf("duplicate wire field %s", name)
		}
		schema.Properties[name] = child
		if !child.Nullable {
			schema.Required = append(schema.Required, name)
		}
	}
	return schema, nil
}
func (schema *Schema) applyConstraint(constraint string) error {
	one, zero := 1, 0
	switch constraint {
	case "NULLABLE":
		schema.Nullable = true
	case "NOT_NULL":
	case "NOT_BLANK":
		if schema.Type == "array" {
			schema.MinItems = &one
		} else {
			schema.MinLength = &one
			schema.NotBlank = true
		}
	case "POSITIVE":
		schema.Minimum = &one
	case "NON_NEGATIVE":
		schema.Minimum = &zero
	default:
		return schema.applyNumericConstraint(constraint)
	}
	return nil
}
func (schema *Schema) applyNumericConstraint(constraint string) error {
	for _, bound := range []struct {
		prefix string
		target **int
	}{{"MAX_LENGTH_", &schema.MaxLength}, {"MIN_LENGTH_", &schema.MinLength}, {"MAX_ITEMS_", &schema.MaxItems}, {"MIN_ITEMS_", &schema.MinItems}, {"MAX_", &schema.Maximum}, {"MIN_", &schema.Minimum}} {
		if !strings.HasPrefix(constraint, bound.prefix) {
			continue
		}
		n, err := strconv.Atoi(strings.TrimPrefix(constraint, bound.prefix))
		if err != nil {
			return fmt.Errorf("invalid JSON query constraint %s", constraint)
		}
		*bound.target = &n
		return nil
	}
	return fmt.Errorf("unsupported JSON query constraint %s", constraint)
}
func (schema *Schema) applyFormat(format string) error {
	if format == "" {
		return nil
	}
	if format != "canonical_sha256" || schema.Type != "string" {
		return fmt.Errorf("unsupported JSON query format %q on %s", format, schema.Type)
	}
	// 固定长度与 pattern 一起使用，避免不同正则引擎的行尾锚点容忍尾随换行。
	length := 71
	if schema.MaxLength != nil && *schema.MaxLength < length {
		return fmt.Errorf("canonical_sha256 conflicts with max length")
	}
	if schema.MinLength != nil && *schema.MinLength > length {
		return fmt.Errorf("canonical_sha256 conflicts with min length")
	}
	schema.Pattern = "^sha256:[0-9a-f]{64}$"
	schema.MinLength, schema.MaxLength = &length, &length
	return nil
}

func (schema *Schema) validateBounds(name string) error {
	if schema.Type == "string" && len(schema.Enum) == 0 && schema.MaxLength == nil && schema.MaxUTF8Bytes == nil {
		return fmt.Errorf("string %s requires explicit length boundary", name)
	}
	if schema.Type == "array" && schema.MaxItems == nil {
		return fmt.Errorf("array %s requires MAX_ITEMS boundary", name)
	}
	for _, maximum := range []*int{schema.MaxLength, schema.MaxItems, schema.MaxUTF8Bytes} {
		if maximum != nil && *maximum < 0 {
			return fmt.Errorf("negative JSON query length boundary %s", name)
		}
	}
	for _, pair := range [][2]*int{{schema.MinLength, schema.MaxLength}, {schema.MinItems, schema.MaxItems}, {schema.Minimum, schema.Maximum}} {
		if pair[0] != nil && pair[1] != nil && *pair[0] > *pair[1] {
			return fmt.Errorf("contradictory JSON query bounds %s", name)
		}
	}
	return nil
}
