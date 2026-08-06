package storagecontract

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

// DecodeJSON rejects every field not represented by ast.StorageDocument.
func DecodeJSON(data []byte) (ast.StorageDocument, error) {
	var document ast.StorageDocument
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&document); err != nil {
		return ast.StorageDocument{}, err
	}
	if err := rejectTrailingJSON(decoder); err != nil {
		return ast.StorageDocument{}, err
	}
	return document, nil
}

// DecodeYAML uses KnownFields so nested storage readers cannot silently ignore
// a schema key or preserve a private alias.
func DecodeYAML(data []byte) (ast.StorageDocument, error) {
	var document ast.StorageDocument
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)
	if err := decoder.Decode(&document); err != nil {
		return ast.StorageDocument{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return ast.StorageDocument{}, errors.New("storage document must contain exactly one YAML document")
		}
		return ast.StorageDocument{}, err
	}
	return document, nil
}

func LoadOptional(path string) (*ast.StorageDocument, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	document, err := DecodeYAML(data)
	if err != nil {
		return nil, fmt.Errorf("%s: decode storage: %w", path, err)
	}
	return &document, nil
}

func rejectTrailingJSON(decoder *json.Decoder) error {
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("storage document must contain exactly one JSON value")
		}
		return err
	}
	return nil
}
