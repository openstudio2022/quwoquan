package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"quwoquan_service/internal/metadata/storagecontract"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("storage-contract-view", flag.ContinueOnError)
	flags.SetOutput(io.Discard)

	var inputPath string
	flags.StringVar(&inputPath, "input", "", "canonical storage.yaml path")
	if err := flags.Parse(args); err != nil {
		return fail(stderr, "parse arguments: %v", err)
	}
	if flags.NArg() != 0 {
		return fail(stderr, "positional arguments are forbidden")
	}
	if inputPath == "" {
		return fail(stderr, "--input is required")
	}

	inputPath = filepath.Clean(inputPath)
	if filepath.Base(inputPath) != "storage.yaml" {
		return fail(stderr, "--input must name storage.yaml")
	}
	data, err := os.ReadFile(inputPath)
	if err != nil {
		return fail(stderr, "read %s: %v", inputPath, err)
	}
	document, err := storagecontract.DecodeYAML(data)
	if err != nil {
		return fail(stderr, "decode canonical storage %s: %v", inputPath, err)
	}
	payload, err := json.MarshalIndent(document, "", "  ")
	if err != nil {
		return fail(stderr, "encode canonical storage view: %v", err)
	}
	payload = append(payload, '\n')
	if _, err := stdout.Write(payload); err != nil {
		return fail(stderr, "write canonical storage view: %v", err)
	}
	return 0
}

func fail(stderr io.Writer, format string, args ...any) int {
	_, _ = fmt.Fprintf(stderr, "storage-contract-view: "+format+"\n", args...)
	return 2
}
