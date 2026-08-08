package main

import (
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// 最小信封样例，形状与 content/content/post/projections/
// content_discovery_feed_page_slice.yaml 同构：单页 item 上限、object card 数量
// 有界、cursor 与 expiry 成对出现、policyDigest 必须是 canonical sha256 字形。
const envelopeAdmissionProjectionFixture = `
read_model: EnvelopeAdmissionPageSlice
fields:
- name: items
  type: '[]EnvelopeAdmissionItem'
  max_items: 20
- name: objectCards
  type: '[]EnvelopeAdmissionCard'
  max_items: 8
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - paginationExpiresAt
- name: paginationExpiresAt
  type: timestamp
  nullable: true
- name: policyDigest
  type: string
  nullable: true
  format: canonical_sha256
`

func renderEnvelopeAdmissionFixtureForTest(t *testing.T) string {
	t.Helper()
	var projection projectionFile
	if err := yaml.Unmarshal(
		[]byte(envelopeAdmissionProjectionFixture),
		&projection,
	); err != nil {
		t.Fatalf("decode envelope admission projection: %v", err)
	}
	fields, err := canonicalProjectionResponseFields(projection.Fields)
	if err != nil {
		t.Fatalf("map canonical projection response fields: %v", err)
	}
	model := requestModelSpec{
		Name:   strings.TrimSpace(projection.ReadModel),
		Fields: fields,
	}
	var output strings.Builder
	if err := renderDomainResponseModel(&output, model); err != nil {
		t.Fatalf("render envelope admission response model: %v", err)
	}
	renderDomainDecoderHelpers(
		&output,
		map[string]requestModelSpec{model.Name: model},
		true,
	)
	return output.String()
}

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md#gwt-001
func TestDomainResponseDecoderEnforcesEnvelopeAdmission(t *testing.T) {
	generated := renderEnvelopeAdmissionFixtureForTest(t)

	for name, want := range map[string]string{
		"单页 item 上限": `_requiredBoundedList(map["items"], '$path.items', max: 20)`,
		"object card 数量有界": `_requiredBoundedList(map["objectCards"], ` +
			`'$path.objectCards', max: 8)`,
		"cursor 与 expiry 配对": `_requireCoPresentFields(map, ` +
			`const <String>{"nextCursor", "paginationExpiresAt"}, path);`,
		"policyDigest sha256 字形": `_requiredCanonicalSha256Digest(` +
			`map["policyDigest"], '$path.policyDigest')`,
		"bounded list helper":  "List<Object?> _requiredBoundedList(",
		"co-present helper":    "void _requireCoPresentFields(",
		"canonical sha256 helper": "String _requiredCanonicalSha256Digest(" +
			"Object? value, String path) {",
		"canonical sha256 单一真相源": "isCanonicalSha256Digest(",
	} {
		if !strings.Contains(generated, want) {
			t.Fatalf(
				"generated envelope decoder misses %s (%q); got:\n%s",
				name,
				want,
				generated,
			)
		}
	}
}

// 表达位必须 fail-closed：未知 format、非 string 上的 format、悬空或非 nullable
// 的 co_present_with 都不得静默降级成无约束 decoder。
func TestDomainResponseDecoderRejectsInvalidAdmissionDeclarations(t *testing.T) {
	for name, fixture := range map[string]string{
		"unknown format": `
read_model: BadFormatSlice
fields:
- name: digest
  type: string
  nullable: true
  format: md5
`,
		"format on non-string": `
read_model: BadFormatTypeSlice
fields:
- name: expiresAt
  type: timestamp
  nullable: true
  format: canonical_sha256
`,
		"co_present_with references unknown field": `
read_model: BadPairingSlice
fields:
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - missingField
`,
		"co_present_with references required field": `
read_model: RequiredPairingSlice
fields:
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - feedRequestId
- name: feedRequestId
  type: string
`,
	} {
		t.Run(name, func(t *testing.T) {
			var projection projectionFile
			if err := yaml.Unmarshal([]byte(fixture), &projection); err != nil {
				t.Fatalf("decode projection: %v", err)
			}
			fields, err := canonicalProjectionResponseFields(projection.Fields)
			if err != nil {
				return
			}
			var output strings.Builder
			if err := renderDomainResponseModel(&output, requestModelSpec{
				Name:   strings.TrimSpace(projection.ReadModel),
				Fields: fields,
			}); err == nil {
				t.Fatalf(
					"invalid envelope admission declaration must fail closed; got:\n%s",
					output.String(),
				)
			}
		})
	}
}
