package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

const (
	gatheringObjectID           = "circle.gathering"
	gatheringOperationsPath     = "circle/circle_management/gathering/operations.yaml"
	gatheringFieldsPath         = "circle/circle_management/gathering/fields.yaml"
	gatheringPlanObjectID       = "circle.gathering_plan"
	gatheringPlanOperationsPath = "circle/circle_management/gathering_plan/operations.yaml"
	gatheringPlanFieldsPath     = "circle/circle_management/gathering_plan/fields.yaml"
	gatheringOwnerService       = "circle-service"
)

type circleServiceClientSpec struct {
	DisplayName      string
	ObjectID         string
	OperationsPath   string
	FieldsPath       string
	RootTypeName     string
	PublicPackage    string
	PublicImportPath string
	PrivatePackage   string
	MetadataPrefix   string
}

var (
	gatheringServiceClientSpec = circleServiceClientSpec{
		DisplayName:      "Gathering",
		ObjectID:         gatheringObjectID,
		OperationsPath:   gatheringOperationsPath,
		FieldsPath:       gatheringFieldsPath,
		RootTypeName:     "Gathering",
		PublicPackage:    "circlegathering",
		PublicImportPath: "quwoquan_service/generated/serviceclients/circlegathering",
		PrivatePackage:   "gatheringclient",
		MetadataPrefix:   "CircleGathering",
	}
	gatheringPlanServiceClientSpec = circleServiceClientSpec{
		DisplayName:      "GatheringPlan",
		ObjectID:         gatheringPlanObjectID,
		OperationsPath:   gatheringPlanOperationsPath,
		FieldsPath:       gatheringPlanFieldsPath,
		RootTypeName:     "GatheringPlan",
		PublicPackage:    "circlegatheringplan",
		PublicImportPath: "quwoquan_service/generated/serviceclients/circlegatheringplan",
		PrivatePackage:   "gatheringplanclient",
		MetadataPrefix:   "CircleGatheringPlan",
	}
)

type gatheringFieldsDocument struct {
	Entity       string                           `yaml:"entity"`
	Fields       []gatheringField                 `yaml:"fields"`
	Entities     map[string]gatheringTypeDocument `yaml:"entities"`
	Members      map[string]gatheringTypeDocument `yaml:"members"`
	ValueObjects map[string]gatheringTypeDocument `yaml:"value_objects"`
	Types        map[string]gatheringTypeDocument `yaml:"types"`
	Enums        map[string]gatheringEnumDocument `yaml:"enums"`
}

type gatheringTypeDocument struct {
	Fields []gatheringField `yaml:"fields"`
}

type gatheringEnumDocument struct {
	Values []string `yaml:"values"`
}

type gatheringField struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	ObjectRef   string   `yaml:"object_ref"`
	EnumRef     string   `yaml:"enum_ref"`
	Constraints []string `yaml:"constraints"`
}

type gatheringClientModel struct {
	Spec       circleServiceClientSpec
	Operations []ast.Operation
	Types      map[string]gatheringTypeDocument
	TypeNames  []string
	Enums      map[string][]string
	EnumNames  []string
}

func generateGatheringServiceClient(
	source *contractcodegen.Source,
	publicClientOutput string,
	privateAliasOutput string,
	pathsOutput string,
	check bool,
) (int, error) {
	return generateCircleServiceClient(
		source,
		gatheringServiceClientSpec,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		check,
	)
}

func generateGatheringPlanServiceClient(
	source *contractcodegen.Source,
	publicClientOutput string,
	privateAliasOutput string,
	pathsOutput string,
	check bool,
) (int, error) {
	return generateCircleServiceClient(
		source,
		gatheringPlanServiceClientSpec,
		publicClientOutput,
		privateAliasOutput,
		pathsOutput,
		check,
	)
}

