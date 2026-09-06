// Package datarelease loads the identity tuple of an immutable Data release.
//
// A successful load proves that payload/release.json and
// attestations/release.json name the same release and that the attested
// payloadSha256 equals the current payload tree digest. The loader never
// follows a symbolic link in either document path or anywhere in payload/.
package datarelease

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

const (
	HeaderPath      = "payload/release.json"
	AttestationPath = "attestations/release.json"

	HeaderSchema      = "quwoquan_data.release"
	AttestationSchema = "quwoquan_data.release_attestation"
)

const maxIdentityDocumentBytes int64 = 4 << 20

type SourceOwner string

type ReleaseKind string

type ReleaseClass string

type Digest string

const (
	SourceOwnerQWQData SourceOwner = "qwq_data"

	ReleaseKindContent       ReleaseKind = "content"
	ReleaseKindEmptyBaseline ReleaseKind = "empty_baseline"

	ReleaseClassResearch   ReleaseClass = "research"
	ReleaseClassCommercial ReleaseClass = "commercial"
)

// Header is the identity-bearing subset of payload/release.json. Other header
// fields remain owned by the producer schema and are deliberately not copied
// into the shared importer API.
type Header struct {
	Schema       string       `json:"schema"`
	ReleaseID    string       `json:"releaseId"`
	SourceOwner  SourceOwner  `json:"sourceOwner"`
	ReleaseKind  ReleaseKind  `json:"releaseKind"`
	ReleaseClass ReleaseClass `json:"releaseClass"`
}

// Attestation is the identity-bearing subset of attestations/release.json.
type Attestation struct {
	Schema        string       `json:"schema"`
	ReleaseID     string       `json:"releaseId"`
	SourceOwner   SourceOwner  `json:"sourceOwner"`
	ReleaseKind   ReleaseKind  `json:"releaseKind"`
	ReleaseClass  ReleaseClass `json:"releaseClass"`
	PayloadSHA256 Digest       `json:"payloadSha256"`
}

// Tuple is the common immutable release identity consumed by Data importers
// and release-control. PayloadSHA256 has been recomputed from payload/, not
// merely copied from the attestation.
type Tuple struct {
	ReleaseID     string       `json:"releaseId"`
	SourceOwner   SourceOwner  `json:"sourceOwner"`
	ReleaseKind   ReleaseKind  `json:"releaseKind"`
	ReleaseClass  ReleaseClass `json:"releaseClass"`
	PayloadSHA256 Digest       `json:"payloadSha256"`
}

type ErrorCode string

const (
	CodeInvalidRoot    ErrorCode = "invalid_root"
	CodeUnsafePath     ErrorCode = "unsafe_path"
	CodeReadFailed     ErrorCode = "read_failed"
	CodeInvalidJSON    ErrorCode = "invalid_json"
	CodeMissingField   ErrorCode = "missing_field"
	CodeInvalidField   ErrorCode = "invalid_field"
	CodeSchemaMismatch ErrorCode = "schema_mismatch"
	CodeIdentityDrift  ErrorCode = "identity_drift"
	CodeDigestDrift    ErrorCode = "digest_drift"
	CodeReleaseChanged ErrorCode = "release_changed"
)

// LoadError provides a stable machine-readable code while preserving a
// human-readable relative path, field, and wrapped operating-system error.
type LoadError struct {
	Code   ErrorCode
	Path   string
	Field  string
	Detail string
	Err    error
}

func (e *LoadError) Error() string {
	if e == nil {
		return "data release load failed"
	}
	location := ""
	if e.Path != "" {
		location = " at " + e.Path
	}
	if e.Field != "" {
		location += " field " + e.Field
	}
	message := "data release " + string(e.Code) + location
	if e.Detail != "" {
		message += ": " + e.Detail
	}
	if e.Err != nil {
		message += ": " + e.Err.Error()
	}
	return message
}

func (e *LoadError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Err
}

// HasCode allows callers to classify a load failure without parsing text.
func HasCode(err error, code ErrorCode) bool {
	var loadErr *LoadError
	return errors.As(err, &loadErr) && loadErr.Code == code
}

var canonicalDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
var sensitivePathPattern = regexp.MustCompile(`(?i)(?:api[_-]?key|credential|secret|password|access[_-]?token|refresh[_-]?token|cookie|session)`)

