package id

import (
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"
)

const (
	ulidLength = 26
	entropyLen = 10

	// maxTimestampMilliseconds 是 ULID 时间段可表示的毫秒上界（48 bit）。
	// 越界时间无法编码为 canonical ULID，只能停止分配而不是截断或环绕。
	maxTimestampMilliseconds = int64(1) << 48

	// AllocationAttempts 是同一次分配意图允许的候选 ID 总次数。未提交候选
	// 与既有身份冲突时可在此预算内换用新的安全熵；预算耗尽必须安全失败，
	// 不降级为弱随机、别名或时间后缀。
	AllocationAttempts = 3
)

var (
	// ErrTimestampOutOfRange 表示时间戳无法编码为 canonical ULID。
	ErrTimestampOutOfRange = errors.New("runtime/id: timestamp out of encodable range")
	// ErrEntropyUnavailable 表示安全熵不可用；调用方不得改用弱随机。
	ErrEntropyUnavailable = errors.New("runtime/id: secure entropy unavailable")
	// ErrAllocationBudgetExhausted 表示未提交候选连续冲突且预算已耗尽。
	ErrAllocationBudgetExhausted = errors.New("runtime/id: identity allocation budget exhausted")
)

// CandidateProbe 回答一个尚未提交的候选 ID 是否已被既有身份占用。
// 只有 taken=true 才触发有界重分配；err 按原样返回，不当作冲突。
type CandidateProbe func(candidate string) (taken bool, err error)

var crockford = []byte("0123456789ABCDEFGHJKMNPQRSTVWXYZ")

type Generator struct {
	prefix  Prefix
	now     func() time.Time
	entropy io.Reader
}

type GeneratorOption func(*Generator)

func NewGenerator(prefix Prefix, opts ...GeneratorOption) (*Generator, error) {
	if !DefaultRegistry.Contains(prefix) {
		return nil, fmt.Errorf("runtime/id: unregistered prefix %q", prefix)
	}
	g := &Generator{
		prefix:  prefix,
		now:     func() time.Time { return time.Now().UTC() },
		entropy: rand.Reader,
	}
	for _, opt := range opts {
		opt(g)
	}
	if g.now == nil {
		return nil, fmt.Errorf("runtime/id: nil clock")
	}
	if g.entropy == nil {
		return nil, fmt.Errorf("runtime/id: nil entropy")
	}
	return g, nil
}

func MustNewGenerator(prefix Prefix, opts ...GeneratorOption) *Generator {
	g, err := NewGenerator(prefix, opts...)
	if err != nil {
		panic(err)
	}
	return g
}

func WithClock(now func() time.Time) GeneratorOption {
	return func(g *Generator) {
		g.now = now
	}
}

func WithEntropy(entropy io.Reader) GeneratorOption {
	return func(g *Generator) {
		g.entropy = entropy
	}
}

func (g *Generator) Generate() (string, error) {
	return g.GenerateAt(g.now())
}

func (g *Generator) GenerateAt(t time.Time) (string, error) {
	milliseconds := t.UTC().UnixMilli()
	if milliseconds < 0 || milliseconds >= maxTimestampMilliseconds {
		return "", fmt.Errorf("%w: %d", ErrTimestampOutOfRange, milliseconds)
	}
	var entropy [entropyLen]byte
	if _, err := io.ReadFull(g.entropy, entropy[:]); err != nil {
		return "", fmt.Errorf("%w: %v", ErrEntropyUnavailable, err)
	}
	return string(g.prefix) + encodeULID(t.UTC(), entropy), nil
}

func Generate(prefix Prefix) (string, error) {
	return MustNewGenerator(prefix).Generate()
}

func New(prefix string) (string, error) {
	return Generate(Prefix(strings.TrimSpace(prefix)))
}

func MustGenerate(prefix Prefix) string {
	id, err := Generate(prefix)
	if err != nil {
		panic(err)
	}
	return id
}