func generateCircleServiceClient(
	source *contractcodegen.Source,
	spec circleServiceClientSpec,
	publicClientOutput string,
	privateAliasOutput string,
	pathsOutput string,
	check bool,
) (int, error) {
	model, err := buildCircleServiceClientModel(source, spec)
	if err != nil {
		return 0, err
	}
	if err := writeCanonicalGoOutput(
		pathsOutput,
		renderGatheringPaths(model),
		check,
	); err != nil {
		return 0, err
	}
	if err := writeCanonicalGoOutput(
		publicClientOutput,
		renderGatheringClient(model),
		check,
	); err != nil {
		return 0, err
	}
	if err := writeCanonicalGoOutput(
		privateAliasOutput,
		renderGatheringClientAlias(model),
		check,
	); err != nil {
		return 0, err
	}
	return len(model.Operations), nil
}

func buildGatheringClientModel(
	source *contractcodegen.Source,
) (gatheringClientModel, error) {
	return buildCircleServiceClientModel(source, gatheringServiceClientSpec)
}

func buildCircleServiceClientModel(
	source *contractcodegen.Source,
	spec circleServiceClientSpec,
) (gatheringClientModel, error) {
	if source == nil || source.Graph() == nil {
		return gatheringClientModel{}, fmt.Errorf("ContractGraph source is required")
	}
	operations := make([]ast.Operation, 0)
	for _, operation := range source.Graph().Operations {
		if operation.ObjectID == spec.ObjectID {
			operations = append(operations, operation)
		}
	}
	if len(operations) == 0 {
		return gatheringClientModel{}, fmt.Errorf(
			"ContractGraph has no operations for %s",
			spec.ObjectID,
		)
	}
	sort.Slice(operations, func(left, right int) bool {
		return operations[left].ID < operations[right].ID
	})
	for _, operation := range operations {
		if operation.SourcePath != spec.OperationsPath {
			return gatheringClientModel{}, fmt.Errorf(
				"operation %s has non-canonical source %s",
				operation.ID,
				operation.SourcePath,
			)
		}
		if strings.TrimSpace(operation.RequestEntity) == "" ||
			strings.TrimSpace(operation.ResponseEntity) == "" {
			return gatheringClientModel{}, fmt.Errorf(
				"operation %s requires typed request and response entities",
				operation.ID,
			)
		}
	}

	var fields gatheringFieldsDocument
	if err := source.Decode(spec.FieldsPath, &fields); err != nil {
		return gatheringClientModel{}, fmt.Errorf(
			"load %s: %w",
			spec.FieldsPath,
			err,
		)
	}
	definitions := make(map[string]gatheringTypeDocument)
	for name, definition := range fields.Types {
		definitions[name] = definition
	}
	for name, definition := range fields.ValueObjects {
		definitions[name] = definition
	}
	for name, definition := range fields.Members {
		definitions[name] = definition
	}
	for name, definition := range fields.Entities {
		definitions[name] = definition
	}
	rootName := strings.TrimSpace(fields.Entity)
	if rootName == "" {
		rootName = spec.RootTypeName
	}
	if len(fields.Fields) != 0 {
		definitions[rootName] = gatheringTypeDocument{Fields: fields.Fields}
	}

	requiredTypes := map[string]struct{}{}
	queue := make([]string, 0, len(operations)*2)
	addType := func(name string) {
		name = strings.TrimSpace(name)
		if name == "" {
			return
		}
		if _, exists := requiredTypes[name]; exists {
			return
		}
		requiredTypes[name] = struct{}{}
		queue = append(queue, name)
	}
	for _, operation := range operations {
		addType(operation.RequestEntity)
		addType(operation.ResponseEntity)
	}
	requiredEnums := map[string]struct{}{}
	for len(queue) != 0 {
		name := queue[0]
		queue = queue[1:]
		definition, exists := definitions[name]
		if !exists {
			return gatheringClientModel{}, fmt.Errorf(
				"typed operation entity %s is absent from %s",
				name,
				gatheringFieldsPath,
			)
		}
		for _, field := range definition.Fields {
			if enumRef := strings.TrimSpace(field.EnumRef); enumRef != "" {
				requiredEnums[enumRef] = struct{}{}
			}
			if referenced := gatheringReferencedType(field, definitions); referenced != "" {
				addType(referenced)
			}
		}
	}

	typeNames := make([]string, 0, len(requiredTypes))
	types := make(map[string]gatheringTypeDocument, len(requiredTypes))
	for name := range requiredTypes {
		typeNames = append(typeNames, name)
		types[name] = definitions[name]
	}
	sort.Strings(typeNames)

	enums := make(map[string][]string, len(requiredEnums))
	enumNames := make([]string, 0, len(requiredEnums))
	for name := range requiredEnums {
		definition, exists := fields.Enums[name]
		if !exists || len(definition.Values) == 0 {
			return gatheringClientModel{}, fmt.Errorf(
				"typed operation enum %s is absent from %s",
				name,
				gatheringFieldsPath,
			)
		}
		enumNames = append(enumNames, name)
		enums[name] = append([]string(nil), definition.Values...)
	}
	sort.Strings(enumNames)

	return gatheringClientModel{
		Spec:       spec,
		Operations: operations,
		Types:      types,
		TypeNames:  typeNames,
		Enums:      enums,
		EnumNames:  enumNames,
	}, nil
}

