package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
)

const (
	maxGraphInputBytes = 128 << 20
	planSchema         = "readiness-execution-plan/v1"
)

type options struct {
	graphPath string
}

type fatalResult struct {
	Error string `json:"error"`
}

// executionPlan is a deterministic projection of graph-authored runner
// responsibilities. It intentionally carries no result, receipt, signature or
// commercial-readiness field: those remain owned by evaluate_readiness.
type executionPlan struct {
	Schema                  string          `json:"schema"`
	ContractGraphSourceHash string          `json:"contractGraphSourceHash"`
	CaseCount               int             `json:"caseCount"`
	ExecutionSlotCount      int             `json:"executionSlotCount"`
	RunnerSourceCount       int             `json:"runnerSourceCount"`
	Slots                   []executionSlot `json:"slots"`
}

type executionSlot struct {
	ObjectID         string                            `json:"objectId"`
	SpecRef          string                            `json:"specRef"`
	CaseID           string                            `json:"caseId"`
	Producer         ast.ReadinessProducer             `json:"producer"`
	Layer            ast.ReadinessLayer                `json:"layer"`
	Target           ast.ReadinessCaseTarget           `json:"target"`
	RunnerSourcePath string                            `json:"runnerSourcePath"`
	SourcePath       string                            `json:"sourcePath"`
	Execution        ast.ReadinessExecutionRequirement `json:"execution"`
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout))
}

// run returns 0 for a valid read-only plan and 2 for malformed input. Every
// path emits exactly one JSON document to stdout.
func run(args []string, stdout io.Writer) int {
	plan, err := buildPlan(args)
	if err != nil {
		_ = writeJSON(stdout, fatalResult{Error: err.Error()})
		return 2
	}
	if err := writeJSON(stdout, plan); err != nil {
		return 2
	}
	return 0
}

func buildPlan(args []string) (executionPlan, error) {
	configuration, err := parseOptions(args)
	if err != nil {
		return executionPlan{}, err
	}
	graphBytes, err := readiness.ReadStableRegularFile(
		configuration.graphPath, maxGraphInputBytes,
	)
	if err != nil {
		return executionPlan{}, fmt.Errorf("read current ContractGraph: %w", err)
	}
	current, err := decodeGraph(graphBytes)
	if err != nil {
		return executionPlan{}, err
	}
	return projectExecutionPlan(current)
}

func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("plan-readiness-execution", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var result options
	flags.StringVar(&result.graphPath, "graph", "", "current ContractGraph JSON")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, errors.New("positional arguments are forbidden")
	}
	if strings.TrimSpace(result.graphPath) == "" {
		return options{}, errors.New("--graph is required")
	}
	return result, nil
}

func decodeGraph(data []byte) (*graph.ContractGraph, error) {
	if err := readiness.RejectDuplicateJSONKeys(data); err != nil {
		return nil, fmt.Errorf("decode current ContractGraph: %w", err)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var current graph.ContractGraph
	if err := decoder.Decode(&current); err != nil {
		return nil, fmt.Errorf("decode current ContractGraph: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, errors.New("decode current ContractGraph: trailing JSON document")
		}
		return nil, fmt.Errorf("decode current ContractGraph trailing content: %w", err)
	}
	return &current, nil
}

func projectExecutionPlan(current *graph.ContractGraph) (executionPlan, error) {
	sourceHash, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		return executionPlan{}, fmt.Errorf("derive ContractGraph source hash: %w", err)
	}
	result := executionPlan{
		Schema:                  planSchema,
		ContractGraphSourceHash: sourceHash,
		CaseCount:               len(current.ReadinessCases),
		Slots:                   make([]executionSlot, 0),
	}
	caseIdentities := map[string]struct{}{}
	slotIdentities := map[string]struct{}{}
	runnerSources := map[string]struct{}{}
	for _, contract := range current.ReadinessCases {
		if err := validateCaseShape(contract); err != nil {
			return executionPlan{}, err
		}
		caseIdentity := strings.Join([]string{
			contract.ObjectID, contract.SpecRef, contract.CaseID,
			string(contract.Producer), string(contract.Layer),
			string(contract.Target.Kind), contract.Target.ID,
			contract.RunnerSourcePath, contract.SourcePath,
		}, "\x00")
		if _, duplicate := caseIdentities[caseIdentity]; duplicate {
			return executionPlan{}, fmt.Errorf(
				"duplicate readiness case identity %q", contract.CaseID,
			)
		}
		caseIdentities[caseIdentity] = struct{}{}
		runnerSources[contract.RunnerSourcePath] = struct{}{}
		for _, execution := range contract.Executions {
			if err := validateExecutionShape(contract.CaseID, execution); err != nil {
				return executionPlan{}, err
			}
			slotIdentity := caseIdentity + "\x00" + strings.Join([]string{
				execution.Environment, execution.Platform, execution.DeviceClass,
				execution.Provider, string(execution.DigestBinding),
			}, "\x00")
			if _, duplicate := slotIdentities[slotIdentity]; duplicate {
				return executionPlan{}, fmt.Errorf(
					"duplicate execution requirement for readiness case %q", contract.CaseID,
				)
			}
			slotIdentities[slotIdentity] = struct{}{}
			result.Slots = append(result.Slots, executionSlot{
				ObjectID: contract.ObjectID, SpecRef: contract.SpecRef,
				CaseID: contract.CaseID, Producer: contract.Producer,
				Layer: contract.Layer, Target: contract.Target,
				RunnerSourcePath: contract.RunnerSourcePath,
				SourcePath:       contract.SourcePath, Execution: execution,
			})
		}
	}
	sort.Slice(result.Slots, func(i, j int) bool {
		return executionSlotKey(result.Slots[i]) < executionSlotKey(result.Slots[j])
	})
	result.ExecutionSlotCount = len(result.Slots)
	result.RunnerSourceCount = len(runnerSources)
	return result, nil
}

func validateCaseShape(contract ast.ReadinessCaseContract) error {
	values := []string{
		contract.ObjectID, contract.SpecRef, contract.CaseID,
		string(contract.Producer), string(contract.Layer),
		string(contract.Target.Kind), contract.Target.ID,
		contract.RunnerSourcePath, contract.SourcePath,
	}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("readiness case %q has an incomplete execution identity", contract.CaseID)
		}
	}
	if len(contract.Executions) == 0 {
		return fmt.Errorf("readiness case %q has no execution requirements", contract.CaseID)
	}
	return nil
}

func validateExecutionShape(caseID string, execution ast.ReadinessExecutionRequirement) error {
	for _, value := range []string{
		execution.Environment, execution.Platform, execution.DeviceClass,
		execution.Provider, string(execution.DigestBinding),
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("readiness case %q has an incomplete execution requirement", caseID)
		}
	}
	return nil
}

func executionSlotKey(slot executionSlot) string {
	return strings.Join([]string{
		slot.ObjectID, slot.CaseID, slot.SpecRef,
		string(slot.Producer), string(slot.Layer),
		string(slot.Target.Kind), slot.Target.ID,
		slot.RunnerSourcePath, slot.SourcePath,
		slot.Execution.Environment, slot.Execution.Platform,
		slot.Execution.DeviceClass, slot.Execution.Provider,
		string(slot.Execution.DigestBinding),
	}, "\x00")
}

func writeJSON(writer io.Writer, value any) error {
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}
