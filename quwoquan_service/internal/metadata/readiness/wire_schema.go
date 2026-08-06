package readiness

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const (
	maxBundleDocumentBytes   = 32 << 20
	maxReceiptDocumentBytes  = 1 << 20
	maxSnapshotDocumentBytes = 1 << 20
	maxSchemaDocumentBytes   = 4 << 20
)

type wireSchema struct {
	name     string
	compiled *jsonschema.Schema
}

// WireSchemas is the single runtime projection of the canonical readiness
// schemas. Production evaluators and signed receipt resolvers require this set;
// typed decoding alone is deliberately insufficient.
type WireSchemas struct {
	bundle          wireSchema
	journeyBundle   wireSchema
	receipt         wireSchema
	journeyReceipt  wireSchema
	currentSnapshot wireSchema
}

func LoadWireSchemas(metadataDir string) (*WireSchemas, error) {
	metadataRoot, metadataInfo, schemaRoot, schemaInfo, err := stableSchemaRoots(metadataDir)
	if err != nil {
		return nil, err
	}
	load := func(name string) (wireSchema, error) {
		path := filepath.Join(schemaRoot, name+".schema.json")
		data, err := ReadStableRegularFile(path, maxSchemaDocumentBytes)
		if err != nil {
			return wireSchema{}, fmt.Errorf("read %s schema: %w", name, err)
		}
		document, err := decodeUniqueJSON(data)
		if err != nil {
			return wireSchema{}, fmt.Errorf("decode %s schema: %w", name, err)
		}
		compiler := jsonschema.NewCompiler()
		if err := compiler.AddResource(path, document); err != nil {
			return wireSchema{}, fmt.Errorf("register %s schema: %w", name, err)
		}
		compiled, err := compiler.Compile(path)
		if err != nil {
			return wireSchema{}, fmt.Errorf("compile %s schema: %w", name, err)
		}
		return wireSchema{name: name, compiled: compiled}, nil
	}
	bundle, err := load("readiness_result_bundle")
	if err != nil {
		return nil, err
	}
	journeyBundle, err := load("journey_readiness_result_bundle")
	if err != nil {
		return nil, err
	}
	receipt, err := load("readiness_receipt")
	if err != nil {
		return nil, err
	}
	journeyReceipt, err := load("journey_readiness_receipt")
	if err != nil {
		return nil, err
	}
	currentSnapshot, err := load("readiness_current_snapshot")
	if err != nil {
		return nil, err
	}
	if err := verifyStableSchemaRoots(
		metadataRoot, metadataInfo, schemaRoot, schemaInfo,
	); err != nil {
		return nil, err
	}
	return &WireSchemas{
		bundle:          bundle,
		journeyBundle:   journeyBundle,
		receipt:         receipt,
		journeyReceipt:  journeyReceipt,
		currentSnapshot: currentSnapshot,
	}, nil
}

func stableSchemaRoots(metadataDir string) (string, os.FileInfo, string, os.FileInfo, error) {
	if metadataDir == "" {
		return "", nil, "", nil, fmt.Errorf("metadata schema root is required")
	}
	metadataRoot, err := filepath.Abs(metadataDir)
	if err != nil {
		return "", nil, "", nil, fmt.Errorf("resolve metadata schema root: %w", err)
	}
	metadataInfo, err := os.Lstat(metadataRoot)
	if err != nil || metadataInfo.Mode()&os.ModeSymlink != 0 || !metadataInfo.IsDir() {
		return "", nil, "", nil, fmt.Errorf("metadata schema root must be a stable directory")
	}
	schemaRoot := filepath.Join(metadataRoot, "_schemas")
	schemaInfo, err := os.Lstat(schemaRoot)
	if err != nil || schemaInfo.Mode()&os.ModeSymlink != 0 || !schemaInfo.IsDir() {
		return "", nil, "", nil, fmt.Errorf("canonical _schemas root must be a stable directory")
	}
	return metadataRoot, metadataInfo, schemaRoot, schemaInfo, nil
}

func verifyStableSchemaRoots(
	metadataRoot string,
	metadataInfo os.FileInfo,
	schemaRoot string,
	schemaInfo os.FileInfo,
) error {
	currentMetadata, err := os.Lstat(metadataRoot)
	if err != nil || currentMetadata.Mode()&os.ModeSymlink != 0 ||
		!currentMetadata.IsDir() || !os.SameFile(metadataInfo, currentMetadata) {
		return fmt.Errorf("metadata schema root changed while loading")
	}
	currentSchemas, err := os.Lstat(schemaRoot)
	if err != nil || currentSchemas.Mode()&os.ModeSymlink != 0 ||
		!currentSchemas.IsDir() || !os.SameFile(schemaInfo, currentSchemas) {
		return fmt.Errorf("canonical _schemas root changed while loading")
	}
	return nil
}

