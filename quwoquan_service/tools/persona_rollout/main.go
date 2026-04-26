package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	personarollout "quwoquan_service/runtime/persona"
)

func main() {
	inputPath := flag.String("input", "", "path to rollout input json")
	switchLatencyMs := flag.Float64("switch-latency-ms", 0, "observed persona switch latency in milliseconds")
	flag.Parse()

	if *inputPath == "" {
		exitWithError(fmt.Errorf("missing --input"))
	}

	body, err := os.ReadFile(*inputPath)
	if err != nil {
		exitWithError(fmt.Errorf("read input: %w", err))
	}

	var input personarollout.Input
	if err := json.Unmarshal(body, &input); err != nil {
		exitWithError(fmt.Errorf("parse input: %w", err))
	}

	plan := personarollout.BuildMigrationPlan(input)
	report := personarollout.ValidatePlan(plan, input)
	out, err := personarollout.BuildReportJSON(plan, report, *switchLatencyMs)
	if err != nil {
		exitWithError(fmt.Errorf("marshal report: %w", err))
	}

	_, _ = os.Stdout.Write(out)
	_, _ = os.Stdout.WriteString("\n")
}

func exitWithError(err error) {
	_, _ = fmt.Fprintf(os.Stderr, "persona rollout error: %v\n", err)
	os.Exit(1)
}
