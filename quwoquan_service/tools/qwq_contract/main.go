package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	contractopenapi "quwoquan_service/internal/metadata/openapi"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "qwq-contract:", err)
		os.Exit(1)
	}
}

func run(args []string, stdout io.Writer) error {
	if len(args) == 0 {
		return errors.New(
			"expected validate, generate, check, generate-openapi, check-openapi, coverage or review-object",
		)
	}
	switch args[0] {
	case "validate":
		return runValidate(args[1:], stdout)
	case "generate":
		return runGenerate(args[1:], stdout)
	case "check":
		return runCheck(args[1:], stdout)
	case "generate-openapi":
		return runGenerateOpenAPI(args[1:], stdout)
	case "check-openapi":
		return runCheckOpenAPI(args[1:], stdout)
	case "coverage":
		return runCoverage(args[1:], stdout)
	case "review-object":
		return runReviewObject(args[1:], stdout)
	default:
		return fmt.Errorf("unknown command %q", args[0])
	}
}

func runValidate(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("validate", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := registerRepoRoot(flags)
	profileValue := flags.String("profile", string(validate.ProfileCommercial), "baseline or commercial")
	format := flags.String("format", "text", "text, summary or json")
	if err := flags.Parse(args); err != nil {
		return err
	}
	profile, err := parseProfile(*profileValue)
	if err != nil {
		return err
	}
	root, err := resolveRepoRoot(*repoRoot)
	if err != nil {
		return err
	}
	contractGraph, issues, err := compiler.Validate(
		*metadataDir,
		profile,
		load.WithRepoRoot(root),
	)
	if err != nil {
		return err
	}
	if *format == "json" {
		payload := struct {
			Profile string           `json:"profile"`
			Issues  []validate.Issue `json:"issues"`
		}{
			Profile: string(profile),
			Issues:  issues,
		}
		data, marshalErr := json.MarshalIndent(payload, "", "  ")
		if marshalErr != nil {
			return marshalErr
		}
		fmt.Fprintln(stdout, string(data))
	} else if *format == "text" {
		fmt.Fprintf(stdout, "ContractGraph: %d sources, %d documents, %d objects, %d operations, %d projections\n",
			len(contractGraph.Sources), len(contractGraph.Documents), len(contractGraph.Objects), len(contractGraph.Operations), len(contractGraph.Projections))
		for _, current := range issues {
			fmt.Fprintf(stdout, "%s %s: %s\n", current.Code, current.SourcePath, current.Message)
		}
	} else if *format == "summary" {
		counts := map[string]int{}
		for _, current := range issues {
			counts[current.Code]++
		}
		codes := make([]string, 0, len(counts))
		for code := range counts {
			codes = append(codes, code)
		}
		sort.Strings(codes)
		fmt.Fprintf(stdout, "ContractGraph: %d sources, %d documents, %d objects, %d operations, %d projections, %d issues\n",
			len(contractGraph.Sources), len(contractGraph.Documents), len(contractGraph.Objects), len(contractGraph.Operations), len(contractGraph.Projections), len(issues))
		for _, code := range codes {
			fmt.Fprintf(stdout, "%s=%d\n", code, counts[code])
		}
	} else {
		return fmt.Errorf("unsupported format %q", *format)
	}
	if len(issues) > 0 {
		return fmt.Errorf("validation failed with %d issue(s)", len(issues))
	}
	return nil
}

func runGenerate(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("generate", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := registerRepoRoot(flags)
	output := flags.String("output", "", "graph JSON output; stdout when empty")
	goSecurityOutput := flags.String(
		"go-security-output",
		"",
		"generated Go operation security descriptor output",
	)
	profileValue := flags.String("profile", string(validate.ProfileCommercial), "baseline or commercial")
	if err := flags.Parse(args); err != nil {
		return err
	}
	profile, err := parseProfile(*profileValue)
	if err != nil {
		return err
	}
	contractGraph, err := compileAndValidate(*metadataDir, *repoRoot, profile)
	if err != nil {
		return err
	}
	data, err := contractcodegen.MarshalGraph(contractGraph)
	if err != nil {
		return err
	}
	if *output == "" {
		if *goSecurityOutput != "" {
			return errors.New(
				"--go-security-output requires --output for a fixed graph bundle",
			)
		}
		_, err = stdout.Write(data)
		return err
	}
	if err := os.WriteFile(*output, data, 0o644); err != nil {
		return err
	}
	if *goSecurityOutput == "" {
		return nil
	}
	graphDigest := fmt.Sprintf("%x", sha256.Sum256(data))
	securitySource := contractcodegen.RenderOperationSecurityGo(
		contractGraph,
		graphDigest,
	)
	if err := os.MkdirAll(filepath.Dir(*goSecurityOutput), 0o755); err != nil {
		return err
	}
	return os.WriteFile(*goSecurityOutput, securitySource, 0o644)
}

func runCheck(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("check", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := registerRepoRoot(flags)
	input := flags.String("input", "", "generated graph JSON to check")
	profileValue := flags.String("profile", string(validate.ProfileCommercial), "baseline or commercial")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *input == "" {
		return errors.New("--input is required")
	}
	profile, err := parseProfile(*profileValue)
	if err != nil {
		return err
	}
	contractGraph, err := compileAndValidate(*metadataDir, *repoRoot, profile)
	if err != nil {
		return err
	}
	expected, err := contractcodegen.MarshalGraph(contractGraph)
	if err != nil {
		return err
	}
	actual, err := os.ReadFile(*input)
	if err != nil {
		return err
	}
	if !bytes.Equal(expected, actual) {
		return fmt.Errorf("%s is stale; run qwq-contract generate", *input)
	}
	fmt.Fprintf(stdout, "ContractGraph is current: %s\n", *input)
	return nil
}

func runGenerateOpenAPI(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("generate-openapi", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String(
		"metadata-dir",
		"contracts/metadata",
		"metadata root and OpenAPI output root",
	)
	repoRoot := registerRepoRoot(flags)
	if err := flags.Parse(args); err != nil {
		return err
	}
	contractGraph, err := compile(*metadataDir, *repoRoot)
	if err != nil {
		return err
	}
	snapshots, err := contractopenapi.Generate(contractGraph)
	if err != nil {
		return err
	}
	if err := contractopenapi.WriteDirectory(*metadataDir, snapshots); err != nil {
		return err
	}
	operationCount := 0
	for _, snapshot := range snapshots {
		operationCount += snapshot.OperationCount
	}
	fmt.Fprintf(
		stdout,
		"Generated %d OpenAPI snapshot(s) covering %d operation(s)\n",
		len(snapshots),
		operationCount,
	)
	return nil
}

func runCheckOpenAPI(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("check-openapi", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String(
		"metadata-dir",
		"contracts/metadata",
		"metadata root containing generated OpenAPI snapshots",
	)
	repoRoot := registerRepoRoot(flags)
	if err := flags.Parse(args); err != nil {
		return err
	}
	contractGraph, err := compile(*metadataDir, *repoRoot)
	if err != nil {
		return err
	}
	snapshots, err := contractopenapi.Generate(contractGraph)
	if err != nil {
		return err
	}
	drifts, err := contractopenapi.CompareDirectory(*metadataDir, snapshots)
	if err != nil {
		return err
	}
	if len(drifts) != 0 {
		return fmt.Errorf(
			"%s\nrun qwq-contract generate-openapi",
			contractopenapi.FormatDrifts(drifts),
		)
	}
	fmt.Fprintf(
		stdout,
		"OpenAPI snapshots are current: %d domain(s)\n",
		len(snapshots),
	)
	return nil
}

func runCoverage(args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("coverage", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	metadataDir := flags.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := registerRepoRoot(flags)
	format := flags.String("format", "text", "text or json")
	if err := flags.Parse(args); err != nil {
		return err
	}
	contractGraph, err := compile(*metadataDir, *repoRoot)
	if err != nil {
		return err
	}
	coverage := contractGraph.Coverage()
	if *format == "json" {
		data, marshalErr := contractcodegen.MarshalCoverage(coverage)
		if marshalErr != nil {
			return marshalErr
		}
		_, err = stdout.Write(data)
		return err
	}
	if *format != "text" {
		return fmt.Errorf("unsupported format %q", *format)
	}
	fmt.Fprintf(stdout,
		"sources=%d documents=%d objects=%d explicit_object_kinds=%d registered_domains=%d bounded_contexts=%d registered_objects=%d object_relationships=%d operations=%d runtime_entrypoints=%d explicit_operation_kinds=%d bound_operations=%d projections=%d public_operations=%d openapi_operations=%d openapi_matched=%d openapi_orphans=%d readiness_evidence_packets=%d readiness_evidence_objects=%d readiness_modeled=%d readiness_contract_ready=%d readiness_implemented=%d readiness_commercial_ready=%d\n",
		coverage.Sources,
		coverage.Documents,
		coverage.Objects,
		coverage.ExplicitObjectKinds,
		coverage.RegisteredDomains,
		coverage.BoundedContexts,
		coverage.RegisteredObjects,
		coverage.ObjectRelationships,
		coverage.Operations,
		coverage.RuntimeEntrypoints,
		coverage.ExplicitOperationKinds,
		coverage.BoundOperations,
		coverage.Projections,
		coverage.PublicOperations,
		coverage.OpenAPIOperations,
		coverage.OpenAPIMatched,
		coverage.OpenAPIOrphans,
		coverage.ReadinessEvidencePackets,
		coverage.ReadinessEvidenceObjects,
		coverage.ReadinessModeled,
		coverage.ReadinessContractReady,
		coverage.ReadinessImplemented,
		coverage.ReadinessCommercialReady,
	)
	return nil
}

// registerRepoRoot 在每个会走 Load 的子命令上注册 `--repo-root`。`--metadata-dir` 指向
// `scripts/contracts/build_service_contract_view.py` 合成的只含 YAML 的一次性契约视图，
// 里面没有 `internal/**`、`tests/**` 与端侧目录，所以 readinessEvidence 的物理路径只能以
// 仓库根为基准解析。写法与同一个 Makefile 里 codegen_observability_catalog 的
// `--metadata-dir` + `--repo-root` 一致，不引入第二种解析方式。
func registerRepoRoot(flags *flag.FlagSet) *string {
	return flags.String(
		"repo-root",
		"",
		"repository root used to derive readiness evidence from physical paths",
	)
}

// resolveRepoRoot 对缺失的 `--repo-root` fail-closed。静默接受空值会让全仓 readiness 恒为
// 0 条证据、恒停在 contract-ready，看上去只是「运行证据还没接入」，这是最危险的形态。
func resolveRepoRoot(value string) (string, error) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return "", errors.New(
			"--repo-root is required: 未提供 repo-root，无法派生 readinessEvidence" +
				"（--metadata-dir 是只含 YAML 的一次性契约视图，读不到 internal/**、" +
				"tests/** 与端侧目录）",
		)
	}
	absolute, err := filepath.Abs(trimmed)
	if err != nil {
		return "", fmt.Errorf("--repo-root %q: %w", trimmed, err)
	}
	info, err := os.Stat(absolute)
	if err != nil {
		return "", fmt.Errorf("--repo-root %q: %w", trimmed, err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("--repo-root %q is not a directory", trimmed)
	}
	return absolute, nil
}

func compile(metadataDir string, repoRoot string) (*graph.ContractGraph, error) {
	root, err := resolveRepoRoot(repoRoot)
	if err != nil {
		return nil, err
	}
	return compiler.Build(metadataDir, load.WithRepoRoot(root))
}

func compileAndValidate(
	metadataDir string,
	repoRoot string,
	profile validate.Profile,
) (*graph.ContractGraph, error) {
	root, err := resolveRepoRoot(repoRoot)
	if err != nil {
		return nil, err
	}
	return compiler.RequireValid(metadataDir, profile, load.WithRepoRoot(root))
}

func parseProfile(value string) (validate.Profile, error) {
	profile := validate.Profile(value)
	if profile != validate.ProfileBaseline && profile != validate.ProfileCommercial {
		return "", fmt.Errorf("unsupported profile %q", value)
	}
	return profile, nil
}
