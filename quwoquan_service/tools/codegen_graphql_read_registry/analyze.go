package main

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/vektah/gqlparser/v2/ast"
)

type costSummary struct {
	base        int
	worst       int
	depth       int
	fieldCount  int
	multipliers map[string]ListMultiplier
}

type mergedField struct {
	field        *ast.Field
	selectionSet ast.SelectionSet
}

func analyzeOperation(
	schema *ast.Schema,
	document *ast.QueryDocument,
	operation *ast.OperationDefinition,
) (costSummary, error) {
	if operation.Operation != ast.Query {
		return costSummary{}, errors.New("only query operations may enter the persisted read registry")
	}
	analyzer := operationAnalyzer{
		schema: schema, document: document, operation: operation,
	}
	summary, err := analyzer.analyzeComposite(schema.Query, operation.SelectionSet, false)
	if err != nil {
		return costSummary{}, err
	}
	if summary.fieldCount == 0 {
		return costSummary{}, errors.New("query must select at least one top-level field")
	}
	return summary, nil
}

type operationAnalyzer struct {
	schema    *ast.Schema
	document  *ast.QueryDocument
	operation *ast.OperationDefinition
}

func (analyzer operationAnalyzer) analyzeComposite(
	definition *ast.Definition,
	selectionSet ast.SelectionSet,
	underList bool,
) (costSummary, error) {
	if definition == nil || !definition.IsCompositeType() {
		return costSummary{}, errors.New("selection parent must be a composite GraphQL type")
	}
	runtimeTypes := []*ast.Definition{definition}
	if definition.IsAbstractType() {
		runtimeTypes = append([]*ast.Definition(nil), analyzer.schema.GetPossibleTypes(definition)...)
		sort.Slice(runtimeTypes, func(left, right int) bool {
			return runtimeTypes[left].Name < runtimeTypes[right].Name
		})
		if len(runtimeTypes) == 0 {
			return costSummary{}, fmt.Errorf("abstract type %s has no possible object types", definition.Name)
		}
	}

	var selected costSummary
	maximumDepth := 0
	maximumFields := 0
	for index, runtimeType := range runtimeTypes {
		summary, err := analyzer.analyzeRuntime(runtimeType, selectionSet, underList)
		if err != nil {
			return costSummary{}, fmt.Errorf("type %s: %w", runtimeType.Name, err)
		}
		if summary.depth > maximumDepth {
			maximumDepth = summary.depth
		}
		if summary.fieldCount > maximumFields {
			maximumFields = summary.fieldCount
		}
		if index == 0 || summary.worst > selected.worst ||
			(summary.worst == selected.worst && summary.base > selected.base) {
			selected = summary
		}
	}
	selected.depth = maximumDepth
	selected.fieldCount = maximumFields
	return selected, nil
}

func (analyzer operationAnalyzer) analyzeRuntime(
	runtimeType *ast.Definition,
	selectionSet ast.SelectionSet,
	underList bool,
) (costSummary, error) {
	fields, err := analyzer.collectFields(runtimeType, selectionSet, map[string]bool{})
	if err != nil {
		return costSummary{}, err
	}
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	summary := costSummary{
		fieldCount: len(keys), multipliers: map[string]ListMultiplier{},
	}
	for _, key := range keys {
		fieldSummary, err := analyzer.analyzeField(fields[key], underList)
		if err != nil {
			return costSummary{}, fmt.Errorf("field %s: %w", key, err)
		}
		summary.base += fieldSummary.base
		summary.worst += fieldSummary.worst
		if fieldSummary.depth > summary.depth {
			summary.depth = fieldSummary.depth
		}
		if err := mergeMultipliers(summary.multipliers, fieldSummary.multipliers); err != nil {
			return costSummary{}, err
		}
	}
	return summary, nil
}

