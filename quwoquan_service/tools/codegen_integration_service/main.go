// codegen_integration_service 从 integration 域 metadata 生成对象级 Go 产物与跨服务
// client path 常量。对象错误与 location metadata 必须输出到各自 generated 目录，
// 禁止聚合后借住 external_interaction。
//   - generated/serviceclients/integration_paths.g.go
//     （integration path + user DeviceRegistration PushEndpoint 内部 path/scope）
package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

type apiRoute struct {
	Method          string `yaml:"method"`
	Path            string `yaml:"path"`
	Operation       string `yaml:"operation"`
	RequestBindings struct {
		Query []struct {
			Name string `yaml:"name"`
		} `yaml:"query"`
	} `yaml:"request_bindings"`
	Authorization struct {
		Scopes []string `yaml:"scopes"`
	} `yaml:"authorization"`
}

type serviceRoutesFile struct {
	ResponseListKey string     `yaml:"response_list_key"`
	APIRoutes       []apiRoute `yaml:"api_routes"`
}

type upstreamReference struct {
	Owner     string `yaml:"owner"`
	Operation string `yaml:"operation"`
}

type pushDeliveryServiceFile struct {
	Upstreams struct {
		UserPushEndpointSecret     upstreamReference `yaml:"user_push_endpoint_secret"`
		UserPushEndpointInvalidate upstreamReference `yaml:"user_push_endpoint_invalidate"`
	} `yaml:"upstreams"`
}

type locationProjectionFile struct {
	Fields []struct {
		Name string `yaml:"name"`
	} `yaml:"fields"`
}

type integrationErrorSource struct {
	Context    string
	Object     string
	SourcePath string
	Comment    string
	Timeout    bool
}