func gatheringReferencedType(
	field gatheringField,
	definitions map[string]gatheringTypeDocument,
) string {
	if objectRef := strings.TrimSpace(field.ObjectRef); objectRef != "" {
		if _, exists := definitions[objectRef]; exists {
			return objectRef
		}
	}
	fieldType := strings.TrimSpace(field.Type)
	fieldType = strings.TrimSpace(strings.TrimPrefix(fieldType, "[]"))
	if _, exists := definitions[fieldType]; exists {
		return fieldType
	}
	return ""
}

func renderGatheringPaths(model gatheringClientModel) string {
	var output strings.Builder
	output.WriteString(
		"// Code generated by tools/codegen_circle_domain from " +
			model.Spec.OperationsPath + ". DO NOT EDIT.\n",
	)
	output.WriteString("package serviceclients\n\n")
	output.WriteString("import (\n\t\"net/url\"\n\t\"strings\"\n)\n\n")
	output.WriteString(`// CircleGatheringOperationMetadata is the immutable transport projection of
// one canonical Circle Gathering ContractGraph operation.
type CircleGatheringOperationMetadata struct {
	OperationID       string
	Method            string
	PathTemplate      string
	RequestEntity     string
	ResponseEntity    string
	OperationKind     string
	AuthMode          string
	Principal         string
	Scopes            []string
	Permissions       []string
	Idempotency       string
	SuccessStatus     int
	CommercialStatus  string
	CommercialReason  string
	CommercialGapID   string
	CommercialStory   string
	ContractDigest    string
}

`)
	output.WriteString("const (\n")
	for _, operation := range model.Operations {
		name := gatheringOperationGoName(operation)
		fmt.Fprintf(
			&output,
			"\tCircleGathering%sOperationID = %q\n",
			name,
			operation.ID,
		)
		fmt.Fprintf(
			&output,
			"\tCircleGathering%sPathTemplate = %q\n",
			name,
			operation.PathTemplate,
		)
	}
	output.WriteString(")\n\n")
	output.WriteString("var circleGatheringOperations = []CircleGatheringOperationMetadata{\n")
	for _, operation := range model.Operations {
		name := gatheringOperationGoName(operation)
		successStatus := operation.SuccessStatus
		if successStatus == 0 {
			successStatus = 200
		}
		fmt.Fprintf(&output, "\t{\n")
		fmt.Fprintf(
			&output,
			"\t\tOperationID: CircleGathering%sOperationID,\n",
			name,
		)
		fmt.Fprintf(&output, "\t\tMethod: %q,\n", operation.Method)
		fmt.Fprintf(
			&output,
			"\t\tPathTemplate: CircleGathering%sPathTemplate,\n",
			name,
		)
		fmt.Fprintf(&output, "\t\tRequestEntity: %q,\n", operation.RequestEntity)
		fmt.Fprintf(&output, "\t\tResponseEntity: %q,\n", operation.ResponseEntity)
		fmt.Fprintf(&output, "\t\tOperationKind: %q,\n", operation.Kind)
		fmt.Fprintf(&output, "\t\tAuthMode: %q,\n", operation.AuthMode)
		fmt.Fprintf(&output, "\t\tPrincipal: %q,\n", operation.Principal)
		fmt.Fprintf(&output, "\t\tScopes: %s,\n", goStringSlice(operation.Scopes))
		fmt.Fprintf(
			&output,
			"\t\tPermissions: %s,\n",
			goStringSlice(operation.Permissions),
		)
		fmt.Fprintf(
			&output,
			"\t\tIdempotency: %q,\n",
			operation.Reliability.Idempotency,
		)
		fmt.Fprintf(&output, "\t\tSuccessStatus: %d,\n", successStatus)
		fmt.Fprintf(
			&output,
			"\t\tCommercialStatus: %q,\n",
			operation.Commercial.Status,
		)
		fmt.Fprintf(
			&output,
			"\t\tCommercialReason: %q,\n",
			operation.Commercial.BlockReason,
		)
		fmt.Fprintf(
			&output,
			"\t\tCommercialGapID: %q,\n",
			operation.Commercial.GapID,
		)
		fmt.Fprintf(
			&output,
			"\t\tCommercialStory: %q,\n",
			operation.Commercial.TargetStory,
		)
		fmt.Fprintf(
			&output,
			"\t\tContractDigest: %q,\n",
			gatheringOperationContractDigest(operation),
		)
		fmt.Fprintf(&output, "\t},\n")
	}
	output.WriteString("}\n\n")
	output.WriteString(`func cloneCircleGatheringOperation(
	operation CircleGatheringOperationMetadata,
) CircleGatheringOperationMetadata {
	operation.Scopes = append([]string(nil), operation.Scopes...)
	operation.Permissions = append([]string(nil), operation.Permissions...)
	return operation
}

// CircleGatheringOperations returns all generated operations without exposing
// the package-owned backing slice.
func CircleGatheringOperations() []CircleGatheringOperationMetadata {
	result := make([]CircleGatheringOperationMetadata, len(circleGatheringOperations))
	for index, operation := range circleGatheringOperations {
		result[index] = cloneCircleGatheringOperation(operation)
	}
	return result
}

// LookupCircleGatheringOperation resolves only canonical generated operation IDs.
func LookupCircleGatheringOperation(
	operationID string,
) (CircleGatheringOperationMetadata, bool) {
	switch strings.TrimSpace(operationID) {
`)
	for index, operation := range model.Operations {
		fmt.Fprintf(
			&output,
			"\tcase CircleGathering%sOperationID:\n\t\treturn cloneCircleGatheringOperation(circleGatheringOperations[%d]), true\n",
			gatheringOperationGoName(operation),
			index,
		)
	}
	output.WriteString(`	default:
		return CircleGatheringOperationMetadata{}, false
	}
}

`)
	for _, operation := range model.Operations {
		renderGatheringPathFunction(&output, operation)
	}
	return renderCircleServiceClientNames(output.String(), model.Spec)
}

