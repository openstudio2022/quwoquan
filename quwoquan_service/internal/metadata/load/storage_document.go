package load

import (
	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"
)

func decodeStorageJSON(data []byte) (ast.StorageDocument, error) {
	return storagecontract.DecodeJSON(data)
}

func decodeStorageYAML(data []byte) (ast.StorageDocument, error) {
	return storagecontract.DecodeYAML(data)
}

func loadOptionalStorageDocument(path string) (*ast.StorageDocument, error) {
	return storagecontract.LoadOptional(path)
}
