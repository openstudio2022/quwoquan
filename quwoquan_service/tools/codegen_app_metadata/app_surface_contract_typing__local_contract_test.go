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

func validateAppSurfaceResponseContract(operation appExposedOperation) error {
	client := operation.ClientContract
	if client == nil {
		return fmt.Errorf("%s has no source-derived client ABI", operation.CanonicalOperationID)
	}

	responseBodyKind := strings.TrimSpace(operation.ResponseBodyKind)
	responseEntity := strings.TrimSpace(operation.ResponseEntity)
	if responseBodyKind == "upgrade" {
		if responseEntity != "" {
			return fmt.Errorf(
				"%s upgrade must not declare response_entity %s",
				operation.CanonicalOperationID,
				responseEntity,
			)
		}
		if client.ResponseType != "void" ||
			client.ResponseDecoder != "decodeEmptyResponse" {
			return fmt.Errorf(
				"%s upgrade client ABI %s/%s must be void/decodeEmptyResponse",
				operation.CanonicalOperationID,
				client.ResponseType,
				client.ResponseDecoder,
			)
		}
		return nil
	}

	if responseEntity == "" {
		if responseBodyKind != "ack" {
			return fmt.Errorf(
				"%s has no response_entity for response_body_kind %s",
				operation.CanonicalOperationID,
				responseBodyKind,
			)
		}
		if client.ResponseType != "void" ||
			client.ResponseDecoder != "decodeEmptyResponse" {
			return fmt.Errorf(
				"%s empty ack client ABI %s/%s must be void/decodeEmptyResponse",
				operation.CanonicalOperationID,
				client.ResponseType,
				client.ResponseDecoder,
			)
		}
		return nil
	}

	expectedDecoder := "decode" + responseEntity
	if client.ResponseType != responseEntity ||
		client.ResponseDecoder != expectedDecoder {
		return fmt.Errorf(
			"%s client ABI %s/%s is not derived from response_entity %s",
			operation.CanonicalOperationID,
			client.ResponseType,
			client.ResponseDecoder,
			responseEntity,
		)
	}
	return nil
}

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
		if responseErr := validateAppSurfaceResponseContract(operation); responseErr != nil {
			failures = append(failures, responseErr.Error())
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

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestAppSurfaceResponseContractDistinguishesJSONAckAndUpgrade(t *testing.T) {
	typed := &appClientContract{
		ResponseType:    "ResponseView",
		ResponseDecoder: "decodeResponseView",
	}
	empty := &appClientContract{
		ResponseType:    "void",
		ResponseDecoder: "decodeEmptyResponse",
	}
	tests := []struct {
		name      string
		operation appExposedOperation
		wantError string
	}{
		{
			name: "object response derives its JSON decoder",
			operation: appExposedOperation{
				CanonicalOperationID: "example.object.Get",
				ResponseBodyKind:     "object",
				ResponseEntity:       "ResponseView",
				ClientContract:       typed,
			},
		},
		{
			name: "ack may carry a typed JSON receipt",
			operation: appExposedOperation{
				CanonicalOperationID: "example.command.Apply",
				ResponseBodyKind:     "ack",
				ResponseEntity:       "ResponseView",
				ClientContract:       typed,
			},
		},
		{
			name: "empty ack uses the canonical void decoder",
			operation: appExposedOperation{
				CanonicalOperationID: "example.command.Report",
				ResponseBodyKind:     "ack",
				ClientContract:       empty,
			},
		},
		{
			name: "upgrade has a typed request descriptor and no JSON response",
			operation: appExposedOperation{
				CanonicalOperationID: "example.connection.Upgrade",
				ResponseBodyKind:     "upgrade",
				ClientContract:       empty,
			},
		},
		{
			name: "object cannot silently lose its response entity",
			operation: appExposedOperation{
				CanonicalOperationID: "example.object.Missing",
				ResponseBodyKind:     "object",
				ClientContract:       empty,
			},
			wantError: "has no response_entity",
		},
		{
			name: "empty ack cannot pretend to decode JSON",
			operation: appExposedOperation{
				CanonicalOperationID: "example.command.Invalid",
				ResponseBodyKind:     "ack",
				ClientContract:       typed,
			},
			wantError: "must be void/decodeEmptyResponse",
		},
		{
			name: "upgrade cannot declare a JSON response entity",
			operation: appExposedOperation{
				CanonicalOperationID: "example.connection.Invalid",
				ResponseBodyKind:     "upgrade",
				ResponseEntity:       "ResponseView",
				ClientContract:       empty,
			},
			wantError: "must not declare response_entity",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := validateAppSurfaceResponseContract(test.operation)
			if test.wantError == "" {
				if err != nil {
					t.Fatal(err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), test.wantError) {
				t.Fatalf("error = %v, want substring %q", err, test.wantError)
			}
		})
	}
}