func renderCircleServiceClientNames(
	contents string,
	spec circleServiceClientSpec,
) string {
	contents = strings.ReplaceAll(
		contents,
		"CircleGathering",
		spec.MetadataPrefix,
	)
	contents = strings.ReplaceAll(
		contents,
		"circleGathering",
		lowerGoName(spec.MetadataPrefix),
	)
	if spec.DisplayName != "Gathering" {
		contents = strings.ReplaceAll(
			contents,
			"Circle Gathering ContractGraph",
			"Circle "+spec.DisplayName+" ContractGraph",
		)
		contents = strings.ReplaceAll(
			contents,
			"Gathering fields.yaml",
			spec.DisplayName+" fields.yaml",
		)
		contents = strings.ReplaceAll(
			contents,
			"circle gathering operation",
			"circle gathering plan operation",
		)
		contents = strings.ReplaceAll(
			contents,
			"generated Circle Gathering operation",
			"generated Circle "+spec.DisplayName+" operation",
		)
	}
	return contents
}

func renderGatheringOperationEncoder(
	output *strings.Builder,
	operation ast.Operation,
	model gatheringClientModel,
) {
	types := model.Types
	name := gatheringOperationGoName(operation)
	requestType := operation.RequestEntity
	responseType := operation.ResponseEntity
	fmt.Fprintf(
		output,
		"func Encode%s(request %s) (RequestPacket, error) {\n",
		name,
		requestType,
	)
	fmt.Fprintf(
		output,
		"\toperation, err := operationMetadata(serviceclients.CircleGathering%sOperationID)\n",
		name,
	)
	output.WriteString("\tif err != nil {\n\t\treturn RequestPacket{}, err\n\t}\n")
	output.WriteString("\tcanonicalRequest, err := json.Marshal(request)\n")
	output.WriteString("\tif err != nil {\n")
	fmt.Fprintf(
		output,
		"\t\treturn RequestPacket{}, fmt.Errorf(\"encode %s canonical request: %%w\", err)\n",
		operation.ID,
	)
	output.WriteString("\t}\n")
	fmt.Fprintf(output, "\trequestPath := serviceclients.CircleGathering%sPath(", name)
	for index, binding := range operationPathBindings(operation) {
		if index != 0 {
			output.WriteString(", ")
		}
		fmt.Fprintf(output, "request.%s", goFieldName(binding.Field))
	}
	output.WriteString(")\n")
	output.WriteString("\tquery := make(url.Values)\n")
	requestDefinition := types[requestType]
	fieldByName := map[string]gatheringField{}
	for _, field := range requestDefinition.Fields {
		fieldByName[field.Name] = field
	}
	for _, binding := range operationQueryBindings(operation) {
		field, exists := fieldByName[binding.Field]
		if !exists {
			panic(fmt.Sprintf(
				"%s query field %s absent from %s",
				operation.ID,
				binding.Field,
				requestType,
			))
		}
		expression, err := gatheringQueryExpression(
			"request."+goFieldName(field.Name),
			field,
		)
		if err != nil {
			panic(err)
		}
		required := binding.Required == nil || *binding.Required
		if !required {
			fmt.Fprintf(
				output,
				"\tif %s {\n\t\tquery.Set(%q, %s)\n\t}\n",
				gatheringNonZeroExpression(
					"request."+goFieldName(field.Name),
					field,
				),
				binding.Name,
				expression,
			)
		} else {
			fmt.Fprintf(
				output,
				"\tquery.Set(%q, %s)\n",
				binding.Name,
				expression,
			)
		}
	}
	output.WriteString("\tvar body []byte\n")
	if operation.RequestBodyKind == "object" {
		boundFields := operationBoundFields(operation)
		bodyFields := make([]gatheringField, 0, len(requestDefinition.Fields))
		for _, field := range requestDefinition.Fields {
			if _, bound := boundFields[field.Name]; !bound {
				bodyFields = append(bodyFields, field)
			}
		}
		if len(bodyFields) == len(requestDefinition.Fields) {
			output.WriteString("\tbody = canonicalRequest\n")
		} else {
			output.WriteString("\tbody, err = json.Marshal(struct {\n")
			for _, field := range bodyFields {
				goType, err := circleServiceGoType(field, model)
				if err != nil {
					panic(err)
				}
				fmt.Fprintf(
					output,
					"\t\t%s %s `json:%q`\n",
					goFieldName(field.Name),
					goType,
					gatheringJSONTag(field),
				)
			}
			output.WriteString("\t}{\n")
			for _, field := range bodyFields {
				fmt.Fprintf(
					output,
					"\t\t%s: request.%s,\n",
					goFieldName(field.Name),
					goFieldName(field.Name),
				)
			}
			output.WriteString("\t})\n")
			output.WriteString("\tif err != nil {\n")
			fmt.Fprintf(
				output,
				"\t\treturn RequestPacket{}, fmt.Errorf(\"encode %s body: %%w\", err)\n",
				operation.ID,
			)
			output.WriteString("\t}\n")
		}
	}
	output.WriteString("\treturn RequestPacket{\n")
	output.WriteString("\t\tOperation: operation,\n\t\tPath: requestPath,\n")
	output.WriteString("\t\tQuery: query,\n\t\tBody: body,\n")
	output.WriteString("\t\tCanonicalRequest: canonicalRequest,\n\t}, nil\n}\n\n")

	fmt.Fprintf(
		output,
		"func Decode%sResponse(packet ResponsePacket) (%s, error) {\n",
		name,
		responseType,
	)
	fmt.Fprintf(
		output,
		"\toperation, err := operationMetadata(serviceclients.CircleGathering%sOperationID)\n",
		name,
	)
	fmt.Fprintf(
		output,
		"\tif err != nil {\n\t\treturn %s{}, err\n\t}\n",
		responseType,
	)
	fmt.Fprintf(output, "\tvar response %s\n", responseType)
	fmt.Fprintf(
		output,
		"\tif err := decodeResponse(operation, packet, &response); err != nil {\n\t\treturn %s{}, err\n\t}\n",
		responseType,
	)
	output.WriteString("\treturn response, nil\n}\n\n")
}

