package main

import (
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/requestbinding"
)

type jsonQuerySpec struct {
	Binding  requestBindingYAML
	Schema   *requestbinding.Schema
	TypeName string
	Function string
}

func resolveJSONQueries(g *graph.ContractGraph, sourcePath string, route serviceRouteYAML) ([]jsonQuerySpec, error) {
	var result []jsonQuerySpec
	for _, binding := range route.RequestBindings.Query {
		if binding.Encoding == "" {
			continue
		}
		op := ast.Operation{SourcePath: sourcePath, RequestEntity: route.RequestEntity}
		schema, err := requestbinding.Resolve(g.Documents, op, ast.RequestBinding{Name: binding.Name, Field: binding.Field, Encoding: binding.Encoding, MaxBytes: binding.MaxBytes})
		if err != nil {
			return nil, fmt.Errorf("%s: %w", route.Operation, err)
		}
		name := "Generated" + toPascal(route.Operation) + toPascal(binding.Field) + "Query"
		result = append(result, jsonQuerySpec{Binding: binding, Schema: schema, TypeName: name, Function: "Bind" + name})
	}
	return result, nil
}

func generateJSONQueryBindings(routes []serviceRouteYAML, outputDir string) error {
	var queries []jsonQuerySpec
	for _, route := range routes {
		queries = append(queries, route.JSONQueries...)
	}
	if len(queries) == 0 {
		return nil
	}
	var out strings.Builder
	out.WriteString("// Code generated from canonical request_bindings and typed fields. DO NOT EDIT.\npackage transport\n\nimport (\n\"encoding/json\"\n\"fmt\"\n\"io\"\n\"net/http\"\n\"net/url\"\n\"strings\"\n\"unicode/utf8\"\n)\nvar _ = utf8.RuneCountInString\n")
	for _, query := range queries {
		renderJSONQueryType(&out, query.TypeName, query.Schema)
		renderJSONQueryValidation(&out, query.TypeName, query.Schema)
		fmt.Fprintf(&out, "func %s(r *http.Request) (*%s,error) {\nvalues,err:=url.ParseQuery(r.URL.RawQuery);if err!=nil{return nil,fmt.Errorf(\"invalid query encoding\")}\nentries,present:=values[%q]\n", query.Function, query.TypeName, query.Binding.Name)
		if query.Binding.Required != nil && *query.Binding.Required {
			fmt.Fprintf(&out, "if !present{return nil,fmt.Errorf(%q)}\n", query.Binding.Name+" is required")
		} else {
			out.WriteString("if !present{return nil,nil}\n")
		}
		fmt.Fprintf(&out, "if len(entries)!=1 || strings.TrimSpace(entries[0])==\"\" || len(entries[0])>%d || !utf8.ValidString(entries[0]) {return nil,fmt.Errorf(\"invalid JSON query cardinality or byte length\")}\n", query.Binding.MaxBytes)
		out.WriteString("decoder:=json.NewDecoder(strings.NewReader(entries[0]));decoder.UseNumber();var raw any\nif err:=decoder.Decode(&raw);err!=nil{return nil,fmt.Errorf(\"invalid JSON query object\")}\nvar trailing any;if decoder.Decode(&trailing)!=io.EOF{return nil,fmt.Errorf(\"JSON query contains trailing data\")}\n")
		fmt.Fprintf(&out, "if raw==nil{return nil,fmt.Errorf(\"JSON query must be an object\")}\nif err:=validate%s(raw);err!=nil{return nil,err}\nvar value %s\nif err:=json.Unmarshal([]byte(entries[0]),&value);err!=nil{return nil,fmt.Errorf(\"invalid typed JSON query\")}\nreturn &value,nil\n}\n", query.TypeName, query.TypeName)
	}
	payload := out.String()
	if strings.Contains(payload, "regexp.MatchString(") {
		payload = strings.Replace(payload, "import (", "import (\n\"regexp\"", 1)
	}
	formatted, err := format.Source([]byte(payload))
	if err != nil {
		return fmt.Errorf("format JSON query binder: %w", err)
	}
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outputDir, "json_query_bindings.go"), formatted, 0644)
}

