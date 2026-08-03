package main

import (
	"fmt"
	"sort"
	"strings"
	"unicode"
)

type canonicalRequestEnumMember struct {
	WireValue  string
	DartMember string
}

// canonicalRequestEnumMembers resolves the Dart member used for every
// canonical wire value. Most enums use the deterministic wire-to-lowerCamel
// projection; metadata declares only the exceptional public Dart ABI member
// names (for example, `private` -> `privateProfile`).
func canonicalRequestEnumMembers(
	field fieldDef,
	values []string,
) ([]canonicalRequestEnumMember, error) {
	canonicalValues := make(map[string]struct{}, len(values))
	for _, value := range values {
		canonicalValues[value] = struct{}{}
	}

	overrides := make(map[string]string, len(field.ClientEnumMembers))
	for rawWire, rawMember := range field.ClientEnumMembers {
		wire := strings.TrimSpace(rawWire)
		member := strings.TrimSpace(rawMember)
		if wire == "" || member == "" {
			return nil, fmt.Errorf(
				"field %s client_enum_members requires non-empty wire and Dart member names",
				field.Name,
			)
		}
		if _, exists := canonicalValues[wire]; !exists {
			return nil, fmt.Errorf(
				"field %s client_enum_members maps unknown canonical value %q",
				field.Name,
				wire,
			)
		}
		if !isDartIdentifier(member) {
			return nil, fmt.Errorf(
				"field %s client_enum_members maps %q to invalid Dart member %q",
				field.Name,
				wire,
				member,
			)
		}
		overrides[wire] = member
	}

	result := make([]canonicalRequestEnumMember, 0, len(values))
	seenMembers := map[string]string{}
	for _, value := range values {
		member := overrides[value]
		if member == "" {
			member = canonicalDartEnumMemberName(field.EnumRef, value)
		}
		if previous, exists := seenMembers[member]; exists {
			return nil, fmt.Errorf(
				"field %s canonical enum values %q and %q map to Dart member %s",
				field.Name,
				previous,
				value,
				member,
			)
		}
		seenMembers[member] = value
		result = append(result, canonicalRequestEnumMember{
			WireValue:  value,
			DartMember: member,
		})
	}
	return result, nil
}

// canonicalDartEnumMemberName keeps wire values language-neutral while
// deriving one stable Dart member name for every request and response use.
// ProfileVisibility.private historically cannot use the ambiguous bare
// `private` member in the public App contract, so the semantic enum name is
// part of its deterministic projection rather than a field-local override.
func canonicalDartEnumMemberName(enumName, wireValue string) string {
	if strings.TrimSpace(enumName) == "ProfileVisibility" &&
		strings.TrimSpace(wireValue) == "private" {
		return "privateProfile"
	}
	return toDartValueName(wireValue)
}

func canonicalRequestEnumMembersFingerprint(values map[string]string) string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+"="+values[key])
	}
	return strings.Join(parts, ",")
}

func isDartIdentifier(value string) bool {
	for index, current := range value {
		if index == 0 {
			if current != '_' && !unicode.IsLetter(current) {
				return false
			}
			continue
		}
		if current != '_' && !unicode.IsLetter(current) && !unicode.IsDigit(current) {
			return false
		}
	}
	return value != ""
}