func operationPathBindings(operation ast.Operation) []ast.RequestBinding {
	if operation.RequestBindings == nil {
		return nil
	}
	return operation.RequestBindings.Path
}

func operationQueryBindings(operation ast.Operation) []ast.RequestBinding {
	if operation.RequestBindings == nil {
		return nil
	}
	return operation.RequestBindings.Query
}

func operationBoundFields(operation ast.Operation) map[string]struct{} {
	result := map[string]struct{}{}
	if operation.RequestBindings == nil {
		return result
	}
	for _, bindings := range [][]ast.RequestBinding{
		operation.RequestBindings.Path,
		operation.RequestBindings.Query,
		operation.RequestBindings.Header,
		operation.RequestBindings.Injected,
	} {
		for _, binding := range bindings {
			result[binding.Field] = struct{}{}
		}
	}
	return result
}

func gatheringOperationGoName(operation ast.Operation) string {
	name := strings.TrimSpace(operation.LocalID)
	if name == "" {
		segments := strings.Split(operation.ID, ".")
		name = segments[len(segments)-1]
	}
	return goFieldName(name)
}

func gatheringOperationContractDigest(operation ast.Operation) string {
	identity := strings.Join([]string{
		gatheringOwnerService,
		operation.ID,
		operation.RequestEntity,
		operation.ResponseEntity,
	}, "|")
	digest := sha256.Sum256([]byte(identity))
	return "sha256:" + hex.EncodeToString(digest[:])
}

