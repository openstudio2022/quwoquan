package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestDecodeMembersCarriesCompleteTypedMemberShape(t *testing.T) {
	var document yaml.Node
	if err := yaml.Unmarshal([]byte(`
Line:
  kind: owned_entity
  identity: [lineId, locale]
  cardinality: many
  max_cardinality: 16
  ownership: aggregate
  write_access: aggregate_facade_only
  description: aggregate-owned localized line
Revision:
  kind: value_object
  cardinality: many
  max_cardinality: 32
  ownership: aggregate
  append_only: true
  description: immutable revision snapshot
`), &document); err != nil {
		t.Fatal(err)
	}
	members, err := decodeMembers(document.Content[0])
	if err != nil {
		t.Fatalf("decode complete members: %v", err)
	}
	if len(members) != 2 || members[0].Name != "Line" ||
		members[0].Kind != "owned_entity" ||
		strings.Join(members[0].Identity, ",") != "lineId,locale" ||
		members[0].Cardinality != "many" || members[0].MaxCardinality != 16 ||
		members[0].Ownership != "aggregate" ||
		members[0].WriteAccess != "aggregate_facade_only" ||
		members[0].Description != "aggregate-owned localized line" {
		t.Fatalf("owned member shape = %+v", members)
	}
	if !members[1].AppendOnly || members[1].Description != "immutable revision snapshot" {
		t.Fatalf("value member shape = %+v", members[1])
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestDecodeMembersRejectsAliasesAndIndependentMemberShape(t *testing.T) {
	for name, source := range map[string]string{
		"cardinality alias":   `Member: {kind: owned_entity, identity: [memberId], cardinality: 1:N, max_cardinality: 2, ownership: aggregate, write_access: aggregate_facade_only, description: member}`,
		"missing identity":    `Member: {kind: owned_entity, cardinality: many, max_cardinality: 2, ownership: aggregate, write_access: aggregate_facade_only, description: member}`,
		"value write":         `Member: {kind: value_object, cardinality: one, max_cardinality: 1, ownership: aggregate, write_access: aggregate_facade_only, description: member}`,
		"unknown field":       `Member: {kind: value_object, cardinality: one, max_cardinality: 1, ownership: aggregate, description: member, owner: Post}`,
		"missing description": `Member: {kind: value_object, cardinality: one, max_cardinality: 1, ownership: aggregate}`,
		"duplicate identity":  `Member: {kind: owned_entity, identity: [memberId, memberId], cardinality: many, max_cardinality: 2, ownership: aggregate, write_access: aggregate_facade_only, description: member}`,
		"invalid identity":    `Member: {kind: owned_entity, identity: [member_id], cardinality: many, max_cardinality: 2, ownership: aggregate, write_access: aggregate_facade_only, description: member}`,
		"singleton many":      `Member: {kind: value_object, cardinality: many, max_cardinality: 1, ownership: aggregate, description: member}`,
		"false append only":   `Member: {kind: value_object, cardinality: many, max_cardinality: 2, ownership: aggregate, append_only: false, description: member}`,
		"noncanonical name":   `member: {kind: value_object, cardinality: one, max_cardinality: 1, ownership: aggregate, description: member}`,
	} {
		t.Run(name, func(t *testing.T) {
			var document yaml.Node
			if err := yaml.Unmarshal([]byte(source), &document); err != nil {
				t.Fatal(err)
			}
			_, err := decodeMembers(document.Content[0])
			if err == nil {
				t.Fatalf("%s was accepted", name)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestLoadObjectRejectsMembersOnNonAggregateRoot(t *testing.T) {
	metadataDir := t.TempDir()
	path := filepath.Join(metadataDir, "content", "content", "post", "object.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(`
kind: projection
description: projection object
identity: {fields: [id], version_source: checkpoint}
access: {commands: none, queries: named_reader, cross_context: public_contract_only}
relationships: []
members:
  Slice: {kind: value_object, cardinality: one, max_cardinality: 1, ownership: aggregate, description: illegal}
`), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err := loadObject(metadataDir, path)
	if err == nil || !strings.Contains(err.Error(), "only allowed on aggregate_root") {
		t.Fatalf("non-aggregate members error = %v", err)
	}
}