func encodeULID(t time.Time, entropy [entropyLen]byte) string {
	var b [16]byte
	ms := uint64(t.UnixMilli())
	b[0] = byte(ms >> 40)
	b[1] = byte(ms >> 32)
	b[2] = byte(ms >> 24)
	b[3] = byte(ms >> 16)
	b[4] = byte(ms >> 8)
	b[5] = byte(ms)
	copy(b[6:], entropy[:])

	encoded := make([]byte, ulidLength)
	encoded[0] = crockford[(b[0]&224)>>5]
	encoded[1] = crockford[b[0]&31]
	encoded[2] = crockford[(b[1]&248)>>3]
	encoded[3] = crockford[((b[1]&7)<<2)|((b[2]&192)>>6)]
	encoded[4] = crockford[(b[2]&62)>>1]
	encoded[5] = crockford[((b[2]&1)<<4)|((b[3]&240)>>4)]
	encoded[6] = crockford[((b[3]&15)<<1)|((b[4]&128)>>7)]
	encoded[7] = crockford[(b[4]&124)>>2]
	encoded[8] = crockford[((b[4]&3)<<3)|((b[5]&224)>>5)]
	encoded[9] = crockford[b[5]&31]
	encoded[10] = crockford[(b[6]&248)>>3]
	encoded[11] = crockford[((b[6]&7)<<2)|((b[7]&192)>>6)]
	encoded[12] = crockford[(b[7]&62)>>1]
	encoded[13] = crockford[((b[7]&1)<<4)|((b[8]&240)>>4)]
	encoded[14] = crockford[((b[8]&15)<<1)|((b[9]&128)>>7)]
	encoded[15] = crockford[(b[9]&124)>>2]
	encoded[16] = crockford[((b[9]&3)<<3)|((b[10]&224)>>5)]
	encoded[17] = crockford[b[10]&31]
	encoded[18] = crockford[(b[11]&248)>>3]
	encoded[19] = crockford[((b[11]&7)<<2)|((b[12]&192)>>6)]
	encoded[20] = crockford[(b[12]&62)>>1]
	encoded[21] = crockford[((b[12]&1)<<4)|((b[13]&240)>>4)]
	encoded[22] = crockford[((b[13]&15)<<1)|((b[14]&128)>>7)]
	encoded[23] = crockford[(b[14]&124)>>2]
	encoded[24] = crockford[((b[14]&3)<<3)|((b[15]&224)>>5)]
	encoded[25] = crockford[b[15]&31]
	return string(encoded)
}

func Split(raw string) (Prefix, string, error) {
	underscore := strings.IndexByte(raw, '_')
	if underscore < 0 {
		return "", "", fmt.Errorf("runtime/id: missing prefix separator")
	}
	prefix := Prefix(raw[:underscore+1])
	if !DefaultRegistry.Contains(prefix) {
		return "", "", fmt.Errorf("runtime/id: unregistered prefix %q", prefix)
	}
	suffix := raw[underscore+1:]
	if !isULIDSuffix(suffix) {
		return "", "", fmt.Errorf("runtime/id: invalid ulid suffix")
	}
	return prefix, suffix, nil
}

func Validate(raw string) error {
	_, _, err := Split(raw)
	return err
}

func IsValid(raw string) bool {
	return Validate(raw) == nil
}

func isULIDSuffix(suffix string) bool {
	if len(suffix) != ulidLength {
		return false
	}
	// ULID is a 128-bit value encoded into 26 Crockford characters (130 bits).
	// The first character therefore only admits 0-7; accepting 8-Z creates a
	// non-canonical value that cannot round-trip through independent encoders.
	if suffix[0] < '0' || suffix[0] > '7' {
		return false
	}
	for _, ch := range suffix {
		if !isCrockford(ch) {
			return false
		}
	}
	return true
}

func isCrockford(ch rune) bool {
	return (ch >= '0' && ch <= '9') ||
		(ch >= 'A' && ch <= 'H') ||
		(ch >= 'J' && ch <= 'K') ||
		(ch >= 'M' && ch <= 'N') ||
		(ch >= 'P' && ch <= 'T') ||
		(ch >= 'V' && ch <= 'Z')
}
