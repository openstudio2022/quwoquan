// Command codegen_circle_domain regenerates every circle bounded-context object
// into its service-root generated/<context>/<object>/contract package.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

type circleDomainGenerationPlan struct {
	Name           string
	SourcePath     string
	GenerateModel  bool
	GenerateEvents bool
}

func main() {
	var metadataDir string
	var contractGraphPath string
	var outputDir string
	var sharedDir string
	var check bool
	var checkErrors bool
	var hostAuthorityOnly bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&contractGraphPath, "contract-graph", "", "optional canonical ContractGraph input")
	flag.StringVar(&outputDir, "output-dir", "services/circle-service/generated/circle_management", "circle-service generated context directory")
	flag.StringVar(&sharedDir, "shared-dir", "generated/serviceclients", "cross-service client metadata output directory")
	flag.BoolVar(&check, "check", false, "fail when canonical Circle generated outputs are stale")
	flag.BoolVar(&checkErrors, "check-errors", false, "fail when object-owned Circle error outputs are stale")
	flag.BoolVar(&hostAuthorityOnly, "host-authority-only", false, "generate only the canonical Gathering Host authority owner client")
	flag.Parse()

	source, err := circleCodegenSource(metadataDir, contractGraphPath)
	if err != nil {
		exitErr(err)
	}
	hostAuthorityClientPath := filepath.Join(
		filepath.Clean(sharedDir),
		"hostauthority",
		"owner_authority_clients.g.go",
	)
	gatheringPlanPublicClientPath := filepath.Join(
		filepath.Clean(sharedDir),
		"circlegatheringplan",
		"gathering_plan_service_client.g.go",
	)
	gatheringPlanPrivateClientPath := filepath.Join(
		filepath.Clean(outputDir),
		"gathering_plan",
		"contract",
		"client",
		"gathering_plan_service_client.g.go",
	)
	gatheringPlanPathsPath := filepath.Join(
		filepath.Clean(sharedDir),
		"circle_gathering_plan_paths.g.go",
	)
	if hostAuthorityOnly {
		operationCount, err := generateHostAuthorityOwnerClient(
			source,
			hostAuthorityClientPath,
			check,
		)
		if err != nil {
			exitErr(fmt.Errorf("generate Host authority owner client: %w", err))
		}
		fmt.Printf(
			"codegen_circle_domain: wrote or verified %d Host authority owner operations under %s\n",
			operationCount,
			hostAuthorityClientPath,
		)
		return
	}
	if check || checkErrors {
		generatedErrorObjects, err := generateErrors(source, outputDir, true)
		if err != nil {
			exitErr(fmt.Errorf("verify Circle errors: %w", err))
		}
		if check {
			operationCount, err := generateGatheringServiceClient(
				source,
				filepath.Join(filepath.Clean(sharedDir), "circlegathering", "gathering_service_client.g.go"),
				filepath.Join(filepath.Clean(outputDir), "gathering", "contract", "client", "gathering_service_client.g.go"),
				filepath.Join(filepath.Clean(sharedDir), "circle_paths.g.go"),
				true,
			)
			if err != nil {
				exitErr(fmt.Errorf("verify Gathering service client: %w", err))
			}
			gatheringPlanOperationCount, err := generateGatheringPlanServiceClient(
				source,
				gatheringPlanPublicClientPath,
				gatheringPlanPrivateClientPath,
				gatheringPlanPathsPath,
				true,
			)
			if err != nil {
				exitErr(fmt.Errorf("verify GatheringPlan service client: %w", err))
			}
			hostAuthorityOperationCount, err := generateHostAuthorityOwnerClient(
				source,
				hostAuthorityClientPath,
				true,
			)
			if err != nil {
				exitErr(fmt.Errorf("verify Host authority owner client: %w", err))
			}
			fmt.Printf(
				"codegen_circle_domain: verified %d Gathering operations, %d GatheringPlan operations, %d Host authority owner operations, and %d object-owned error packets\n",
				operationCount,
				gatheringPlanOperationCount,
				hostAuthorityOperationCount,
				generatedErrorObjects,
			)
			return
		}
		fmt.Printf("codegen_circle_domain: verified %d object-owned error packets under %s\n", generatedErrorObjects, outputDir)
		return
	}
	plans, err := circleDomainGenerationPlans(source)
	if err != nil {
		exitErr(fmt.Errorf("derive Circle domain generation plan: %w", err))
	}
	generatedModels := 0
	generatedEvents := 0
	for _, plan := range plans {
		generator := contractcodegen.NewDomainGenerator(
			source,
			filepath.Join(filepath.Clean(outputDir), contractcodegen.CamelToSnake(plan.Name)),
			contractcodegen.WithTypedEnums(),
			contractcodegen.WithSliceEntityRefs(),
			contractcodegen.WithSkipViewEntities(),
			contractcodegen.WithGoFieldIDSuffix(),
			contractcodegen.WithBusinessObjectEntitiesOnly(),
			contractcodegen.WithObjectFirstRoot(),
		)
		if plan.GenerateModel {
			if err := generator.GenerateDomainModel(plan.Name); err != nil {
				exitErr(fmt.Errorf("generate %s model: %w", plan.Name, err))
			}
			generatedModels++
		}
		if plan.GenerateEvents {
			if err := generator.GenerateDomainEvents(plan.Name); err != nil {
				exitErr(fmt.Errorf("generate %s events: %w", plan.Name, err))
			}
			generatedEvents++
		}
	}
	generatedErrorObjects, err := generateErrors(source, outputDir, false)
	if err != nil {
		exitErr(fmt.Errorf("generate Circle errors: %w", err))
	}
	operationCount, err := generateGatheringServiceClient(
		source,
		filepath.Join(filepath.Clean(sharedDir), "circlegathering", "gathering_service_client.g.go"),
		filepath.Join(filepath.Clean(outputDir), "gathering", "contract", "client", "gathering_service_client.g.go"),
		filepath.Join(filepath.Clean(sharedDir), "circle_paths.g.go"),
		false,
	)
	if err != nil {
		exitErr(fmt.Errorf("generate Gathering service client: %w", err))
	}
	gatheringPlanOperationCount, err := generateGatheringPlanServiceClient(
		source,
		gatheringPlanPublicClientPath,
		gatheringPlanPrivateClientPath,
		gatheringPlanPathsPath,
		false,
	)
	if err != nil {
		exitErr(fmt.Errorf("generate GatheringPlan service client: %w", err))
	}
	hostAuthorityOperationCount, err := generateHostAuthorityOwnerClient(
		source,
		hostAuthorityClientPath,
		false,
	)
	if err != nil {
		exitErr(fmt.Errorf("generate Host authority owner client: %w", err))
	}
	fmt.Printf(
		"codegen_circle_domain: wrote %d object models, %d event packets, %d Gathering operations, %d GatheringPlan operations, %d Host authority owner operations, and %d object-owned error packets under %s\n",
		generatedModels,
		generatedEvents,
		operationCount,
		gatheringPlanOperationCount,
		hostAuthorityOperationCount,
		generatedErrorObjects,
		outputDir,
	)
}