func gatheringGoType(
	field gatheringField,
	types map[string]gatheringTypeDocument,
) (string, error) {
	if objectRef := strings.TrimSpace(field.ObjectRef); objectRef != "" {
		if _, exists := types[objectRef]; exists {
			return objectRef, nil
		}
	}
	fieldType := strings.TrimSpace(field.Type)
	if strings.HasPrefix(fieldType, "[]") {
		inner := strings.TrimSpace(strings.TrimPrefix(fieldType, "[]"))
		if _, exists := types[inner]; exists {
			return "[]" + inner, nil
		}
		primitive, err := gatheringPrimitiveGoType(inner)
		if err != nil {
			return "", fmt.Errorf("%s array: %w", field.Name, err)
		}
		return "[]" + primitive, nil
	}
	if fieldType == "enum" {
		if strings.TrimSpace(field.EnumRef) == "" {
			return "", fmt.Errorf("%s enum_ref is required", field.Name)
		}
		return field.EnumRef, nil
	}
	if _, exists := types[fieldType]; exists {
		return fieldType, nil
	}
	return gatheringPrimitiveGoType(fieldType)
}

func circleServiceGoType(
	field gatheringField,
	model gatheringClientModel,
) (string, error) {
	goType, err := gatheringGoType(field, model.Types)
	if err != nil {
		return "", err
	}
	if model.Spec.ObjectID == gatheringPlanObjectID &&
		containsString(field.Constraints, "NULLABLE") &&
		(goType == "time.Time" ||
			isCircleServiceObjectType(goType, model.Types)) {
		return "*" + goType, nil
	}
	return goType, nil
}

func isCircleServiceObjectType(
	goType string,
	types map[string]gatheringTypeDocument,
) bool {
	_, found := types[strings.TrimPrefix(goType, "[]")]
	return found && !strings.HasPrefix(goType, "[]")
}

