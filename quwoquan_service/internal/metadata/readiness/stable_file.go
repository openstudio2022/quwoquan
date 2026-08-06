package readiness

import (
	"fmt"
	"io"
	"os"
)

// ReadStableRegularFile rejects symlinks, non-regular inputs, oversize files
// and identity changes across open/read. CLI callers use it to make an input
// swap a hard evaluation error rather than evaluating a mixed snapshot.
func ReadStableRegularFile(path string, limit int64) ([]byte, error) {
	if path == "" || limit <= 0 {
		return nil, fmt.Errorf("stable file path and positive limit are required")
	}
	before, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if before.Mode()&os.ModeSymlink != 0 || !before.Mode().IsRegular() || before.Size() > limit {
		return nil, fmt.Errorf("input must be a bounded regular file")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || opened.Size() > limit ||
		!os.SameFile(before, opened) {
		return nil, fmt.Errorf("input changed while opening")
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return nil, err
	}
	if len(data) == 0 || int64(len(data)) > limit {
		return nil, fmt.Errorf("input size is invalid")
	}
	after, err := os.Lstat(path)
	if err != nil || after.Mode()&os.ModeSymlink != 0 || !os.SameFile(before, after) ||
		after.Size() != opened.Size() || after.ModTime() != opened.ModTime() {
		return nil, fmt.Errorf("input changed while reading")
	}
	return data, nil
}