// Load validates and returns one immutable Data release tuple.
func Load(releaseRoot string) (Tuple, error) {
	var zero Tuple
	root, err := openReleaseRoot(releaseRoot)
	if err != nil {
		return zero, err
	}
	defer root.Close()

	headerRaw, err := readIdentityDocument(root, HeaderPath)
	if err != nil {
		return zero, err
	}
	attestationRaw, err := readIdentityDocument(root, AttestationPath)
	if err != nil {
		return zero, err
	}

	header, err := decodeHeader(headerRaw)
	if err != nil {
		return zero, err
	}
	attestation, err := decodeAttestation(attestationRaw)
	if err != nil {
		return zero, err
	}
	if err := validateSameIdentity(header, attestation); err != nil {
		return zero, err
	}

	actualDigest, err := digestPayload(root, headerRaw)
	if err != nil {
		return zero, err
	}
	if actualDigest != attestation.PayloadSHA256 {
		return zero, &LoadError{
			Code:   CodeDigestDrift,
			Path:   AttestationPath,
			Field:  "payloadSha256",
			Detail: fmt.Sprintf("attested %q, computed %q", attestation.PayloadSHA256, actualDigest),
		}
	}

	attestationAfterDigest, err := readIdentityDocument(root, AttestationPath)
	if err != nil {
		return zero, err
	}
	if !bytes.Equal(attestationRaw, attestationAfterDigest) {
		return zero, &LoadError{
			Code:   CodeReleaseChanged,
			Path:   AttestationPath,
			Detail: "attestation changed while the release was being verified",
		}
	}
	verifiedDigest, err := digestPayload(root, headerRaw)
	if err != nil {
		return zero, err
	}
	if verifiedDigest != actualDigest {
		return zero, &LoadError{
			Code:   CodeReleaseChanged,
			Path:   "payload",
			Detail: fmt.Sprintf("payload digest changed from %q to %q during verification", actualDigest, verifiedDigest),
		}
	}

	return Tuple{
		ReleaseID:     header.ReleaseID,
		SourceOwner:   header.SourceOwner,
		ReleaseKind:   header.ReleaseKind,
		ReleaseClass:  header.ReleaseClass,
		PayloadSHA256: actualDigest,
	}, nil
}

func openReleaseRoot(releaseRoot string) (*os.Root, error) {
	if strings.TrimSpace(releaseRoot) == "" {
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "release root is required"}
	}
	absolute, err := filepath.Abs(releaseRoot)
	if err != nil {
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "resolve release root", Err: err}
	}
	info, err := os.Lstat(absolute)
	if err != nil {
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "inspect release root", Err: err}
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return nil, &LoadError{Code: CodeUnsafePath, Detail: "release root must not be a symbolic link"}
	}
	if !info.IsDir() {
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "release root is not a directory"}
	}
	root, err := os.OpenRoot(absolute)
	if err != nil {
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "open release root", Err: err}
	}
	afterOpen, err := os.Lstat(absolute)
	if err != nil {
		root.Close()
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "reinspect release root", Err: err}
	}
	openedInfo, err := root.Stat(".")
	if err != nil {
		root.Close()
		return nil, &LoadError{Code: CodeInvalidRoot, Detail: "inspect opened release root", Err: err}
	}
	if afterOpen.Mode()&os.ModeSymlink != 0 || !afterOpen.IsDir() ||
		!os.SameFile(info, afterOpen) || !os.SameFile(afterOpen, openedInfo) {
		root.Close()
		return nil, &LoadError{Code: CodeUnsafePath, Detail: "release root changed while it was being opened"}
	}
	return root, nil
}

func readIdentityDocument(root *os.Root, relativePath string) ([]byte, error) {
	if err := requireRegularPath(root, relativePath); err != nil {
		return nil, err
	}
	file, err := root.Open(filepath.FromSlash(relativePath))
	if err != nil {
		return nil, &LoadError{Code: CodeReadFailed, Path: relativePath, Detail: "open document", Err: err}
	}
	defer file.Close()

	raw, err := io.ReadAll(io.LimitReader(file, maxIdentityDocumentBytes+1))
	if err != nil {
		return nil, &LoadError{Code: CodeReadFailed, Path: relativePath, Detail: "read document", Err: err}
	}
	if int64(len(raw)) > maxIdentityDocumentBytes {
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "document exceeds 4 MiB limit"}
	}
	return raw, nil
}