func gatheringPrimitiveGoType(value string) (string, error) {
	switch strings.TrimSpace(value) {
	case "string", "ObjectId", "uuid", "url":
		return "string", nil
	case "int64", "int", "integer", "long":
		return "int64", nil
	case "int32":
		return "int32", nil
	case "float", "float64", "double":
		return "float64", nil
	case "float32":
		return "float32", nil
	case "bool", "boolean":
		return "bool", nil
	case "date", "datetime", "timestamp":
		return "time.Time", nil
	case "bytes", "binary":
		return "[]byte", nil
	default:
		return "", fmt.Errorf("unsupported metadata type %q", value)
	}
}

func gatheringJSONTag(field gatheringField) string {
	name := field.Name
	if name == "_id" {
		name = "id"
	}
	if containsString(field.Constraints, "NULLABLE") {
		name += ",omitempty"
	}
	return name
}

func gatheringQueryExpression(
	expression string,
	field gatheringField,
) (string, error) {
	fieldType := strings.TrimSpace(field.Type)
	switch fieldType {
	case "string", "ObjectId", "uuid", "url":
		return expression, nil
	case "enum":
		return "string(" + expression + ")", nil
	case "int64", "int", "integer", "long":
		return "strconv.FormatInt(int64(" + expression + "), 10)", nil
	case "int32":
		return "strconv.FormatInt(int64(" + expression + "), 10)", nil
	case "float", "float64", "double":
		return "strconv.FormatFloat(float64(" + expression + "), 'g', -1, 64)", nil
	case "float32":
		return "strconv.FormatFloat(float64(" + expression + "), 'g', -1, 32)", nil
	case "bool", "boolean":
		return "strconv.FormatBool(" + expression + ")", nil
	case "date", "datetime", "timestamp":
		return expression + ".UTC().Format(time.RFC3339Nano)", nil
	default:
		return "", fmt.Errorf(
			"query field %s has unsupported type %s",
			field.Name,
			field.Type,
		)
	}
}

func gatheringNonZeroExpression(
	expression string,
	field gatheringField,
) string {
	switch strings.TrimSpace(field.Type) {
	case "string", "ObjectId", "uuid", "url", "enum":
		return expression + ` != ""`
	case "bool", "boolean":
		return expression
	case "date", "datetime", "timestamp":
		return "!" + expression + ".IsZero()"
	default:
		return expression + " != 0"
	}
}

func goFieldName(value string) string {
	value = strings.TrimSpace(value)
	if value == "_id" {
		return "ID"
	}
	if strings.HasSuffix(value, "Id") {
		return upperCamel(value[:len(value)-2]) + "ID"
	}
	return upperCamel(strings.ReplaceAll(value, "_", " "))
}

func lowerGoName(value string) string {
	exported := goFieldName(value)
	if exported == "" {
		return ""
	}
	if strings.HasSuffix(exported, "ID") {
		base := strings.TrimSuffix(exported, "ID")
		if base == "" {
			return "id"
		}
		return strings.ToLower(base[:1]) + base[1:] + "ID"
	}
	return strings.ToLower(exported[:1]) + exported[1:]
}

func upperCamel(value string) string {
	parts := strings.FieldsFunc(value, func(current rune) bool {
		return current == '_' || current == '-' || current == '.' ||
			current == '/' || unicode.IsSpace(current)
	})
	var result strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		runes := []rune(part)
		result.WriteRune(unicode.ToUpper(runes[0]))
		result.WriteString(string(runes[1:]))
	}
	return result.String()
}

func enumConstName(typeName, wireValue string) string {
	return typeName + upperCamel(wireValue)
}

func goStringSlice(values []string) string {
	if len(values) == 0 {
		return "nil"
	}
	var output strings.Builder
	output.WriteString("[]string{")
	for index, value := range values {
		if index != 0 {
			output.WriteString(", ")
		}
		output.WriteString(strconv.Quote(value))
	}
	output.WriteString("}")
	return output.String()
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func writeCanonicalGoOutput(path string, contents string, check bool) error {
	formatted, err := format.Source([]byte(contents))
	if err != nil {
		return fmt.Errorf("gofmt %s: %w", path, err)
	}
	if check {
		current, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read generated output %s: %w", path, err)
		}
		if !bytes.Equal(current, formatted) {
			return fmt.Errorf("generated output is stale: %s", path)
		}
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(path, formatted, 0o644); err != nil {
		return err
	}
	return nil
}
