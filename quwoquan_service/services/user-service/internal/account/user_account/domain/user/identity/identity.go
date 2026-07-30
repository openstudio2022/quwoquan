// Package identity owns the one canonical UserAccount and Persona identity shape.
package identity

import (
	"fmt"
	"strconv"
	"strings"

	xxhash "github.com/cespare/xxhash/v2"
)

const (
	SlotCount    = 16384
	HashFunction = "xxhash64"

	// canonicalFormatMarker is a frozen byte segment of every identity already
	// persisted in production-shaped stores. It is not a negotiated contract
	// version and has no alternative value.
	canonicalFormatMarker = "01"
	ownerIDPrefix         = "uo"
	personaIDPrefix       = "us"
	entropyLength         = 26
	shardHexLength        = 4
)

var canonicalOriginCodes = map[string]struct{}{
	"ad": {},
	"ph": {},
	"f1": {},
	"f2": {},
	"f3": {},
	"mg": {},
}

// OwnerID is the parsed canonical account identity. Its logical shard is
// derived from origin and entropy and must match the encoded shard exactly.
type OwnerID struct {
	raw          string
	originCode   string
	logicalShard int
	entropy      string
}

func NewOwnerID(originCode, entropy string) (OwnerID, error) {
	if !canonicalOriginCode(originCode) {
		return OwnerID{}, fmt.Errorf("invalid owner identity origin")
	}
	if !lowercaseCrockfordEntropy(entropy) {
		return OwnerID{}, fmt.Errorf("invalid owner identity entropy")
	}
	logicalShard := ComputeLogicalShard(originCode, entropy)
	raw := fmt.Sprintf(
		"%s_%s_%s_%04x_%s",
		ownerIDPrefix,
		canonicalFormatMarker,
		originCode,
		logicalShard,
		entropy,
	)
	return OwnerID{
		raw:          raw,
		originCode:   originCode,
		logicalShard: logicalShard,
		entropy:      entropy,
	}, nil
}

func ParseOwnerID(raw string) (OwnerID, error) {
	parts := strings.Split(raw, "_")
	if len(parts) != 5 || parts[0] != ownerIDPrefix ||
		parts[1] != canonicalFormatMarker ||
		!canonicalOriginCode(parts[2]) || !lowerHex(parts[3], shardHexLength) ||
		!lowercaseCrockfordEntropy(parts[4]) {
		return OwnerID{}, fmt.Errorf("invalid canonical owner identity")
	}
	logicalShard, err := strconv.ParseUint(parts[3], 16, 16)
	if err != nil || logicalShard >= SlotCount {
		return OwnerID{}, fmt.Errorf("invalid canonical owner identity shard")
	}
	expectedShard := ComputeLogicalShard(parts[2], parts[4])
	if int(logicalShard) != expectedShard {
		return OwnerID{}, fmt.Errorf("owner identity shard does not match its routing hash")
	}
	return OwnerID{
		raw:          raw,
		originCode:   parts[2],
		logicalShard: int(logicalShard),
		entropy:      parts[4],
	}, nil
}

func IsCanonicalOwnerID(raw string) bool {
	_, err := ParseOwnerID(raw)
	return err == nil
}

func (id OwnerID) String() string {
	return id.raw
}

func (id OwnerID) OriginCode() string {
	return id.originCode
}

func (id OwnerID) LogicalShard() int {
	return id.logicalShard
}

func (id OwnerID) LogicalShardHex() string {
	return fmt.Sprintf("%04x", id.logicalShard)
}

func (id OwnerID) Entropy() string {
	return id.entropy
}

func (id OwnerID) RoutingKey() string {
	routingHash := ComputeRoutingHash(id.originCode, id.entropy)
	return fmt.Sprintf("%04x%016x", id.logicalShard, routingHash)
}

// PersonaID is the parsed canonical public Persona identity.
type PersonaID struct {
	raw          string
	logicalShard int
	entropy      string
}

func NewPersonaID(logicalShardHex, entropy string) (PersonaID, error) {
	if !lowerHex(logicalShardHex, shardHexLength) ||
		!lowercaseCrockfordEntropy(entropy) {
		return PersonaID{}, fmt.Errorf("invalid persona identity")
	}
	logicalShard, err := strconv.ParseUint(logicalShardHex, 16, 16)
	if err != nil || logicalShard >= SlotCount {
		return PersonaID{}, fmt.Errorf("invalid persona identity shard")
	}
	raw := fmt.Sprintf(
		"%s_%s_%s_%s",
		personaIDPrefix,
		canonicalFormatMarker,
		logicalShardHex,
		entropy,
	)
	return PersonaID{
		raw:          raw,
		logicalShard: int(logicalShard),
		entropy:      entropy,
	}, nil
}

func ParsePersonaID(raw string) (PersonaID, error) {
	parts := strings.Split(raw, "_")
	if len(parts) != 4 || parts[0] != personaIDPrefix ||
		parts[1] != canonicalFormatMarker {
		return PersonaID{}, fmt.Errorf("invalid canonical persona identity")
	}
	personaID, err := NewPersonaID(parts[2], parts[3])
	if err != nil || personaID.raw != raw {
		return PersonaID{}, fmt.Errorf("invalid canonical persona identity")
	}
	return personaID, nil
}

func IsCanonicalPersonaID(raw string) bool {
	_, err := ParsePersonaID(raw)
	return err == nil
}

func (id PersonaID) String() string {
	return id.raw
}

func (id PersonaID) LogicalShard() int {
	return id.logicalShard
}

func (id PersonaID) LogicalShardHex() string {
	return fmt.Sprintf("%04x", id.logicalShard)
}

func (id PersonaID) Entropy() string {
	return id.entropy
}

func ComputeLogicalShard(originCode, entropy string) int {
	return int(ComputeRoutingHash(originCode, entropy) % SlotCount)
}

func ComputeRoutingHash(originCode, entropy string) uint64 {
	return xxhash.Sum64String(
		canonicalFormatMarker + "|" + originCode + "|" + entropy,
	)
}

func canonicalOriginCode(value string) bool {
	_, ok := canonicalOriginCodes[value]
	return ok
}

func lowercaseCrockfordEntropy(value string) bool {
	if len(value) != entropyLength {
		return false
	}
	for _, current := range value {
		if (current >= '0' && current <= '9') ||
			(current >= 'a' && current <= 'h') ||
			(current >= 'j' && current <= 'k') ||
			(current >= 'm' && current <= 'n') ||
			(current >= 'p' && current <= 't') ||
			(current >= 'v' && current <= 'z') {
			continue
		}
		return false
	}
	return true
}

func lowerHex(value string, length int) bool {
	if len(value) != length {
		return false
	}
	for _, current := range value {
		if (current >= '0' && current <= '9') ||
			(current >= 'a' && current <= 'f') {
			continue
		}
		return false
	}
	return true
}