func requireRegularPath(root *os.Root, relativePath string) error {
	nativePath := filepath.FromSlash(relativePath)
	if !filepath.IsLocal(nativePath) || filepath.Clean(nativePath) != nativePath {
		return &LoadError{Code: CodeUnsafePath, Path: relativePath, Detail: "path escapes release root"}
	}
	parts := strings.Split(nativePath, string(filepath.Separator))
	current := ""
	for index, part := range parts {
		if part == "" || part == "." || part == ".." {
			return &LoadError{Code: CodeUnsafePath, Path: relativePath, Detail: "path contains an unsafe segment"}
		}
		current = filepath.Join(current, part)
		info, err := root.Lstat(current)
		if err != nil {
			return &LoadError{Code: CodeReadFailed, Path: relativePath, Detail: "inspect path", Err: err}
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return &LoadError{Code: CodeUnsafePath, Path: filepath.ToSlash(current), Detail: "symbolic links are forbidden"}
		}
		if index < len(parts)-1 && !info.IsDir() {
			return &LoadError{Code: CodeUnsafePath, Path: filepath.ToSlash(current), Detail: "path component is not a directory"}
		}
		if index == len(parts)-1 && !info.Mode().IsRegular() {
			return &LoadError{Code: CodeUnsafePath, Path: relativePath, Detail: "document is not a regular file"}
		}
	}
	return nil
}

func decodeHeader(raw []byte) (Header, error) {
	object, err := decodeJSONObject(raw, HeaderPath)
	if err != nil {
		return Header{}, err
	}
	schema, err := requiredString(object, HeaderPath, "schema")
	if err != nil {
		return Header{}, err
	}
	if schema != HeaderSchema {
		return Header{}, &LoadError{Code: CodeSchemaMismatch, Path: HeaderPath, Field: "schema", Detail: fmt.Sprintf("expected %q, got %q", HeaderSchema, schema)}
	}
	releaseID, err := requiredCanonicalString(object, HeaderPath, "releaseId")
	if err != nil {
		return Header{}, err
	}
	sourceOwner, err := requiredString(object, HeaderPath, "sourceOwner")
	if err != nil {
		return Header{}, err
	}
	releaseKind, err := requiredString(object, HeaderPath, "releaseKind")
	if err != nil {
		return Header{}, err
	}
	releaseClass, err := requiredString(object, HeaderPath, "releaseClass")
	if err != nil {
		return Header{}, err
	}

	header := Header{
		Schema:       schema,
		ReleaseID:    releaseID,
		SourceOwner:  SourceOwner(sourceOwner),
		ReleaseKind:  ReleaseKind(releaseKind),
		ReleaseClass: ReleaseClass(releaseClass),
	}
	if err := validateHeaderFields(header); err != nil {
		return Header{}, err
	}
	return header, nil
}

func decodeAttestation(raw []byte) (Attestation, error) {
	object, err := decodeJSONObject(raw, AttestationPath)
	if err != nil {
		return Attestation{}, err
	}
	schema, err := requiredString(object, AttestationPath, "schema")
	if err != nil {
		return Attestation{}, err
	}
	if schema != AttestationSchema {
		return Attestation{}, &LoadError{Code: CodeSchemaMismatch, Path: AttestationPath, Field: "schema", Detail: fmt.Sprintf("expected %q, got %q", AttestationSchema, schema)}
	}
	releaseID, err := requiredCanonicalString(object, AttestationPath, "releaseId")
	if err != nil {
		return Attestation{}, err
	}
	sourceOwner, err := requiredString(object, AttestationPath, "sourceOwner")
	if err != nil {
		return Attestation{}, err
	}
	releaseKind, err := requiredString(object, AttestationPath, "releaseKind")
	if err != nil {
		return Attestation{}, err
	}
	releaseClass, err := requiredString(object, AttestationPath, "releaseClass")
	if err != nil {
		return Attestation{}, err
	}
	payloadSHA256, err := requiredString(object, AttestationPath, "payloadSha256")
	if err != nil {
		return Attestation{}, err
	}

	attestation := Attestation{
		Schema:        schema,
		ReleaseID:     releaseID,
		SourceOwner:   SourceOwner(sourceOwner),
		ReleaseKind:   ReleaseKind(releaseKind),
		ReleaseClass:  ReleaseClass(releaseClass),
		PayloadSHA256: Digest(payloadSHA256),
	}
	if err := validateAttestationFields(attestation); err != nil {
		return Attestation{}, err
	}
	return attestation, nil
}