var integrationErrorSources = []integrationErrorSource{
	{
		Context:    "external_integration",
		Object:     "capability_grant",
		SourcePath: "integration/external_integration/capability_grant/errors.yaml",
		Comment:    "CapabilityGrant error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "connector_authorization",
		SourcePath: "integration/external_integration/connector_authorization/errors.yaml",
		Comment:    "ConnectorAuthorization error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "connector_definition",
		SourcePath: "integration/external_integration/connector_definition/errors.yaml",
		Comment:    "ConnectorDefinition error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "connector_connection",
		SourcePath: "integration/external_integration/connector_connection/errors.yaml",
		Comment:    "ConnectorConnection error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "connector_invocation",
		SourcePath: "integration/external_integration/connector_invocation/errors.yaml",
		Comment:    "ConnectorInvocation error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "external_interaction",
		SourcePath: "integration/external_integration/external_interaction/errors.yaml",
		Comment:    "ExternalInteraction error sentinels and helpers. user_message comes from its object errors.yaml.",
		Timeout:    true,
	},
	{
		Context:    "external_integration",
		Object:     "location",
		SourcePath: "integration/external_integration/location/errors.yaml",
		Comment:    "Location error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
	{
		Context:    "external_integration",
		Object:     "push_delivery",
		SourcePath: "integration/external_integration/push_delivery/errors.yaml",
		Comment:    "PushDelivery error sentinels and helpers. user_message comes from its object errors.yaml.",
	},
}

func main() {
	var metadataDir string
	var outputDir string
	var sharedDir string
	var check bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/integration-service/generated", "integration-service generated root directory")
	flag.StringVar(&sharedDir, "shared-dir", "generated/serviceclients", "cross-service client constants output directory")
	flag.BoolVar(&check, "check", false, "fail when generated output is stale")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}

	merged, err := generateObjectErrors(source, outputDir, check)
	if err != nil {
		exitErr(err)
	}

	var routes serviceRoutesFile
	const routesSource = "integration/external_integration/external_interaction/operations.yaml"
	if err := source.Decode(routesSource, &routes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", routesSource, err))
	}
	pathByOperation := map[string]string{}
	for _, route := range routes.APIRoutes {
		operation := strings.TrimSpace(route.Operation)
		path := strings.TrimSpace(route.Path)
		if operation == "" || path == "" {
			continue
		}
		pathByOperation[operation] = path
	}
	required := []string{
		"GetSmsOtpDeliveryReadiness",
		"SubmitExternalInteractionRequest",
		"GetExternalInteractionRequest",
		"ListExternalInteractionAttempts",
		"ListExternalInteractionDeadLetters",
		"RecoverExternalInteractionDeadLetter",
		"GetExternalInteractionMetricsSnapshot",
	}
	for _, operation := range required {
		if pathByOperation[operation] == "" {
			exitErr(fmt.Errorf("%s: operation %q missing api route path", routesSource, operation))
		}
	}
	var pushRoutes pushDeliveryServiceFile
	const pushRoutesSource = "integration/external_integration/push_delivery/operations.yaml"
	if err := source.Decode(pushRoutesSource, &pushRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", pushRoutesSource, err))
	}
	secretRef := pushRoutes.Upstreams.UserPushEndpointSecret
	invalidateRef := pushRoutes.Upstreams.UserPushEndpointInvalidate
	validateUpstreamReference(
		pushRoutesSource,
		secretRef,
		"user.DeviceRegistration",
		"ResolvePushEndpointSecret",
	)
	validateUpstreamReference(
		pushRoutesSource,
		invalidateRef,
		"user.DeviceRegistration",
		"InvalidateDevicePushEndpoint",
	)
	var userRoutes serviceRoutesFile
	const userRoutesSource = "user/account/device_registration/operations.yaml"
	if err := source.Decode(userRoutesSource, &userRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", userRoutesSource, err))
	}
	secretRoute := requiredRouteWithPathParameter(
		userRoutesSource,
		userRoutes.APIRoutes,
		secretRef.Operation,
		"GET",
		"endpointRef",
	)
	invalidateRoute := requiredRouteWithPathParameter(
		userRoutesSource,
		userRoutes.APIRoutes,
		invalidateRef.Operation,
		"POST",
		"endpointRef",
	)
	secretScope := requiredSingleScope(userRoutesSource, secretRoute)
	invalidateScope := requiredSingleScope(userRoutesSource, invalidateRoute)
	var connectorConnectionRoutes serviceRoutesFile
	const connectorConnectionRoutesSource = "integration/external_integration/connector_connection/operations.yaml"
	if err := source.Decode(connectorConnectionRoutesSource, &connectorConnectionRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", connectorConnectionRoutesSource, err))
	}
	connectorGrantRoute := requiredRoute(
		connectorConnectionRoutesSource,
		connectorConnectionRoutes.APIRoutes,
		"ResolveConnectorCapabilityGrant",
		"POST",
	)
	requireExactRoutePath(
		connectorConnectionRoutesSource,
		connectorGrantRoute,
		"/internal/integrations/connector-capability-grants:resolve",
	)
	connectorGrantScope := requiredSingleScope(
		connectorConnectionRoutesSource,
		connectorGrantRoute,
	)

	var service strings.Builder
	service.WriteString("// Code generated by tools/codegen_integration_service from " + routesSource + ". DO NOT EDIT.\n")
	service.WriteString("package generated\n\n")
	service.WriteString("// ExternalInteraction transport paths from api_routes.\n")
	service.WriteString("const (\n")
	service.WriteString(fmt.Sprintf("\tSmsOtpDeliveryReadinessPath = %q\n", pathByOperation["GetSmsOtpDeliveryReadiness"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestsPath = %q\n", pathByOperation["SubmitExternalInteractionRequest"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestByIDPathTemplate = %q\n", pathByOperation["GetExternalInteractionRequest"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestAttemptsPathTemplate = %q\n", pathByOperation["ListExternalInteractionAttempts"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestDeadLettersPath = %q\n", pathByOperation["ListExternalInteractionDeadLetters"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestDeadLetterRecoverPath = %q\n", pathByOperation["RecoverExternalInteractionDeadLetter"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestMetricsSnapshotPath = %q\n", pathByOperation["GetExternalInteractionMetricsSnapshot"]))
	service.WriteString(")\n")
	writeGoFile(
		filepath.Join(outputDir, "external_integration", "external_interaction", "external_interaction_metadata.go"),
		service.String(),
		check,
	)

	var locationRoutes serviceRoutesFile
	const locationRoutesSource = "integration/external_integration/location/operations.yaml"
	if err := source.Decode(locationRoutesSource, &locationRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", locationRoutesSource, err))
	}
	var locationProjection locationProjectionFile
	const locationProjectionSource = "integration/external_integration/location/projections/location_poi.yaml"
	if err := source.Decode(locationProjectionSource, &locationProjection); err != nil {
		exitErr(fmt.Errorf("load %s: %w", locationProjectionSource, err))
	}
	var locationRouteProjection locationProjectionFile
	const locationRouteProjectionSource = "integration/external_integration/location/projections/location_route.yaml"
	if err := source.Decode(
		locationRouteProjectionSource,
		&locationRouteProjection,
	); err != nil {
		exitErr(fmt.Errorf("load %s: %w", locationRouteProjectionSource, err))
	}
	writeGoFile(
		filepath.Join(outputDir, "external_integration", "location", "location_metadata.go"),
		renderLocationMetadata(
			locationRoutes,
			locationProjection,
			locationRouteProjection,
			locationRoutesSource,
			locationProjectionSource,
			locationRouteProjectionSource,
		),
		check,
	)

	var client strings.Builder
	client.WriteString("// Code generated by tools/codegen_integration_service from " + routesSource + ", " + connectorConnectionRoutesSource + " and " + userRoutesSource + ". DO NOT EDIT.\n")
	client.WriteString("package serviceclients\n\n")
	client.WriteString("// Integration external interaction transport paths for cross-service callers.\n")
	client.WriteString("const (\n")
	client.WriteString(fmt.Sprintf("\tIntegrationSmsOtpDeliveryReadinessPath = %q\n", pathByOperation["GetSmsOtpDeliveryReadiness"]))
	client.WriteString(fmt.Sprintf("\tIntegrationSmsOtpDeliveryReadinessScope = %q\n", requiredSingleScope(routesSource, requiredRoute(routesSource, routes.APIRoutes, "GetSmsOtpDeliveryReadiness", "GET"))))
	client.WriteString(fmt.Sprintf("\tIntegrationExternalRequestsPath = %q\n", pathByOperation["SubmitExternalInteractionRequest"]))
	client.WriteString(")\n\n")
	client.WriteString("// Connector capability resolution path and scope for trusted service callers.\n")
	client.WriteString("const (\n")
	client.WriteString(fmt.Sprintf("\tIntegrationConnectorCapabilityGrantResolvePath = %q\n", connectorGrantRoute.Path))
	client.WriteString(fmt.Sprintf("\tIntegrationConnectorCapabilityGrantReadScope = %q\n", connectorGrantScope))
	client.WriteString(")\n\n")
	client.WriteString("// User PushEndpoint internal paths generated from user/account/device_registration/operations.yaml.\n")
	client.WriteString("const (\n")
	client.WriteString(fmt.Sprintf("\tUserPushEndpointSecretPathTemplate = %q\n", secretRoute.Path))
	client.WriteString(fmt.Sprintf("\tUserPushEndpointInvalidatePathTemplate = %q\n", invalidateRoute.Path))
	client.WriteString(fmt.Sprintf("\tUserPushEndpointSecretScope = %q\n", secretScope))
	client.WriteString(fmt.Sprintf("\tUserPushEndpointInvalidateScope = %q\n", invalidateScope))
	client.WriteString(")\n\n")
	client.WriteString("// Integration stable error codes consumed by cross-service callers\n")
	client.WriteString("// (from integration errors.yaml; strings are the wire contract).\n")
	client.WriteString("const (\n")
	for _, definition := range merged.Errors {
		if strings.TrimSpace(definition.GoConst) == "" {
			continue
		}
		client.WriteString(fmt.Sprintf(
			"\tIntegration%sCode = %q\n",
			strings.TrimPrefix(definition.GoConst, "Err"),
			definition.Code,
		))
	}
	client.WriteString(")\n")
	writeGoFile(filepath.Join(sharedDir, "integration_paths.g.go"), client.String(), check)
}

func generateObjectErrors(
	source *contractcodegen.Source,
	outputDir string,
	check bool,
) (*contractcodegen.ErrorsFile, error) {
	paths := make([]string, 0, len(integrationErrorSources))
	for _, item := range integrationErrorSources {
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(item.SourcePath, &errorsFile); err != nil {
			return nil, fmt.Errorf("load %s: %w", item.SourcePath, err)
		}
		options := contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_integration_service",
			SourcePath:   item.SourcePath,
			CommentLines: []string{item.Comment},
		}
		if item.Timeout {
			options.ExtraImports = []string{"context"}
			options.Trailer = `// IsTimeout reports context deadline exhaustion for provider calls.
func IsTimeout(err error) bool {
	return errors.Is(err, context.DeadlineExceeded)
}
`
		}
		writeGoFile(
			filepath.Join(outputDir, item.Context, item.Object, "errors.go"),
			contractcodegen.RenderGoErrorsFile(&errorsFile, options),
			check,
		)
		paths = append(paths, item.SourcePath)
	}
	return mergeErrors(source, paths...)
}

func renderLocationMetadata(
	routes serviceRoutesFile,
	poiProjection locationProjectionFile,
	routeProjection locationProjectionFile,
	routesSource string,
	poiProjectionSource string,
	routeProjectionSource string,
) string {
	pathByOperation := map[string]string{}
	queryParams := []string{}
	seenParams := map[string]bool{}
	for _, route := range routes.APIRoutes {
		pathByOperation[strings.TrimSpace(route.Operation)] = strings.TrimSpace(route.Path)
		for _, binding := range route.RequestBindings.Query {
			parameter := strings.TrimSpace(binding.Name)
			if parameter != "" && !seenParams[parameter] {
				seenParams[parameter] = true
				queryParams = append(queryParams, parameter)
			}
		}
	}
	for _, operation := range []string{
		"GetNearbyLocations",
		"SearchLocations",
		"ReadLocationRoute",
	} {
		if pathByOperation[operation] == "" {
			exitErr(fmt.Errorf("%s: operation %q missing api route path", routesSource, operation))
		}
	}
	var output strings.Builder
	output.WriteString("// Code generated by tools/codegen_integration_service from " +
		routesSource + ", " + poiProjectionSource + " and " +
		routeProjectionSource + ". DO NOT EDIT.\n")
	output.WriteString("package generated\n\n")
	output.WriteString("// Location transport metadata belongs to integration.external_integration.location.\n")
	responseKey := strings.TrimSpace(routes.ResponseListKey)
	if responseKey == "" {
		responseKey = "items"
	}
	output.WriteString(fmt.Sprintf("const ResponseListKey = %q\n\n", responseKey))
	output.WriteString("// API paths from operations.yaml.\n")
	output.WriteString(fmt.Sprintf("const NearbyPath = %q\n", pathByOperation["GetNearbyLocations"]))
	output.WriteString(fmt.Sprintf("const SearchPath = %q\n", pathByOperation["SearchLocations"]))
	output.WriteString(fmt.Sprintf("const RoutePath = %q\n\n", pathByOperation["ReadLocationRoute"]))
	output.WriteString("// Query parameter names from operations.yaml.\n")
	for _, parameter := range queryParams {
		output.WriteString(fmt.Sprintf("const QueryParam%s = %q\n", exportedName(parameter), parameter))
	}
	output.WriteString("\n// Location client projection field keys.\n")
	seenFields := map[string]bool{}
	for _, projection := range []locationProjectionFile{
		poiProjection,
		routeProjection,
	} {
		for _, field := range projection.Fields {
			name := strings.TrimSpace(field.Name)
			if name != "" && !seenFields[name] {
				seenFields[name] = true
				output.WriteString(fmt.Sprintf(
					"const FieldKey%s = %q\n",
					exportedName(name),
					name,
				))
			}
		}
	}
	return output.String()
}

func exportedName(value string) string {
	parts := strings.FieldsFunc(value, func(character rune) bool {
		return character == '_' || character == '-' || character == '.'
	})
	for index, part := range parts {
		if part == "" {
			continue
		}
		parts[index] = strings.ToUpper(part[:1]) + part[1:]
	}
	return strings.Join(parts, "")
}

func validateUpstreamReference(
	sourcePath string,
	reference upstreamReference,
	owner string,
	operation string,
) {
	if strings.TrimSpace(reference.Owner) != owner {
		exitErr(fmt.Errorf(
			"%s: upstream operation %s must be owned by %s",
			sourcePath,
			operation,
			owner,
		))
	}
	if strings.TrimSpace(reference.Operation) != operation {
		exitErr(fmt.Errorf(
			"%s: expected upstream operation %s, got %q",
			sourcePath,
			operation,
			reference.Operation,
		))
	}
}

func requiredRoute(
	sourcePath string,
	routes []apiRoute,
	operation string,
	method string,
) apiRoute {
	for _, route := range routes {
		if strings.TrimSpace(route.Operation) != operation {
			continue
		}
		if strings.TrimSpace(route.Method) != method {
			exitErr(fmt.Errorf(
				"%s: operation %s must use method %s",
				sourcePath,
				operation,
				method,
			))
		}
		if strings.TrimSpace(route.Path) == "" {
			exitErr(fmt.Errorf(
				"%s: operation %s must declare a route path",
				sourcePath,
				operation,
			))
		}
		return route
	}
	exitErr(fmt.Errorf("%s: operation %s is required", sourcePath, operation))
	return apiRoute{}
}

func requiredRouteWithPathParameter(
	sourcePath string,
	routes []apiRoute,
	operation string,
	method string,
	parameter string,
) apiRoute {
	route := requiredRoute(sourcePath, routes, operation, method)
	placeholder := "{" + strings.TrimSpace(parameter) + "}"
	if placeholder == "{}" || !strings.Contains(route.Path, placeholder) {
		exitErr(fmt.Errorf(
			"%s: operation %s path must contain %s",
			sourcePath,
			operation,
			placeholder,
		))
	}
	return route
}

func requireExactRoutePath(sourcePath string, route apiRoute, expected string) {
	if strings.TrimSpace(route.Path) != expected {
		exitErr(fmt.Errorf(
			"%s: operation %s path must be %q",
			sourcePath,
			route.Operation,
			expected,
		))
	}
}

func requiredSingleScope(sourcePath string, route apiRoute) string {
	if len(route.Authorization.Scopes) != 1 ||
		strings.TrimSpace(route.Authorization.Scopes[0]) == "" {
		exitErr(fmt.Errorf(
			"%s: operation %s must declare exactly one service scope",
			sourcePath,
			route.Operation,
		))
	}
	return strings.TrimSpace(route.Authorization.Scopes[0])
}

func mergeErrors(source *contractcodegen.Source, paths ...string) (*contractcodegen.ErrorsFile, error) {
	merged := &contractcodegen.ErrorsFile{Domain: "INTEGRATION"}
	seen := map[string]contractcodegen.ErrorDefinition{}
	for _, path := range paths {
		var file contractcodegen.ErrorsFile
		if err := source.Decode(path, &file); err != nil {
			return nil, fmt.Errorf("load %s: %w", path, err)
		}
		for _, definition := range file.Errors {
			existing, duplicate := seen[definition.Code]
			if duplicate {
				if existing.GoConst != definition.GoConst {
					return nil, fmt.Errorf(
						"error code %s declared with divergent go_const %q vs %q",
						definition.Code, existing.GoConst, definition.GoConst,
					)
				}
				continue
			}
			seen[definition.Code] = definition
			merged.Errors = append(merged.Errors, definition)
		}
	}
	return merged, nil
}

func writeGoFile(path string, contents string, check bool) {
	formatted, err := format.Source([]byte(contents))
	if err != nil {
		exitErr(fmt.Errorf("gofmt %s: %w", path, err))
	}
	if check {
		current, readErr := os.ReadFile(path)
		if readErr != nil {
			exitErr(fmt.Errorf("read generated output %s: %w", path, readErr))
		}
		if !bytes.Equal(current, formatted) {
			exitErr(fmt.Errorf("generated output is stale: %s", path))
		}
		fmt.Printf("codegen_integration_service: verified %s\n", path)
		return
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(path, formatted, 0o644); err != nil {
		exitErr(err)
	}
	fmt.Printf("codegen_integration_service: wrote %s\n", path)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_integration_service error: %v\n", err)
	os.Exit(1)
}