func (analyzer operationAnalyzer) collectFields(
	runtimeType *ast.Definition,
	selectionSet ast.SelectionSet,
	fragmentStack map[string]bool,
) (map[string]mergedField, error) {
	result := map[string]mergedField{}
	for _, selection := range selectionSet {
		switch typed := selection.(type) {
		case *ast.Field:
			if !directiveAllowsWorstCase(typed.Directives) {
				continue
			}
			responseKey := typed.Alias
			if responseKey == "" {
				responseKey = typed.Name
			}
			current, exists := result[responseKey]
			if !exists {
				result[responseKey] = mergedField{
					field: typed, selectionSet: append(ast.SelectionSet(nil), typed.SelectionSet...),
				}
				continue
			}
			current.selectionSet = append(current.selectionSet, typed.SelectionSet...)
			result[responseKey] = current
		case *ast.FragmentSpread:
			if !directiveAllowsWorstCase(typed.Directives) || typed.Definition == nil ||
				!directiveAllowsWorstCase(typed.Definition.Directives) ||
				!analyzer.typeConditionMatches(runtimeType, typed.Definition.TypeCondition) {
				continue
			}
			if fragmentStack[typed.Name] {
				return nil, fmt.Errorf("fragment cycle contains %s", typed.Name)
			}
			fragmentStack[typed.Name] = true
			expanded, err := analyzer.collectFields(runtimeType, typed.Definition.SelectionSet, fragmentStack)
			delete(fragmentStack, typed.Name)
			if err != nil {
				return nil, err
			}
			mergeFieldMaps(result, expanded)
		case *ast.InlineFragment:
			if !directiveAllowsWorstCase(typed.Directives) ||
				!analyzer.typeConditionMatches(runtimeType, typed.TypeCondition) {
				continue
			}
			expanded, err := analyzer.collectFields(runtimeType, typed.SelectionSet, fragmentStack)
			if err != nil {
				return nil, err
			}
			mergeFieldMaps(result, expanded)
		default:
			return nil, fmt.Errorf("unsupported selection %T", selection)
		}
	}
	return result, nil
}

func mergeFieldMaps(destination, source map[string]mergedField) {
	for key, field := range source {
		current, exists := destination[key]
		if !exists {
			destination[key] = field
			continue
		}
		current.selectionSet = append(current.selectionSet, field.selectionSet...)
		destination[key] = current
	}
}

func (analyzer operationAnalyzer) typeConditionMatches(
	runtimeType *ast.Definition,
	condition string,
) bool {
	if condition == "" || runtimeType.Name == condition {
		return true
	}
	definition := analyzer.schema.Types[condition]
	if definition == nil || !definition.IsAbstractType() {
		return false
	}
	for _, possible := range analyzer.schema.GetPossibleTypes(definition) {
		if possible.Name == runtimeType.Name {
			return true
		}
	}
	return false
}

