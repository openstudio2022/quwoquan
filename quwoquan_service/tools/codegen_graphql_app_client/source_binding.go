package main

import (
	"errors"
	"fmt"
	"reflect"
	"sort"

	metadataast "quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

func validateContractGraphSource(source *contractcodegen.Source, generated contractGraphDocument, entries map[string]registryEntry) error {
	if source == nil || source.Graph() == nil {
		return errors.New("ContractGraph Source is required")
	}
	operationIDs := []string{gatewayOperationID}
	for _, entry := range entries {
		operationIDs = append(operationIDs, entry.CanonicalOperationID)
	}
	sort.Strings(operationIDs)
	for index, operationID := range operationIDs {
		if index > 0 && operationIDs[index-1] == operationID {
			return fmt.Errorf("signed App bundle canonical operation %s is duplicated", operationID)
		}
		generatedOperation, err := exactGraphOperation(generated.Operations, operationID)
		if err != nil {
			return err
		}
		var matches []metadataast.Operation
		for _, operation := range source.Graph().Operations {
			if operation.ID == operationID {
				matches = append(matches, operation)
			}
		}
		if len(matches) != 1 {
			return fmt.Errorf("ContractGraph Source must contain exactly one %s operation", operationID)
		}
		operation := matches[0]
		if string(operation.Kind) != generatedOperation.Kind || operation.ObjectID != generatedOperation.ObjectID ||
			operation.Method != generatedOperation.Method || operation.PathTemplate != generatedOperation.PathTemplate ||
			sourceMaximumBodyBytes(operation) != generatedOperation.ResponseAdmission.MaximumBodyBytes {
			return fmt.Errorf("generated ContractGraph operation %s differs from ContractGraph Source", operationID)
		}
	}
	generatedProjection, err := exactProjection(generated.Projections, detailProjectionID)
	if err != nil {
		return err
	}
	var matches []metadataast.Projection
	for _, projection := range source.Graph().Projections {
		if projection.ID == detailProjectionID {
			matches = append(matches, projection)
		}
	}
	if len(matches) != 1 {
		return fmt.Errorf("ContractGraph Source must contain exactly one %s projection", detailProjectionID)
	}
	sourceFields := append([]string(nil), matches[0].FieldNames...)
	generatedFields := append([]string(nil), generatedProjection.FieldNames...)
	sort.Strings(sourceFields)
	sort.Strings(generatedFields)
	if !reflect.DeepEqual(sourceFields, generatedFields) {
		return errors.New("generated ContentPostDetailSlice projection differs from ContractGraph Source")
	}
	return nil
}

func sourceMaximumBodyBytes(operation metadataast.Operation) int {
	if operation.ResponseAdmission == nil {
		return 0
	}
	return operation.ResponseAdmission.MaximumBodyBytes
}