func decodeJSONObject(raw []byte, relativePath string) (map[string]json.RawMessage, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	opening, err := decoder.Token()
	if err != nil {
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "decode object", Err: err}
	}
	if delimiter, ok := opening.(json.Delim); !ok || delimiter != '{' {
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "top-level value must be an object"}
	}
	object := make(map[string]json.RawMessage)
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "decode field name", Err: err}
		}
		name, ok := token.(string)
		if !ok {
			return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "object field name is invalid"}
		}
		if _, exists := object[name]; exists {
			return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Field: name, Detail: "duplicate field"}
		}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Field: name, Detail: "decode field", Err: err}
		}
		object[name] = value
	}
	closing, err := decoder.Token()
	if err != nil {
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "close object", Err: err}
	}
	if delimiter, ok := closing.(json.Delim); !ok || delimiter != '}' {
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "object is not closed"}
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "multiple JSON values are forbidden"}
		}
		return nil, &LoadError{Code: CodeInvalidJSON, Path: relativePath, Detail: "decode trailing data", Err: err}
	}
	return object, nil
}

func requiredString(object map[string]json.RawMessage, relativePath, field string) (string, error) {
	raw, ok := object[field]
	if !ok {
		return "", &LoadError{Code: CodeMissingField, Path: relativePath, Field: field, Detail: "required field is absent"}
	}
	if trimmed := bytes.TrimSpace(raw); len(trimmed) == 0 || trimmed[0] != '"' {
		return "", &LoadError{Code: CodeInvalidField, Path: relativePath, Field: field, Detail: "field must be a string"}
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return "", &LoadError{Code: CodeInvalidField, Path: relativePath, Field: field, Detail: "field must be a string", Err: err}
	}
	return value, nil
}

func requiredCanonicalString(object map[string]json.RawMessage, relativePath, field string) (string, error) {
	value, err := requiredString(object, relativePath, field)
	if err != nil {
		return "", err
	}
	if value == "" || value != strings.TrimSpace(value) {
		return "", &LoadError{Code: CodeInvalidField, Path: relativePath, Field: field, Detail: "field must be non-empty and have no surrounding whitespace"}
	}
	return value, nil
}

func validateHeaderFields(header Header) error {
	if header.SourceOwner != SourceOwnerQWQData {
		return invalidEnum(HeaderPath, "sourceOwner", string(header.SourceOwner))
	}
	if header.ReleaseKind != ReleaseKindContent && header.ReleaseKind != ReleaseKindEmptyBaseline {
		return invalidEnum(HeaderPath, "releaseKind", string(header.ReleaseKind))
	}
	if header.ReleaseClass != ReleaseClassResearch && header.ReleaseClass != ReleaseClassCommercial {
		return invalidEnum(HeaderPath, "releaseClass", string(header.ReleaseClass))
	}
	return nil
}

func validateAttestationFields(attestation Attestation) error {
	if attestation.SourceOwner != SourceOwnerQWQData {
		return invalidEnum(AttestationPath, "sourceOwner", string(attestation.SourceOwner))
	}
	if attestation.ReleaseKind != ReleaseKindContent && attestation.ReleaseKind != ReleaseKindEmptyBaseline {
		return invalidEnum(AttestationPath, "releaseKind", string(attestation.ReleaseKind))
	}
	if attestation.ReleaseClass != ReleaseClassResearch && attestation.ReleaseClass != ReleaseClassCommercial {
		return invalidEnum(AttestationPath, "releaseClass", string(attestation.ReleaseClass))
	}
	if !canonicalDigestPattern.MatchString(string(attestation.PayloadSHA256)) {
		return &LoadError{Code: CodeInvalidField, Path: AttestationPath, Field: "payloadSha256", Detail: "expected canonical sha256:<64 lowercase hex>"}
	}
	return nil
}