func (schemas *WireSchemas) DecodeBundle(reader io.Reader) (ReadinessResultBundle, error) {
	data, err := validateWireReader(schemas, schemas.bundle, reader, maxBundleDocumentBytes)
	if err != nil {
		return ReadinessResultBundle{}, err
	}
	return decodeBundleBytes(data)
}

func (schemas *WireSchemas) DecodeJourneyBundle(reader io.Reader) (JourneyReadinessResultBundle, error) {
	data, err := validateWireReader(schemas, schemas.journeyBundle, reader, maxBundleDocumentBytes)
	if err != nil {
		return JourneyReadinessResultBundle{}, err
	}
	return decodeJourneyBundleBytes(data)
}

func (schemas *WireSchemas) DecodeReceipt(reader io.Reader) (ReadinessReceipt, []byte, error) {
	data, err := validateWireReader(schemas, schemas.receipt, reader, maxReceiptDocumentBytes)
	if err != nil {
		return ReadinessReceipt{}, nil, err
	}
	receipt, err := decodeReceiptBytes(data)
	return receipt, data, err
}

func (schemas *WireSchemas) DecodeJourneyReceipt(reader io.Reader) (JourneyReadinessReceipt, []byte, error) {
	data, err := validateWireReader(schemas, schemas.journeyReceipt, reader, maxReceiptDocumentBytes)
	if err != nil {
		return JourneyReadinessReceipt{}, nil, err
	}
	receipt, err := decodeJourneyReceiptBytes(data)
	return receipt, data, err
}

func (schemas *WireSchemas) ValidateCurrentSnapshot(data []byte) error {
	if len(data) == 0 || len(data) > maxSnapshotDocumentBytes {
		return fmt.Errorf("current snapshot document size is invalid")
	}
	return schemas.validate(schemas.currentSnapshot, data)
}

func validateWireReader(
	schemas *WireSchemas,
	schema wireSchema,
	reader io.Reader,
	limit int64,
) ([]byte, error) {
	if schemas == nil || schema.compiled == nil {
		return nil, fmt.Errorf("readiness wire schema authority is required")
	}
	data, err := io.ReadAll(io.LimitReader(reader, limit+1))
	if err != nil {
		return nil, fmt.Errorf("read %s document: %w", schema.name, err)
	}
	if len(data) == 0 || int64(len(data)) > limit {
		return nil, fmt.Errorf("%s document size is invalid", schema.name)
	}
	if err := schemas.validate(schema, data); err != nil {
		return nil, err
	}
	return data, nil
}

func (schemas *WireSchemas) validate(schema wireSchema, data []byte) error {
	if schemas == nil || schema.compiled == nil {
		return fmt.Errorf("readiness wire schema authority is required")
	}
	instance, err := decodeUniqueJSON(data)
	if err != nil {
		return fmt.Errorf("decode %s schema instance: %w", schema.name, err)
	}
	if err := schema.compiled.Validate(instance); err != nil {
		return fmt.Errorf("validate %s schema: %w", schema.name, err)
	}
	return nil
}

// RejectDuplicateJSONKeys applies the same no-last-write-wins rule to signed
// trust envelopes and keyrings that do not themselves have a business wire
// schema. Callers still perform their closed typed decode afterwards.
func RejectDuplicateJSONKeys(data []byte) error {
	_, err := decodeUniqueJSON(data)
	return err
}

// decodeUniqueJSON builds the schema instance while rejecting duplicate object
// keys at every depth. encoding/json's normal last-write-wins behavior is not
// acceptable for signed readiness identities.
func decodeUniqueJSON(data []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := decodeUniqueJSONValue(decoder)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("trailing JSON document")
		}
		return nil, fmt.Errorf("trailing JSON content: %w", err)
	}
	return value, nil
}

func decodeUniqueJSONValue(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	delimiter, isDelimiter := token.(json.Delim)
	if !isDelimiter {
		return token, nil
	}
	switch delimiter {
	case '{':
		object := map[string]any{}
		for decoder.More() {
			keyToken, err := decoder.Token()
			if err != nil {
				return nil, err
			}
			key, ok := keyToken.(string)
			if !ok {
				return nil, fmt.Errorf("object key is not a string")
			}
			if _, duplicate := object[key]; duplicate {
				return nil, fmt.Errorf("duplicate object key %q", key)
			}
			value, err := decodeUniqueJSONValue(decoder)
			if err != nil {
				return nil, err
			}
			object[key] = value
		}
		closing, err := decoder.Token()
		if err != nil || closing != json.Delim('}') {
			return nil, fmt.Errorf("object is not closed")
		}
		return object, nil
	case '[':
		array := []any{}
		for decoder.More() {
			value, err := decodeUniqueJSONValue(decoder)
			if err != nil {
				return nil, err
			}
			array = append(array, value)
		}
		closing, err := decoder.Token()
		if err != nil || closing != json.Delim(']') {
			return nil, fmt.Errorf("array is not closed")
		}
		return array, nil
	default:
		return nil, fmt.Errorf("unexpected JSON delimiter %q", delimiter)
	}
}
