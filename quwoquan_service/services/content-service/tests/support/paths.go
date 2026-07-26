package support

import (
	"path/filepath"
	"runtime"
)

// ServiceRoot returns the content-service directory independent of go test's
// per-package working directory.
func ServiceRoot() string {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		panic("resolve content-service test support path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", ".."))
}

// RepositoryRoot returns the repository root for tests that invoke repository
// tooling rather than production code.
func RepositoryRoot() string {
	return filepath.Clean(filepath.Join(ServiceRoot(), "..", "..", ".."))
}
