package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/testsupport/contractsview"
)

// TestEveryAppSurfaceOperationHasOneSourceDerivedTypedOwner proves the source
// inputs accepted by the App generator, without writing any generated file.
// It intentionally includes commercial-blocked operations: readiness controls
// invocation, never whether a typed request/response/error ABI exists.
func TestEveryAppSurfaceOperationHasOneSourceDerivedTypedOwner(t *testing.T) {
	metadataDir := contractsview.Build(t)
	contractGraph, err := compiler.Build(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	activeMetadataSource = contractcodegen.NewSourceFromGraph(
		metadataDir,
		contractGraph,
	)
	activeMetadataRoot = metadataDir

	var surfaces uiSurfacesFile
	if err := activeMetadataSource.Decode("_shared/ui_surfaces.yaml", &surfaces); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(contractGraph.Operations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}
	if len(operations) != len(contractGraph.Operations) {
		t.Fatalf(
			"decoded operations = %d, graph operations = %d",
			len(operations),
			len(contractGraph.Operations),
		)
	}
	byLocalID := map[string][]appExposedOperation{}
	for index := range operations {
		operations[index].CanonicalOperationID = contractGraph.Operations[index].ID
		operations[index].LocalOperationID = contractGraph.Operations[index].LocalID
		localID := operations[index].LocalOperationID
		byLocalID[localID] = append(byLocalID[localID], operations[index])
	}

	references := 0
	unique := map[string]appExposedOperation{}
	var failures []string
	for _, surface := range surfaces.Surfaces {
		seen := map[string]struct{}{}
		for _, localID := range surface.OperationIDs {
			references++
			if _, duplicate := seen[localID]; duplicate {
				failures = append(failures, fmt.Sprintf(
					"surface %s repeats %s",
					surface.ID,
					localID,
				))
				continue
			}
			seen[localID] = struct{}{}
			candidates := byLocalID[localID]
			owned := make([]appExposedOperation, 0, len(candidates))
			for _, candidate := range candidates {
				if candidate.Domain == surface.Owner {
					owned = append(owned, candidate)
				}
			}
			if len(owned) == 1 {
				candidates = owned
			}
			if len(candidates) != 1 {
				candidateIDs := make([]string, 0, len(candidates))
				for _, candidate := range candidates {
					candidateIDs = append(candidateIDs, candidate.CanonicalOperationID)
				}
				sort.Strings(candidateIDs)
				failures = append(failures, fmt.Sprintf(
					"surface %s operation %s has %d owners: %s",
					surface.ID,
					localID,
					len(candidates),
					strings.Join(candidateIDs, ", "),
				))
				continue
			}
			unique[candidates[0].CanonicalOperationID] = candidates[0]
		}
	}

	canonicalEnums, err := loadCanonicalRequestEnumValues()
	if err != nil {
		t.Fatal(err)
	}
	blocked := 0
	operationIDs := make([]string, 0, len(unique))
	for operationID := range unique {
		operationIDs = append(operationIDs, operationID)
	}
	sort.Strings(operationIDs)
	for _, operationID := range operationIDs {
		operation := unique[operationID]
		if operation.Commercial.Status == "blocked" {
			blocked++
		}
		if operation.ClientContract == nil {
			failures = append(failures, operationID+" has no source-derived client ABI")
			continue
		}
		if strings.TrimSpace(operation.RequestEntity) == "" {
			failures = append(failures, operationID+" has no request_entity")
			continue
		}
		if strings.TrimSpace(operation.ResponseEntity) == "" {
			failures = append(failures, operationID+" has no response_entity")
		} else {
			expectedDecoder := "decode" + operation.ResponseEntity
			if operation.ClientContract.ResponseType != operation.ResponseEntity ||
				operation.ClientContract.ResponseDecoder != expectedDecoder {
				failures = append(failures, fmt.Sprintf(
					"%s client ABI %s/%s is not derived from response_entity %s",
					operationID,
					operation.ClientContract.ResponseType,
					operation.ClientContract.ResponseDecoder,
					operation.ResponseEntity,
				))
			}
		}
		if len(operation.ErrorCodes) == 0 {
			failures = append(failures, operationID+" has no canonical error_codes")
		}
		model, _, loadErr := loadOperationRequestModel(
			operation,
			operation.RequestEntity,
		)
		if loadErr != nil {
			failures = append(failures, loadErr.Error())
			continue
		}
		bindings := appRequestBindings{}
		if operation.RequestBindings != nil {
			bindings = *operation.RequestBindings
		}
		for _, validate := range []func() error{
			func() error {
				return validateRequestModelCanonicalEnums(
					operationID,
					model,
					canonicalEnums,
				)
			},
			func() error {
				return validateRequestModelDefaults(operationID, model)
			},
			func() error {
				return validateRequestModelBindings(
					operationID,
					model,
					operation.RequestBodyKind,
					bindings,
					operation.RequestConstants,
				)
			},
		} {
			if validateErr := validate(); validateErr != nil {
				failures = append(failures, validateErr.Error())
			}
		}
	}
	if len(failures) != 0 {
		t.Fatalf(
			"App surface typed contract gaps (%d):\n%s",
			len(failures),
			strings.Join(failures, "\n"),
		)
	}
	t.Logf(
		"App surface typed contracts: surfaces=%d references=%d uniqueOperations=%d blockedIncluded=%d gaps=0",
		len(surfaces.Surfaces),
		references,
		len(unique),
		blocked,
	)
}