func circleDomainGenerationPlans(
	source *contractcodegen.Source,
) ([]circleDomainGenerationPlan, error) {
	if source == nil || source.Graph() == nil {
		return nil, fmt.Errorf("ContractGraph source is required")
	}
	const sourcePrefix = "circle/circle_management/"
	eligibleKinds := map[ast.ObjectKind]struct{}{
		ast.ObjectKindAggregateRoot:     {},
		ast.ObjectKindAppendOnlyFact:    {},
		ast.ObjectKindRuntimeSession:    {},
		ast.ObjectKindExternalReference: {},
	}
	plans := make([]circleDomainGenerationPlan, 0)
	seenNames := make(map[string]string)
	for _, object := range source.Graph().Objects {
		if object.Domain != "circle" ||
			!strings.HasPrefix(object.SourcePath, sourcePrefix) ||
			!strings.HasSuffix(object.SourcePath, "/object.yaml") {
			continue
		}
		if _, eligible := eligibleKinds[object.Kind]; !eligible {
			continue
		}
		objectDir := filepath.ToSlash(filepath.Dir(object.SourcePath))
		fieldsPath := objectDir + "/fields.yaml"
		eventsPath := objectDir + "/events.yaml"
		hasFields := source.Has(fieldsPath)
		hasEvents := source.Has(eventsPath)
		if hasEvents && !hasFields {
			return nil, fmt.Errorf(
				"%s declares events without fields.yaml",
				object.ID,
			)
		}
		if !hasFields {
			continue
		}
		name := strings.TrimSpace(object.Name)
		if name == "" {
			return nil, fmt.Errorf("%s has an empty object name", object.ID)
		}
		if previous, exists := seenNames[name]; exists {
			return nil, fmt.Errorf(
				"Circle generation name %s is shared by %s and %s",
				name,
				previous,
				object.SourcePath,
			)
		}
		seenNames[name] = object.SourcePath
		plans = append(plans, circleDomainGenerationPlan{
			Name:           name,
			SourcePath:     object.SourcePath,
			GenerateModel:  true,
			GenerateEvents: hasEvents,
		})
	}
	sort.Slice(plans, func(left, right int) bool {
		return plans[left].Name < plans[right].Name
	})
	return plans, nil
}

