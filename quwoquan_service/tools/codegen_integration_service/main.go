// codegen_integration_service 从 integration 域 metadata 生成 integration-service
// 的领域 Go 产物与跨服务 client path 常量：
//   - services/integration-service/internal/generated/errors.go
//     （location + external_interaction + push_delivery errors 按 code 去重合并）
//   - services/integration-service/internal/generated/external_interaction_metadata.go
//     （external_interaction api_routes path 常量）
//   - generated/serviceclients/integration_paths.g.go
//     （integration path + user DeviceRegistration PushEndpoint 内部 path/scope）
package main

import (
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
	Method        string `yaml:"method"`
	Path          string `yaml:"path"`
	Operation     string `yaml:"operation"`
	Authorization struct {
		Scopes []string `yaml:"scopes"`
	} `yaml:"authorization"`
}

type serviceRoutesFile struct {
	APIRoutes []apiRoute `yaml:"api_routes"`
}

type upstreamReference struct {
	Owner     string `yaml:"owner"`
	Operation string `yaml:"operation"`
}

type pushDeliveryServiceFile struct {
	Service struct {
		Upstreams struct {
			UserPushEndpointSecret     upstreamReference `yaml:"user_push_endpoint_secret"`
			UserPushEndpointInvalidate upstreamReference `yaml:"user_push_endpoint_invalidate"`
		} `yaml:"upstreams"`
	} `yaml:"service"`
}

func main() {
	var metadataDir string
	var outputDir string
	var sharedDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/integration-service/internal", "integration-service internal output directory")
	flag.StringVar(&sharedDir, "shared-dir", "generated/serviceclients", "cross-service client constants output directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}

	merged, err := mergeErrors(source,
		"integration/location/errors.yaml",
		"integration/external_interaction/errors.yaml",
		"integration/push_delivery/errors.yaml",
	)
	if err != nil {
		exitErr(err)
	}
	errorsRendered := contractcodegen.RenderGoErrorsFile(merged, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_integration_service",
		SourcePath:   "integration/{location,external_interaction,push_delivery}/errors.yaml",
		CommentLines: []string{"Integration error sentinels and helpers merged across location,", "external_interaction and push_delivery. user_message from errors.yaml user_message.zh."},
		ExtraImports: []string{"context"},
		Trailer: `// IsTimeout returns true if err is context.DeadlineExceeded or contains upstream timeout semantics.
func IsTimeout(err error) bool {
	return errors.Is(err, context.DeadlineExceeded)
}
`,
	})
	writeGoFile(filepath.Join(outputDir, "generated", "errors.go"), errorsRendered)

	var routes serviceRoutesFile
	const routesSource = "integration/external_interaction/service.yaml"
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
	const pushRoutesSource = "integration/push_delivery/service.yaml"
	if err := source.Decode(pushRoutesSource, &pushRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", pushRoutesSource, err))
	}
	secretRef := pushRoutes.Service.Upstreams.UserPushEndpointSecret
	invalidateRef := pushRoutes.Service.Upstreams.UserPushEndpointInvalidate
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
	const userRoutesSource = "user/device_registration/service.yaml"
	if err := source.Decode(userRoutesSource, &userRoutes); err != nil {
		exitErr(fmt.Errorf("load %s: %w", userRoutesSource, err))
	}
	secretRoute := requiredRoute(
		userRoutesSource,
		userRoutes.APIRoutes,
		secretRef.Operation,
		"GET",
	)
	invalidateRoute := requiredRoute(
		userRoutesSource,
		userRoutes.APIRoutes,
		invalidateRef.Operation,
		"POST",
	)
	secretScope := requiredSingleScope(userRoutesSource, secretRoute)
	invalidateScope := requiredSingleScope(userRoutesSource, invalidateRoute)

	var service strings.Builder
	service.WriteString("// Code generated by tools/codegen_integration_service from " + routesSource + ". DO NOT EDIT.\n")
	service.WriteString("package generated\n\n")
	service.WriteString("// ExternalInteraction transport paths from api_routes.\n")
	service.WriteString("const (\n")
	service.WriteString(fmt.Sprintf("\tExternalRequestsPath = %q\n", pathByOperation["SubmitExternalInteractionRequest"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestByIDPathTemplate = %q\n", pathByOperation["GetExternalInteractionRequest"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestAttemptsPathTemplate = %q\n", pathByOperation["ListExternalInteractionAttempts"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestDeadLettersPath = %q\n", pathByOperation["ListExternalInteractionDeadLetters"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestDeadLetterRecoverPath = %q\n", pathByOperation["RecoverExternalInteractionDeadLetter"]))
	service.WriteString(fmt.Sprintf("\tExternalRequestMetricsSnapshotPath = %q\n", pathByOperation["GetExternalInteractionMetricsSnapshot"]))
	service.WriteString(")\n")
	writeGoFile(filepath.Join(outputDir, "generated", "external_interaction_metadata.go"), service.String())

	var client strings.Builder
	client.WriteString("// Code generated by tools/codegen_integration_service from " + routesSource + " and " + userRoutesSource + ". DO NOT EDIT.\n")
	client.WriteString("package serviceclients\n\n")
	client.WriteString("// Integration external interaction transport paths for cross-service callers.\n")
	client.WriteString("const (\n")
	client.WriteString(fmt.Sprintf("\tIntegrationExternalRequestsPath = %q\n", pathByOperation["SubmitExternalInteractionRequest"]))
	client.WriteString(")\n\n")
	client.WriteString("// User PushEndpoint internal paths generated from user/device_registration/service.yaml.\n")
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
	writeGoFile(filepath.Join(sharedDir, "integration_paths.g.go"), client.String())
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
		if strings.TrimSpace(route.Path) == "" ||
			!strings.Contains(route.Path, "{endpointRef}") {
			exitErr(fmt.Errorf(
				"%s: operation %s path must contain {endpointRef}",
				sourcePath,
				operation,
			))
		}
		return route
	}
	exitErr(fmt.Errorf("%s: operation %s is required", sourcePath, operation))
	return apiRoute{}
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

func writeGoFile(path string, contents string) {
	formatted, err := format.Source([]byte(contents))
	if err != nil {
		exitErr(fmt.Errorf("gofmt %s: %w", path, err))
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
