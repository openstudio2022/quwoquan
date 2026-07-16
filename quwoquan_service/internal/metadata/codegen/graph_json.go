package codegen

import (
	"bytes"
	"encoding/json"

	"quwoquan_service/internal/metadata/graph"
)

func MarshalGraph(contractGraph *graph.ContractGraph) ([]byte, error) {
	data, err := json.MarshalIndent(contractGraph, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(bytes.TrimSpace(data), '\n'), nil
}

func MarshalCoverage(coverage graph.Coverage) ([]byte, error) {
	data, err := json.MarshalIndent(coverage, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(bytes.TrimSpace(data), '\n'), nil
}