func circleCodegenSource(
	metadataDir string,
	contractGraphPath string,
) (*contractcodegen.Source, error) {
	contractGraphPath = strings.TrimSpace(contractGraphPath)
	if contractGraphPath == "" {
		source, err := contractcodegen.NewSource(
			metadataDir,
			validate.ProfileBaseline,
		)
		if err != nil {
			return nil, fmt.Errorf("compile ContractGraph: %w", err)
		}
		return source, nil
	}
	graphBytes, err := os.ReadFile(contractGraphPath)
	if err != nil {
		return nil, fmt.Errorf(
			"read canonical ContractGraph %s: %w",
			contractGraphPath,
			err,
		)
	}
	var contractGraph graph.ContractGraph
	if err := json.Unmarshal(graphBytes, &contractGraph); err != nil {
		return nil, fmt.Errorf(
			"decode canonical ContractGraph %s: %w",
			contractGraphPath,
			err,
		)
	}
	return contractcodegen.NewSourceFromGraph(
		metadataDir,
		&contractGraph,
	), nil
}

func generateErrors(source *contractcodegen.Source, outputDir string, check bool) (int, error) {
	errorPaths, err := circleObjectErrorPaths(
		source.Paths("circle/circle_management/", "/errors.yaml"),
	)
	if err != nil {
		return 0, err
	}
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(sourcePath, &errorsFile); err != nil {
			return 0, fmt.Errorf("load %s: %w", sourcePath, err)
		}
		rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_circle_domain",
			SourcePath:   sourcePath,
			CommentLines: []string{"Object-owned Circle errors. Transport semantics come from errors.yaml."},
		})
		formatted, err := format.Source([]byte(rendered))
		if err != nil {
			return 0, fmt.Errorf("gofmt generated errors from %s: %w", sourcePath, err)
		}
		outPath := filepath.Join(outputDir, parts[2], "errors.go")
		if check {
			current, err := os.ReadFile(outPath)
			if err != nil {
				return 0, fmt.Errorf("read generated errors %s: %w", outPath, err)
			}
			if string(current) != string(formatted) {
				return 0, fmt.Errorf("generated errors are stale: %s", outPath)
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
			return 0, err
		}
		if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
			return 0, err
		}
	}
	return len(errorPaths), nil
}

func circleObjectErrorPaths(paths []string) ([]string, error) {
	if len(paths) == 0 {
		return nil, fmt.Errorf("Circle metadata has no object-owned errors.yaml")
	}
	result := append([]string(nil), paths...)
	sort.Strings(result)
	for _, sourcePath := range result {
		parts := strings.Split(sourcePath, "/")
		if len(parts) != 4 ||
			parts[0] != "circle" ||
			parts[1] != "circle_management" ||
			strings.TrimSpace(parts[2]) == "" ||
			parts[3] != "errors.yaml" {
			return nil, fmt.Errorf(
				"Circle errors must be owned by exactly one circle_management object: %q",
				sourcePath,
			)
		}
	}
	return result, nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_circle_domain error: %v\n", err)
	os.Exit(1)
}
