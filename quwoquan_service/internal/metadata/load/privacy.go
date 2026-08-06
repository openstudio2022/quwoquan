package load

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

// decodePrivacyDocument is the only YAML reader for privacy policy semantics.
// KnownFields applies recursively, so schema and compiler cannot silently
// diverge by accepting a field that the typed AST ignores.
func decodePrivacyDocument(data []byte) (ast.PrivacyDocument, error) {
	var document ast.PrivacyDocument
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)
	if err := decoder.Decode(&document); err != nil {
		return ast.PrivacyDocument{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return ast.PrivacyDocument{}, errors.New(
				"privacy document must contain exactly one YAML document",
			)
		}
		return ast.PrivacyDocument{}, err
	}
	return document, nil
}

func loadPrivacyDocument(path string) (ast.PrivacyDocument, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return ast.PrivacyDocument{}, err
	}
	document, err := decodePrivacyDocument(data)
	if err != nil {
		return ast.PrivacyDocument{}, fmt.Errorf("%s: decode privacy: %w", path, err)
	}
	return document, nil
}