func jsonQueryKeys(schema *requestbinding.Schema) []string {
	keys := make([]string, 0, len(schema.Properties))
	for key := range schema.Properties {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
func jsonQueryGoType(name string, schema *requestbinding.Schema) string {
	kind := ""
	switch schema.Type {
	case "object":
		kind = name
	case "array":
		kind = "[]" + jsonQueryGoType(name+"Item", schema.Items)
	case "integer":
		kind = "int64"
	case "number":
		kind = "float64"
	case "boolean":
		kind = "bool"
	default:
		kind = "string"
	}
	if schema.Nullable {
		return "*" + kind
	}
	return kind
}
func renderJSONQueryType(out *strings.Builder, name string, schema *requestbinding.Schema) {
	if schema.Type == "array" {
		renderJSONQueryType(out, name+"Item", schema.Items)
		return
	}
	if schema.Type != "object" {
		return
	}
	fmt.Fprintf(out, "type %s struct {\n", name)
	for _, key := range jsonQueryKeys(schema) {
		fmt.Fprintf(out, "%s %s `json:%q`\n", toPascal(key), jsonQueryGoType(name+toPascal(key), schema.Properties[key]), key)
	}
	out.WriteString("}\n")
	for _, key := range jsonQueryKeys(schema) {
		renderJSONQueryType(out, name+toPascal(key), schema.Properties[key])
	}
}
func renderJSONQueryValidation(out *strings.Builder, name string, schema *requestbinding.Schema) {
	fmt.Fprintf(out, "func validate%s(raw any) error {\n", name)
	if schema.Nullable {
		out.WriteString("if raw==nil{return nil}\n")
	}
	failure := "return fmt.Errorf(\"invalid typed JSON query field\")"
	switch schema.Type {
	case "object":
		renderJSONQueryObjectValidation(out, name, schema, failure)
	case "array":
		fmt.Fprintf(out, "value,ok:=raw.([]any);if !ok{%s}\n", failure)
		renderJSONQueryBounds(out, "len(value)", schema.MinItems, schema.MaxItems)
		fmt.Fprintf(out, "for _,item:=range value{if err:=validate%sItem(item);err!=nil{return err}}\n", name)
	case "string":
		renderJSONQueryStringValidation(out, schema, failure)
	case "integer", "number":
		fmt.Fprintf(out, "number,ok:=raw.(json.Number);if !ok{%s}\n", failure)
		if schema.Type == "integer" {
			out.WriteString("value,err:=number.Int64()\n")
		} else {
			out.WriteString("value,err:=number.Float64()\n")
		}
		fmt.Fprintf(out, "if err!=nil{%s};_ = value\n", failure)
		renderJSONQueryBounds(out, "value", schema.Minimum, schema.Maximum)
	case "boolean":
		fmt.Fprintf(out, "if _,ok:=raw.(bool);!ok{%s}\n", failure)
	}
	out.WriteString("return nil\n}\n")
	for _, key := range jsonQueryKeys(schema) {
		renderJSONQueryValidation(out, name+toPascal(key), schema.Properties[key])
	}
	if schema.Items != nil {
		renderJSONQueryValidation(out, name+"Item", schema.Items)
	}
}
func renderJSONQueryStringValidation(out *strings.Builder, schema *requestbinding.Schema, failure string) {
	fmt.Fprintf(out, "value,ok:=raw.(string);if !ok{%s}\n_ = value\n", failure)
	renderJSONQueryBounds(out, "utf8.RuneCountInString(value)", schema.MinLength, schema.MaxLength)
	renderJSONQueryBounds(out, "len(value)", nil, schema.MaxUTF8Bytes)
	if schema.Pattern != "" {
		fmt.Fprintf(out, "if matched,err:=regexp.MatchString(%q,value);err!=nil||!matched{%s}\n", schema.Pattern, failure)
	}
	if schema.NotBlank {
		fmt.Fprintf(out, "if strings.TrimSpace(value)==\"\"{%s}\n", failure)
	}
	if len(schema.Enum) > 0 {
		out.WriteString("switch value {case ")
		renderJSONQueryCases(out, schema.Enum)
		fmt.Fprintf(out, ":\ndefault:%s\n}\n", failure)
	}
}
func renderJSONQueryCases(out *strings.Builder, values []string) {
	for i, value := range values {
		if i > 0 {
			out.WriteString(",")
		}
		fmt.Fprintf(out, "%q", value)
	}
}
func renderJSONQueryObjectValidation(out *strings.Builder, name string, schema *requestbinding.Schema, failure string) {
	fmt.Fprintf(out, "value,ok:=raw.(map[string]any);if !ok{%s}\n", failure)
	out.WriteString("for key:=range value {switch key {\ncase ")
	keys := jsonQueryKeys(schema)
	renderJSONQueryCases(out, keys)
	fmt.Fprintf(out, ":\ndefault:%s\n}}\n", failure)
	for _, key := range schema.Required {
		fmt.Fprintf(out, "if _,ok:=value[%q];!ok{%s}\n", key, failure)
	}
	for _, key := range keys {
		fmt.Fprintf(out, "if field,ok:=value[%q];ok{if err:=validate%s(field);err!=nil{return err}}\n", key, name+toPascal(key))
	}
}
func renderJSONQueryBounds(out *strings.Builder, expression string, minimum, maximum *int) {
	if minimum != nil {
		fmt.Fprintf(out, "if %s < %d{return fmt.Errorf(\"JSON query below minimum\")}\n", expression, *minimum)
	}
	if maximum != nil {
		fmt.Fprintf(out, "if %s > %d{return fmt.Errorf(\"JSON query exceeds maximum\")}\n", expression, *maximum)
	}
}
