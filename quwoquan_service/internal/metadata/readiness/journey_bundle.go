package readiness

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"path/filepath"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func DecodeJourneyBundle(reader io.Reader) (JourneyReadinessResultBundle, error) {
	data, err := io.ReadAll(io.LimitReader(reader, maxBundleDocumentBytes+1))
	if err != nil {
		return JourneyReadinessResultBundle{}, fmt.Errorf("read journey readiness result bundle: %w", err)
	}
	if len(data) == 0 || len(data) > maxBundleDocumentBytes {
		return JourneyReadinessResultBundle{}, fmt.Errorf("journey readiness result bundle size is invalid")
	}
	return decodeJourneyBundleBytes(data)
}

func decodeJourneyBundleBytes(data []byte) (JourneyReadinessResultBundle, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var bundle JourneyReadinessResultBundle
	if err := decoder.Decode(&bundle); err != nil {
		return JourneyReadinessResultBundle{}, fmt.Errorf("decode journey readiness result bundle: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return JourneyReadinessResultBundle{}, fmt.Errorf("decode journey readiness result bundle: trailing JSON document")
		}
		return JourneyReadinessResultBundle{}, fmt.Errorf("decode journey readiness result bundle trailing content: %w", err)
	}
	return bundle, nil
}

func ValidateJourneyBundleSchema(metadataDir string, bundle JourneyReadinessResultBundle) error {
	schemaPath := filepath.Join(metadataDir, "_schemas", "journey_readiness_result_bundle.schema.json")
	compiler := jsonschema.NewCompiler()
	schema, err := compiler.Compile(schemaPath)
	if err != nil {
		return fmt.Errorf("compile journey readiness result bundle schema: %w", err)
	}
	data, err := json.Marshal(bundle)
	if err != nil {
		return fmt.Errorf("marshal journey readiness result bundle: %w", err)
	}
	var instance any
	if err := json.Unmarshal(data, &instance); err != nil {
		return fmt.Errorf("normalize journey readiness result bundle: %w", err)
	}
	if err := schema.Validate(instance); err != nil {
		return fmt.Errorf("validate journey readiness result bundle schema: %w", err)
	}
	return nil
}
