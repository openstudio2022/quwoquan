package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
	readinesstrust "quwoquan_service/internal/metadata/readiness/trust"
)

const (
	maxGraphInputBytes  = 128 << 20
	maxBundleInputBytes = 32 << 20
	maxTrustInputBytes  = 4 << 20
)

type options struct {
	graphPath       string
	bundlePath      string
	snapshotPath    string
	snapshotKeyring string
	runnerKeyring   string
	receiptRoot     string
	evidenceRoot    string
	metadataDir     string
}

type fatalResult struct {
	CommercialReady bool   `json:"commercialReady"`
	Error           string `json:"error"`
}

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdout))
}

// run returns 0 only for a commercial-ready closure, 1 for a complete but
// blocked evaluation, and 2 for malformed/missing trust inputs. Every path
// emits exactly one JSON document to stdout.
func run(ctx context.Context, args []string, stdout io.Writer) int {
	closure, err := evaluate(ctx, args)
	if err != nil {
		_ = writeJSON(stdout, fatalResult{
			CommercialReady: false, Error: err.Error(),
		})
		return 2
	}
	if err := writeJSON(stdout, closure); err != nil {
		return 2
	}
	if !closure.CommercialReady {
		return 1
	}
	return 0
}

func evaluate(ctx context.Context, args []string) (readiness.ClosureResult, error) {
	configuration, err := parseOptions(args)
	if err != nil {
		return readiness.ClosureResult{}, err
	}
	graphBytes, err := readiness.ReadStableRegularFile(
		configuration.graphPath, maxGraphInputBytes,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("read current ContractGraph: %w", err)
	}
	current, err := decodeGraph(graphBytes)
	if err != nil {
		return readiness.ClosureResult{}, err
	}
	schemas, err := readiness.LoadWireSchemas(configuration.metadataDir)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("load readiness wire schemas: %w", err)
	}
	snapshotBytes, err := readiness.ReadStableRegularFile(
		configuration.snapshotPath, maxTrustInputBytes,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("read signed current snapshot: %w", err)
	}
	snapshotKeyringBytes, err := readiness.ReadStableRegularFile(
		configuration.snapshotKeyring, maxTrustInputBytes,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("read snapshot keyring: %w", err)
	}
	snapshotProvider, err := readinesstrust.NewSignedSnapshotProvider(
		snapshotBytes, snapshotKeyringBytes, schemas,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("initialize current snapshot trust: %w", err)
	}
	runnerKeyringBytes, err := readiness.ReadStableRegularFile(
		configuration.runnerKeyring, maxTrustInputBytes,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("read runner keyring: %w", err)
	}
	receiptResolver, err := readinesstrust.NewSignedReceiptResolver(
		configuration.receiptRoot, configuration.evidenceRoot, runnerKeyringBytes, schemas,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("initialize receipt trust: %w", err)
	}
	bundle, err := readiness.ReadStableRegularFile(
		configuration.bundlePath, maxBundleInputBytes,
	)
	if err != nil {
		return readiness.ClosureResult{}, fmt.Errorf("read readiness result bundle: %w", err)
	}
	return readiness.NewEvaluator(snapshotProvider, receiptResolver, schemas).EvaluateJSON(
		ctx, current, bytes.NewReader(bundle),
	), nil
}

func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("evaluate-readiness", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var result options
	flags.StringVar(&result.graphPath, "graph", "", "current ContractGraph JSON")
	flags.StringVar(&result.bundlePath, "bundle", "", "readiness result bundle JSON")
	flags.StringVar(&result.snapshotPath, "snapshot", "", "signed current snapshot JSON")
	flags.StringVar(&result.snapshotKeyring, "snapshot-keyring", "", "trusted snapshot public-key keyring JSON")
	flags.StringVar(&result.runnerKeyring, "runner-keyring", "", "trusted runner public-key keyring JSON")
	flags.StringVar(&result.receiptRoot, "receipt-root", "", "restricted readiness receipt root")
	flags.StringVar(&result.evidenceRoot, "evidence-root", "", "restricted content-addressed evidence root")
	flags.StringVar(&result.metadataDir, "metadata-dir", "", "canonical metadata directory containing readiness schemas")
	if err := flags.Parse(args); err != nil {
		return options{}, err
	}
	if flags.NArg() != 0 {
		return options{}, errors.New("positional arguments are forbidden")
	}
	for name, value := range map[string]string{
		"--graph": result.graphPath, "--bundle": result.bundlePath,
		"--snapshot": result.snapshotPath, "--snapshot-keyring": result.snapshotKeyring,
		"--runner-keyring": result.runnerKeyring, "--receipt-root": result.receiptRoot,
		"--evidence-root": result.evidenceRoot,
		"--metadata-dir":  result.metadataDir,
	} {
		if value == "" {
			return options{}, fmt.Errorf("%s is required", name)
		}
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

func writeJSON(writer io.Writer, value any) error {
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}
