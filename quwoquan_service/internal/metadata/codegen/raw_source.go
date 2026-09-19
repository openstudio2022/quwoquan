package codegen

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// RawFile 读取编译视图中的原始快照字节，且必须匹配 ContractGraph 的唯一来源摘要。
// 它不读取规范化 JSON Documents，也不回退到当前物理源码或部署副本。
func (s *Source) RawFile(relativePath string) ([]byte, error) {
	if !filepath.IsLocal(relativePath) {
		return nil, fmt.Errorf("raw source path must stay relative to metadata root: %s", relativePath)
	}
	path := normalizeRelativePath(relativePath)
	digest, err := s.rawSourceDigest(path)
	if err != nil {
		return nil, err
	}
	root, err := os.OpenRoot(s.root)
	if err != nil {
		return nil, fmt.Errorf("open raw source root: %w", err)
	}
	defer root.Close()
	info, err := root.Lstat(path)
	if err != nil {
		return nil, fmt.Errorf("inspect raw source %s: %w", path, err)
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("raw source %s must be a regular byte snapshot", path)
	}
	file, err := root.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open raw source %s: %w", path, err)
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("stat opened raw source %s: %w", path, err)
	}
	if !os.SameFile(info, opened) {
		return nil, fmt.Errorf("raw source %s changed while opening", path)
	}
	content, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("read raw source %s: %w", path, err)
	}
	actual := sha256.Sum256(content)
	if hex.EncodeToString(actual[:]) != digest {
		return nil, fmt.Errorf("raw source %s SHA256 drift from ContractGraph", path)
	}
	return content, nil
}

func (s *Source) rawSourceDigest(path string) (string, error) {
	if s == nil || s.graph == nil {
		return "", fmt.Errorf("ContractGraph Source is required")
	}
	digest := ""
	matches := 0
	for _, source := range s.graph.Sources {
		if source.Path == path {
			digest = source.SHA256
			matches++
		}
	}
	if matches != 1 {
		return "", fmt.Errorf("raw source %s requires exactly one ContractGraph source digest, got %d", path, matches)
	}
	return digest, nil
}
