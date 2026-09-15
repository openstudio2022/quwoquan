package safety

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/sys/unix"
)

// RuntimeFiles只读受管材料。它验证本地filesystem信任边界，不替代部署实例/current校验。
// caller不可通过材料内的UID声明取得信任；owner从实际进程/受管挂载边界确定。
type RuntimeFiles struct {
	root     string
	identity unix.Stat_t
}

var errRuntimeMaterial = errors.New("CONTENT.RELEASE.query_barrier_not_ready: unsafe or unavailable Post safety runtime material")

func OpenRuntimeFiles(root string) (*RuntimeFiles, error) {
	if !filepath.IsAbs(root) || filepath.Clean(root) != root || root == "/" {
		return nil, errRuntimeMaterial
	}
	fd, st, err := openRuntimeDirectory(root)
	if err != nil {
		return nil, err
	}
	defer unix.Close(fd)
	if st.Mode&0777 != 0700 || int(st.Uid) != os.Geteuid() {
		return nil, errRuntimeMaterial
	}
	return &RuntimeFiles{root: root, identity: st}, nil
}

func openRuntimeDirectory(path string) (int, unix.Stat_t, error) {
	flags := unix.O_RDONLY | unix.O_DIRECTORY | unix.O_NOFOLLOW | unix.O_CLOEXEC
	fd, err := unix.Open("/", flags, 0)
	if err != nil {
		return -1, unix.Stat_t{}, errRuntimeMaterial
	}
	for _, part := range strings.Split(strings.TrimPrefix(path, "/"), "/") {
		if part == "" || part == "." || part == ".." {
			unix.Close(fd)
			return -1, unix.Stat_t{}, errRuntimeMaterial
		}
		next, e := unix.Openat(fd, part, flags, 0)
		unix.Close(fd)
		if e != nil {
			return -1, unix.Stat_t{}, errRuntimeMaterial
		}
		fd = next
		var st unix.Stat_t
		if unix.Fstat(fd, &st) != nil || st.Mode&unix.S_IFMT != unix.S_IFDIR {
			unix.Close(fd)
			return -1, unix.Stat_t{}, errRuntimeMaterial
		}
		// 系统sticky临时祖先可用作隔离测试根，但材料根及子目录必须owner独占。
		if int(st.Uid) != 0 && int(st.Uid) != os.Geteuid() {
			unix.Close(fd)
			return -1, unix.Stat_t{}, errRuntimeMaterial
		}
		if st.Mode&0022 != 0 && !(st.Uid == 0 && st.Mode&unix.S_ISVTX != 0) {
			unix.Close(fd)
			return -1, unix.Stat_t{}, errRuntimeMaterial
		}
	}
	var st unix.Stat_t
	if unix.Fstat(fd, &st) != nil {
		unix.Close(fd)
		return -1, st, errRuntimeMaterial
	}
	return fd, st, nil
}
func sameFile(a, b unix.Stat_t) bool {
	return a.Dev == b.Dev && a.Ino == b.Ino && a.Mode == b.Mode && a.Uid == b.Uid && a.Gid == b.Gid && a.Nlink == b.Nlink
}

func validRuntimeRef(ref string) bool {
	if ref == "" || filepath.IsAbs(ref) || filepath.Clean(ref) != ref || strings.Contains(ref, "\\") {
		return false
	}
	for _, part := range strings.Split(ref, "/") {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}
func (f *RuntimeFiles) open(ref string) (int, unix.Stat_t, error) {
	if f == nil || !validRuntimeRef(ref) {
		return -1, unix.Stat_t{}, errRuntimeMaterial
	}
	fd, st, err := openRuntimeDirectory(f.root)
	if err != nil {
		return -1, st, err
	}
	if !sameFile(st, f.identity) {
		unix.Close(fd)
		return -1, st, errRuntimeMaterial
	}
	parts := strings.Split(ref, "/")
	for _, part := range parts[:len(parts)-1] {
		next, e := unix.Openat(fd, part, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
		unix.Close(fd)
		if e != nil {
			return -1, st, errRuntimeMaterial
		}
		fd = next
		if unix.Fstat(fd, &st) != nil || st.Mode&unix.S_IFMT != unix.S_IFDIR || st.Mode&0777 != 0700 || int(st.Uid) != os.Geteuid() {
			unix.Close(fd)
			return -1, st, errRuntimeMaterial
		}
	}
	next, e := unix.Openat(fd, parts[len(parts)-1], unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	unix.Close(fd)
	if e != nil {
		return -1, st, errRuntimeMaterial
	}
	if unix.Fstat(next, &st) != nil || st.Mode&unix.S_IFMT != unix.S_IFREG || st.Mode&0777 != 0600 || st.Nlink != 1 || int(st.Uid) != os.Geteuid() {
		unix.Close(next)
		return -1, st, errRuntimeMaterial
	}
	return next, st, nil
}

func (f *RuntimeFiles) Read(ref string, limit int64) ([]byte, error) {
	if limit <= 0 || limit > 1<<20 {
		return nil, errRuntimeMaterial
	}
	fd, before, err := f.open(ref)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(fd), "post-safety-material")
	defer file.Close()
	if before.Size < 0 || before.Size > limit {
		return nil, errRuntimeMaterial
	}
	first, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || int64(len(first)) != before.Size {
		return nil, errRuntimeMaterial
	}
	var after unix.Stat_t
	if unix.Fstat(fd, &after) != nil || !sameFile(before, after) || before.Size != after.Size || before.Mtim != after.Mtim || before.Ctim != after.Ctim {
		return nil, errRuntimeMaterial
	}
	// 重新沿根和ref打开，防祖先/文件路径被替换；再次读取内容，拒绝读期间的可观察更改。
	secondFD, again, err := f.open(ref)
	if err != nil {
		return nil, err
	}
	second := os.NewFile(uintptr(secondFD), "post-safety-material")
	defer second.Close()
	if !sameFile(before, again) || before.Size != again.Size || before.Mtim != again.Mtim || before.Ctim != again.Ctim {
		return nil, errRuntimeMaterial
	}
	content, err := io.ReadAll(io.LimitReader(second, limit+1))
	if err != nil || !bytes.Equal(first, content) {
		return nil, errRuntimeMaterial
	}
	return first, nil
}
func runtimeBytesDigest(raw []byte) string {
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}
func (f *RuntimeFiles) ReadDigest(ref, digest string) ([]byte, error) {
	if !validDigest(digest) {
		return nil, errRuntimeMaterial
	}
	raw, err := f.Read(ref, 1<<20)
	if err != nil {
		return nil, err
	}
	if runtimeBytesDigest(raw) != digest {
		return nil, fmt.Errorf("%w: evidence digest differs", errRuntimeMaterial)
	}
	return raw, nil
}