func invalidEnum(relativePath, field, actual string) error {
	return &LoadError{Code: CodeInvalidField, Path: relativePath, Field: field, Detail: fmt.Sprintf("unsupported value %q", actual)}
}

func validateSameIdentity(header Header, attestation Attestation) error {
	comparisons := []struct {
		field       string
		header      string
		attestation string
	}{
		{field: "releaseId", header: header.ReleaseID, attestation: attestation.ReleaseID},
		{field: "sourceOwner", header: string(header.SourceOwner), attestation: string(attestation.SourceOwner)},
		{field: "releaseKind", header: string(header.ReleaseKind), attestation: string(attestation.ReleaseKind)},
		{field: "releaseClass", header: string(header.ReleaseClass), attestation: string(attestation.ReleaseClass)},
	}
	for _, comparison := range comparisons {
		if comparison.header != comparison.attestation {
			return &LoadError{
				Code:   CodeIdentityDrift,
				Path:   AttestationPath,
				Field:  comparison.field,
				Detail: fmt.Sprintf("header %q differs from attestation %q", comparison.header, comparison.attestation),
			}
		}
	}
	return nil
}

type payloadEntry struct {
	path string
	leaf [sha256.Size]byte
}

func digestPayload(root *os.Root, expectedHeader []byte) (Digest, error) {
	entries := make([]payloadEntry, 0)
	expectedHeaderHash := sha256.Sum256(expectedHeader)
	headerObserved := false
	if err := collectPayloadEntries(root, "payload", "", expectedHeaderHash, int64(len(expectedHeader)), &headerObserved, &entries); err != nil {
		return "", err
	}
	if !headerObserved {
		return "", &LoadError{Code: CodeReadFailed, Path: HeaderPath, Detail: "header disappeared while the release was being verified"}
	}

	sort.Slice(entries, func(left, right int) bool { return entries[left].path < entries[right].path })
	level := make([][sha256.Size]byte, len(entries))
	for index := range entries {
		level[index] = entries[index].leaf
	}
	if len(level) == 0 {
		empty := sha256.Sum256(nil)
		return Digest("sha256:" + hex.EncodeToString(empty[:])), nil
	}
	for len(level) > 1 {
		next := make([][sha256.Size]byte, 0, (len(level)+1)/2)
		for index := 0; index < len(level); index += 2 {
			right := level[index]
			if index+1 < len(level) {
				right = level[index+1]
			}
			input := make([]byte, 0, len("node\x00")+sha256.Size*2)
			input = append(input, "node\x00"...)
			input = append(input, level[index][:]...)
			input = append(input, right[:]...)
			next = append(next, sha256.Sum256(input))
		}
		level = next
	}
	return Digest("sha256:" + hex.EncodeToString(level[0][:])), nil
}