func (analyzer operationAnalyzer) analyzeField(
	merged mergedField,
	underList bool,
) (costSummary, error) {
	field := merged.field
	if field.Definition == nil || field.Definition.Type == nil {
		return costSummary{}, errors.New("field definition is unavailable after validation")
	}
	isList := field.Definition.Type.Elem != nil
	if isList && field.Definition.Type.Elem.Elem != nil {
		return costSummary{}, errors.New("nested list return types are forbidden")
	}
	weight, err := fieldWeight(field.Definition, isList)
	if err != nil {
		return costSummary{}, err
	}
	namedType := analyzer.schema.Types[field.Definition.Type.Name()]
	if namedType == nil {
		return costSummary{}, fmt.Errorf("return type %s is unavailable", field.Definition.Type.Name())
	}
	if !isList && field.Definition.Directives.ForName("listCost") != nil {
		return costSummary{}, errors.New("@listCost is only valid on list fields")
	}
	if !isList {
		if namedType.IsLeafType() {
			return costSummary{base: weight, worst: weight, depth: 1, multipliers: map[string]ListMultiplier{}}, nil
		}
		children, err := analyzer.analyzeComposite(namedType, merged.selectionSet, underList)
		if err != nil {
			return costSummary{}, err
		}
		children.base += weight
		children.worst += weight
		children.depth++
		return children, nil
	}

	if underList {
		return costSummary{}, errors.New("nested list selections are forbidden")
	}
	policy, err := analyzer.listPolicy(field)
	if err != nil {
		return costSummary{}, err
	}
	childCost := costSummary{base: 1, worst: 1, multipliers: map[string]ListMultiplier{}}
	if namedType.IsCompositeType() {
		childCost, err = analyzer.analyzeComposite(namedType, merged.selectionSet, true)
		if err != nil {
			return costSummary{}, err
		}
	}
	if len(childCost.multipliers) != 0 {
		return costSummary{}, errors.New("nested list cost plans are forbidden")
	}
	coefficient := childCost.worst
	if coefficient < 1 {
		return costSummary{}, errors.New("list child coefficient must be positive")
	}
	return costSummary{
		base:  weight + policy.DefaultValue*coefficient,
		worst: weight + policy.MaximumValue*coefficient,
		depth: 1 + childCost.depth,
		multipliers: map[string]ListMultiplier{
			policy.VariablePath: {
				VariablePath: policy.VariablePath, Coefficient: coefficient,
				DefaultValue: policy.DefaultValue, MaximumValue: policy.MaximumValue,
			},
		},
	}, nil
}

func directiveAllowsWorstCase(directives ast.DirectiveList) bool {
	for _, directive := range directives {
		argument := directive.Arguments.ForName("if")
		if argument == nil || argument.Value == nil || argument.Value.Kind != ast.BooleanValue {
			continue
		}
		value := argument.Value.Raw == "true"
		if directive.Name == "skip" && value {
			return false
		}
		if directive.Name == "include" && !value {
			return false
		}
	}
	return true
}

func fieldWeight(definition *ast.FieldDefinition, isList bool) (int, error) {
	weight := 1
	if isList {
		weight = 2
	}
	directive := definition.Directives.ForName("cost")
	if directive == nil {
		return weight, nil
	}
	value, err := directiveInt(directive, "weight")
	if err != nil || value < 1 {
		return 0, errors.New("@cost weight must be a positive integer")
	}
	return value, nil
}

func (analyzer operationAnalyzer) listPolicy(field *ast.Field) (ListMultiplier, error) {
	directive := field.Definition.Directives.ForName("listCost")
	if directive == nil {
		return ListMultiplier{}, errors.New("list field requires bounded @listCost policy")
	}
	argumentName, err := directiveString(directive, "argument")
	if err != nil {
		return ListMultiplier{}, errors.New("@listCost argument must be a GraphQL variable path")
	}
	defaultValue, defaultErr := directiveInt(directive, "defaultValue")
	maximumValue, maximumErr := directiveInt(directive, "maximumValue")
	if defaultErr != nil || maximumErr != nil || defaultValue < 1 ||
		maximumValue < defaultValue || maximumValue > 100 {
		return ListMultiplier{}, errors.New("@listCost bounds must satisfy 1 <= defaultValue <= maximumValue <= 100")
	}
	if strings.Contains(argumentName, ".") {
		if err := analyzer.validateInputObjectPaginationPath(argumentName, defaultValue); err != nil {
			return ListMultiplier{}, err
		}
		return ListMultiplier{
			VariablePath: argumentName, DefaultValue: defaultValue,
			MaximumValue: maximumValue,
		}, nil
	}
	if !graphQLName.MatchString(argumentName) {
		return ListMultiplier{}, errors.New("@listCost argument must be a GraphQL variable path")
	}
	argument := field.Arguments.ForName(argumentName)
	if argument == nil || argument.Value == nil || argument.Value.Kind != ast.Variable {
		return ListMultiplier{}, fmt.Errorf("list field argument %s must use a pagination variable", argumentName)
	}
	variable := analyzer.operation.VariableDefinitions.ForName(argument.Value.Raw)
	if variable == nil || variable.Type == nil || variable.Type.Name() != "Int" ||
		variable.DefaultValue == nil || variable.DefaultValue.Kind != ast.IntValue {
		return ListMultiplier{}, fmt.Errorf("pagination variable $%s must be Int with a default", argument.Value.Raw)
	}
	declaredDefault, err := strconv.Atoi(variable.DefaultValue.Raw)
	if err != nil || declaredDefault != defaultValue {
		return ListMultiplier{}, fmt.Errorf("pagination variable $%s default differs from @listCost", argument.Value.Raw)
	}
	return ListMultiplier{
		VariablePath: argument.Value.Raw, DefaultValue: defaultValue,
		MaximumValue: maximumValue,
	}, nil
}

