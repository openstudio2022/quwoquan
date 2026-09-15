package main

import (
	"fmt"
	"github.com/vektah/gqlparser/v2/ast"
	codegen "quwoquan_service/internal/metadata/codegen"
	"strings"
)

type collectionWireField struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	Nullable    bool     `yaml:"nullable"`
	Constraints []string `yaml:"constraints"`
	EnumRef     string   `yaml:"enum_ref"`
}
type collectionWireType struct {
	Fields []collectionWireField `yaml:"fields"`
}

// 直接消费 decoder 的 canonical projection/fields，不用另一份手写字段表。
func validateCollectionSelection(source *codegen.Source, schema *ast.Schema, document *ast.QueryDocument, response, projection string) error {
	var root collectionWireType
	if err := source.Decode("content/content/post_collection/projections/"+projection, &root); err != nil {
		return err
	}
	var types struct {
		Types map[string]collectionWireType `yaml:"types"`
	}
	if err := source.Decode("content/content/post_collection/fields.yaml", &types); err != nil {
		return err
	}
	if len(document.Operations) != 1 || len(document.Operations[0].SelectionSet) != 1 {
		return fmt.Errorf("collection requires exactly one operation/root")
	}
	selected, ok := document.Operations[0].SelectionSet[0].(*ast.Field)
	if !ok || selected.Definition == nil || selected.Definition.Type.Name() != response {
		return fmt.Errorf("collection response owner mismatch")
	}
	return compareCollectionSelection(schema, selected.SelectionSet, root.Fields, types.Types, false, response)
}

// 运行时精确字段校验从解析后的真实 selection 派生，包含 nullable 和 list item。
func collectionSelectionShape(selection ast.SelectionSet) map[string]any {
	fields := map[string]any{}
	for _, node := range selection {
		f := node.(*ast.Field)
		fields[f.Name] = collectionValueShape(f.Definition.Type, f.SelectionSet)
	}
	return map[string]any{"kind": "object", "nullable": false, "fields": fields}
}
func collectionValueShape(typ *ast.Type, selection ast.SelectionSet) map[string]any {
	shape := map[string]any{"nullable": !typ.NonNull}
	if typ.Elem != nil {
		shape["kind"] = "list"
		shape["item"] = collectionValueShape(typ.Elem, selection)
		return shape
	}
	if len(selection) > 0 {
		object := collectionSelectionShape(selection)
		object["nullable"] = !typ.NonNull
		return object
	}
	kind := "string"
	switch typ.Name() {
	case "Int":
		kind = "int"
	case "Boolean":
		kind = "bool"
	}
	shape["kind"] = kind
	return shape
}

func compareCollectionSelection(schema *ast.Schema, selection ast.SelectionSet, fields []collectionWireField, types map[string]collectionWireType, nested bool, path string) error {
	if len(selection) != len(fields) {
		return fmt.Errorf("%s selection count differs from canonical decoder", path)
	}
	byName := map[string]collectionWireField{}
	for _, field := range fields {
		byName[field.Name] = field
	}
	seen := map[string]bool{}
	for _, node := range selection {
		f, ok := node.(*ast.Field)
		if !ok || f.Definition == nil || len(f.Directives) != 0 || f.Alias != "" && f.Alias != f.Name {
			return fmt.Errorf("%s must use exact unconditional fields", path)
		}
		wire, ok := byName[f.Name]
		if !ok || seen[f.Name] {
			return fmt.Errorf("%s unknown or duplicate field %s", path, f.Name)
		}
		seen[f.Name] = true
		nullable := wire.Nullable
		if nested {
			nullable = false
			for _, c := range wire.Constraints {
				if c == "NULLABLE" {
					nullable = true
				}
			}
		}
		typ := f.Definition.Type
		if typ.NonNull == nullable {
			return fmt.Errorf("%s.%s nullability mismatch", path, f.Name)
		}
		name := wire.Type
		list := strings.HasPrefix(name, "[]")
		if list != (typ.Elem != nil) {
			return fmt.Errorf("%s.%s list shape mismatch", path, f.Name)
		}
		if list {
			if !typ.Elem.NonNull {
				return fmt.Errorf("%s.%s nullable list item", path, f.Name)
			}
			typ = typ.Elem
			name = strings.TrimPrefix(name, "[]")
		}
		if object, ok := types[name]; ok {
			if typ.Name() != name {
				return fmt.Errorf("%s.%s object type mismatch", path, f.Name)
			}
			if err := compareCollectionSelection(schema, f.SelectionSet, object.Fields, types, true, path+"."+f.Name); err != nil {
				return err
			}
			continue
		}
		expected := ""
		switch name {
		case "string":
			expected = "String"
		case "enum":
			expected = "String"
		case "int", "int64":
			expected = "Int"
		case "bool":
			expected = "Boolean"
		default:
			return fmt.Errorf("%s unsupported canonical type %s", path, name)
		}
		actual := typ.Name()
		if expected == "String" && actual == "ID" {
			actual = "String"
		}
		if actual != expected || len(f.SelectionSet) != 0 {
			return fmt.Errorf("%s.%s scalar type mismatch", path, f.Name)
		}
	}
	return nil
}
