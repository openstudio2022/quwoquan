package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"path/filepath"
	"strings"

	metadataast "quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

const ownerPersistedQuerySchema = "qwq.object-owned-internal-persisted-graphql"

func deriveOperationBinding(
	source *contractcodegen.Source,
	canonicalOperationID string,
) (operationBinding, error) {
	if source == nil || source.Graph() == nil {
		return operationBinding{}, errors.New("ContractGraph Source is required")
	}
	var matches []metadataast.Operation
	for _, operation := range source.Graph().Operations {
		if operation.ID == canonicalOperationID {
			matches = append(matches, operation)
		}
	}
	if len(matches) == 0 {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s not found in ContractGraph Source",
			canonicalOperationID,
		)
	}
	if len(matches) != 1 {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s has duplicate ContractGraph bindings",
			canonicalOperationID,
		)
	}
	operation := matches[0]
	if !operation.KindExplicit || operation.Kind != metadataast.OperationKindQuery {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s must be an explicit query",
			canonicalOperationID,
		)
	}
	if !operation.Commercial.Explicit || operation.Commercial.Status != "ready" {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s must be commercial ready",
			canonicalOperationID,
		)
	}
	if !objectIDPattern.MatchString(operation.ObjectID) {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s has invalid objectId=%q",
			canonicalOperationID,
			operation.ObjectID,
		)
	}
	authorization := authorizationMetadata{
		Principal:       operation.Principal,
		Scopes:          append([]string(nil), operation.Scopes...),
		OwnershipPolicy: operation.OwnershipPolicy,
	}
	if err := validateAuthorization(&authorization); err != nil {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s authorization: %w",
			canonicalOperationID,
			err,
		)
	}
	sourcePath := filepath.ToSlash(filepath.Clean(operation.SourcePath))
	if sourcePath == "." || filepath.IsAbs(sourcePath) || strings.HasPrefix(sourcePath, "../") {
		return operationBinding{}, fmt.Errorf(
			"canonical operation %s has invalid sourcePath=%q",
			canonicalOperationID,
			operation.SourcePath,
		)
	}
	return operationBinding{
		operationType:  string(operation.Kind),
		objectIDs:      []string{operation.ObjectID},
		authorization:  authorization,
		ownerSourceDir: filepath.ToSlash(filepath.Dir(sourcePath)),
	}, nil
}

func validateOwnerPersistedQuery(
	source *contractcodegen.Source,
	metadata metadataEntry,
	binding operationBinding,
	operationName string,
	document []byte,
) error {
	_, err := loadOwnerPersistedQuery(
		source, metadata, binding, operationName, document,
	)
	return err
}

func loadOwnerPersistedQuery(
	source *contractcodegen.Source,
	metadata metadataEntry,
	binding operationBinding,
	operationName string,
	document []byte,
) (ownerPersistedQueryBinding, error) {
	documentBase := filepath.Base(filepath.FromSlash(metadata.Document))
	if filepath.Ext(documentBase) != ".graphql" {
		return ownerPersistedQueryBinding{}, errors.New("persisted query document must use .graphql")
	}
	bindingBase := strings.TrimSuffix(documentBase, filepath.Ext(documentBase)) + ".yaml"
	bindingPath := filepath.ToSlash(filepath.Join(
		binding.ownerSourceDir,
		"persisted_queries",
		bindingBase,
	))
	var owner ownerPersistedQueryBinding
	if err := source.Graph().DecodeDocument(bindingPath, &owner); err != nil {
		return ownerPersistedQueryBinding{}, fmt.Errorf("load object-owned persisted binding %s: %w", bindingPath, err)
	}
	if owner.Schema != ownerPersistedQuerySchema {
		return ownerPersistedQueryBinding{}, fmt.Errorf("object-owned persisted binding schema=%q", owner.Schema)
	}
	if owner.CanonicalOperationID != metadata.CanonicalOperationID {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding canonicalOperationId drift")
	}
	if len(binding.objectIDs) != 1 || owner.ObjectID != binding.objectIDs[0] {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding objectId drift")
	}
	if owner.Document != documentBase {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding document drift")
	}
	if owner.OperationName != operationName {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding operationName drift")
	}
	if owner.OperationType != binding.operationType {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding operationType drift")
	}
	documentHash := sha256.Sum256(document)
	documentHashHex := hex.EncodeToString(documentHash[:])
	if owner.SHA256Hash != documentHashHex {
		return ownerPersistedQueryBinding{}, errors.New("object-owned persisted binding sha256Hash drift")
	}
	return owner, nil
}