func (analyzer operationAnalyzer) validateInputObjectPaginationPath(path string, defaultValue int) error {
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return errors.New("@listCost input variable path must contain a field")
	}
	for _, part := range parts {
		if !graphQLName.MatchString(part) {
			return fmt.Errorf("@listCost input variable path %q is invalid", path)
		}
	}
	variable := analyzer.operation.VariableDefinitions.ForName(parts[0])
	if variable == nil || variable.Type == nil {
		return fmt.Errorf("pagination variable $%s is not declared", parts[0])
	}
	typeName := variable.Type.Name()
	for index, fieldName := range parts[1:] {
		definition := analyzer.schema.Types[typeName]
		if definition == nil || definition.Kind != ast.InputObject {
			return fmt.Errorf("pagination variable path %s traverses non-input type %s", path, typeName)
		}
		inputField := definition.Fields.ForName(fieldName)
		if inputField == nil || inputField.Type == nil {
			return fmt.Errorf("pagination variable path %s is absent from schema", path)
		}
		if index < len(parts)-2 {
			typeName = inputField.Type.Name()
			continue
		}
		if inputField.Type.Name() != "Int" || inputField.DefaultValue == nil ||
			inputField.DefaultValue.Kind != ast.IntValue {
			return fmt.Errorf("pagination input %s must be Int with a default", path)
		}
		declaredDefault, err := strconv.Atoi(inputField.DefaultValue.Raw)
		if err != nil || declaredDefault != defaultValue {
			return fmt.Errorf("pagination input %s default differs from @listCost", path)
		}
	}
	return nil
}

func directiveInt(directive *ast.Directive, name string) (int, error) {
	argument := directive.Arguments.ForName(name)
	if argument == nil || argument.Value == nil || argument.Value.Kind != ast.IntValue {
		return 0, fmt.Errorf("@%s %s must be an integer", directive.Name, name)
	}
	return strconv.Atoi(argument.Value.Raw)
}

func directiveString(directive *ast.Directive, name string) (string, error) {
	argument := directive.Arguments.ForName(name)
	if argument == nil || argument.Value == nil || argument.Value.Kind != ast.StringValue {
		return "", fmt.Errorf("@%s %s must be a string", directive.Name, name)
	}
	return strings.TrimSpace(argument.Value.Raw), nil
}

func mergeMultipliers(destination, source map[string]ListMultiplier) error {
	for path, multiplier := range source {
		current, exists := destination[path]
		if !exists {
			destination[path] = multiplier
			continue
		}
		if current.DefaultValue != multiplier.DefaultValue || current.MaximumValue != multiplier.MaximumValue {
			return fmt.Errorf("pagination variable %s has conflicting bounds", path)
		}
		current.Coefficient += multiplier.Coefficient
		destination[path] = current
	}
	return nil
}

func sortedMultipliers(values map[string]ListMultiplier) []ListMultiplier {
	paths := make([]string, 0, len(values))
	for path := range values {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	result := make([]ListMultiplier, 0, len(paths))
	for _, path := range paths {
		result = append(result, values[path])
	}
	return result
}
