package readiness

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"path/filepath"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// DecodeBundle rejects unknown fields and trailing documents before semantic
// evaluation. This keeps credentials, endpoints and ad-hoc proof payloads out
// of the canonical wire by construction.
func DecodeBundle(reader io.Reader) (ReadinessResultBundle, error) {
	data, err := io.ReadAll(io.LimitReader(reader, maxBundleDocumentBytes+1))
	if err != nil {
		return ReadinessResultBundle{}, fmt.Errorf("read readiness result bundle: %w", err)
	}
	if len(data) == 0 || len(data) > maxBundleDocumentBytes {
		return ReadinessResultBundle{}, fmt.Errorf("readiness result bundle size is invalid")
	}
	return decodeBundleBytes(data)
}

func decodeBundleBytes(data []byte) (ReadinessResultBundle, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var bundle ReadinessResultBundle
	if err := decoder.Decode(&bundle); err != nil {
		return ReadinessResultBundle{}, fmt.Errorf("decode readiness result bundle: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return ReadinessResultBundle{}, fmt.Errorf("decode readiness result bundle: trailing JSON document")
		}
		return ReadinessResultBundle{}, fmt.Errorf("decode readiness result bundle trailing content: %w", err)
	}
	return bundle, nil
}

func ValidateBundleSchema(metadataDir string, bundle ReadinessResultBundle) error {
	schemaPath := filepath.Join(
		metadataDir, "_schemas", "readiness_result_bundle.schema.json",
	)
	compiler := jsonschema.NewCompiler()
	schema, err := compiler.Compile(schemaPath)
	if err != nil {
		return fmt.Errorf("compile readiness result bundle schema: %w", err)
	}
	data, err := json.Marshal(bundle)
	if err != nil {
		return fmt.Errorf("marshal readiness result bundle: %w", err)
	}
	var instance any
	if err := json.Unmarshal(data, &instance); err != nil {
		return fmt.Errorf("normalize readiness result bundle: %w", err)
	}
	if err := schema.Validate(instance); err != nil {
		return fmt.Errorf("validate readiness result bundle schema: %w", err)
	}
	return nil
}