func collectPayloadEntries(
	root *os.Root,
	directory string,
	payloadRelativeDirectory string,
	expectedHeaderHash [sha256.Size]byte,
	expectedHeaderSize int64,
	headerObserved *bool,
	entries *[]payloadEntry,
) error {
	if err := requireDirectoryPath(root, directory); err != nil {
		return err
	}
	dir, err := root.Open(directory)
	if err != nil {
		return &LoadError{Code: CodeReadFailed, Path: filepath.ToSlash(directory), Detail: "open payload directory", Err: err}
	}
	children, readErr := dir.ReadDir(-1)
	closeErr := dir.Close()
	if readErr != nil {
		return &LoadError{Code: CodeReadFailed, Path: filepath.ToSlash(directory), Detail: "read payload directory", Err: readErr}
	}
	if closeErr != nil {
		return &LoadError{Code: CodeReadFailed, Path: filepath.ToSlash(directory), Detail: "close payload directory", Err: closeErr}
	}

	for _, child := range children {
		childPayloadRelative := filepath.Join(payloadRelativeDirectory, child.Name())
		childPath := filepath.Join(directory, child.Name())
		childPathSlash := filepath.ToSlash(childPath)
		info, err := root.Lstat(childPath)
		if err != nil {
			return &LoadError{Code: CodeReadFailed, Path: childPathSlash, Detail: "inspect payload entry", Err: err}
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return &LoadError{Code: CodeUnsafePath, Path: childPathSlash, Detail: "symbolic links are forbidden"}
		}
		if info.IsDir() {
			if err := collectPayloadEntries(
				root,
				childPath,
				childPayloadRelative,
				expectedHeaderHash,
				expectedHeaderSize,
				headerObserved,
				entries,
			); err != nil {
				return err
			}
			continue
		}
		if !info.Mode().IsRegular() {
			return &LoadError{Code: CodeUnsafePath, Path: childPathSlash, Detail: "payload entries must be regular files"}
		}

		blobHash, size, err := hashPayloadFile(root, childPath)
		if err != nil {
			return err
		}
		relativeSlash := filepath.ToSlash(childPayloadRelative)
		if relativeSlash == "release.json" {
			*headerObserved = true
			if size != expectedHeaderSize || blobHash != expectedHeaderHash {
				return &LoadError{Code: CodeReleaseChanged, Path: HeaderPath, Detail: "header changed while the release was being verified"}
			}
		}
		leafPath := relativeSlash
		if sensitivePathPattern.MatchString(leafPath) {
			pathHash := sha256.Sum256([]byte(leafPath))
			leafPath = "redacted/" + hex.EncodeToString(pathHash[:])
		}
		blobDigest := "sha256:" + hex.EncodeToString(blobHash[:])
		leafInput := []byte("blob\x00" + leafPath + "\x00" + blobDigest + "\x00" + strconv.FormatInt(size, 10))
		*entries = append(*entries, payloadEntry{path: relativeSlash, leaf: sha256.Sum256(leafInput)})
	}
	return nil
}

func requireDirectoryPath(root *os.Root, relativePath string) error {
	nativePath := filepath.FromSlash(relativePath)
	if !filepath.IsLocal(nativePath) || filepath.Clean(nativePath) != nativePath {
		return &LoadError{Code: CodeUnsafePath, Path: relativePath, Detail: "path escapes release root"}
	}
	parts := strings.Split(nativePath, string(filepath.Separator))
	current := ""
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return &LoadError{Code: CodeUnsafePath, Path: relativePath, Detail: "path contains an unsafe segment"}
		}
		current = filepath.Join(current, part)
		info, err := root.Lstat(current)
		if err != nil {
			return &LoadError{Code: CodeReadFailed, Path: filepath.ToSlash(current), Detail: "inspect directory path", Err: err}
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return &LoadError{Code: CodeUnsafePath, Path: filepath.ToSlash(current), Detail: "symbolic links are forbidden"}
		}
		if !info.IsDir() {
			return &LoadError{Code: CodeUnsafePath, Path: filepath.ToSlash(current), Detail: "path component is not a directory"}
		}
	}
	return nil
}

func hashPayloadFile(root *os.Root, relativePath string) ([sha256.Size]byte, int64, error) {
	var zero [sha256.Size]byte
	relativeSlash := filepath.ToSlash(relativePath)
	if err := requireRegularPath(root, relativeSlash); err != nil {
		return zero, 0, err
	}
	file, err := root.Open(relativePath)
	if err != nil {
		return zero, 0, &LoadError{Code: CodeReadFailed, Path: relativeSlash, Detail: "open payload file", Err: err}
	}
	defer file.Close()
	before, err := file.Stat()
	if err != nil {
		return zero, 0, &LoadError{Code: CodeReadFailed, Path: relativeSlash, Detail: "stat payload file", Err: err}
	}
	hash := sha256.New()
	size, err := io.Copy(hash, file)
	if err != nil {
		return zero, 0, &LoadError{Code: CodeReadFailed, Path: relativeSlash, Detail: "hash payload file", Err: err}
	}
	after, err := file.Stat()
	if err != nil {
		return zero, 0, &LoadError{Code: CodeReadFailed, Path: relativeSlash, Detail: "restat payload file", Err: err}
	}
	if size != before.Size() || size != after.Size() || before.ModTime() != after.ModTime() {
		return zero, 0, &LoadError{Code: CodeReleaseChanged, Path: relativeSlash, Detail: "payload file changed while it was being hashed"}
	}
	copy(zero[:], hash.Sum(nil))
	return zero, size, nil
}
