package main

import (
	"strings"
	"testing"
)

func TestCanonicalRequestEnumMembersUsesMetadataDartMemberMapping(t *testing.T) {
	members, err := canonicalRequestEnumMembers(
		fieldDef{
			Name: "profileVisibility",
			ClientEnumMembers: map[string]string{
				"private": "privateProfile",
			},
		},
		[]string{"public", "friends", "private"},
	)
	if err != nil {
		t.Fatalf("canonicalRequestEnumMembers() error = %v", err)
	}
	want := []canonicalRequestEnumMember{
		{WireValue: "public", DartMember: "public"},
		{WireValue: "friends", DartMember: "friends"},
		{WireValue: "private", DartMember: "privateProfile"},
	}
	if len(members) != len(want) {
		t.Fatalf("members = %#v, want %#v", members, want)
	}
	for index := range want {
		if members[index] != want[index] {
			t.Fatalf("members[%d] = %#v, want %#v", index, members[index], want[index])
		}
	}
}

func TestRequestFieldWireExpressionUsesMetadataDartMemberMapping(t *testing.T) {
	got, err := requestFieldWireExpression(
		"request.profileVisibility",
		fieldDef{
			Name:           "profileVisibility",
			Type:           "ProfileVisibility",
			EnumRef:        "ProfileVisibility",
			ClientDartType: "ProfileVisibility",
			ClientWire:     "canonicalEnum",
			ClientEnumMembers: map[string]string{
				"private": "privateProfile",
			},
		},
		false,
		map[string][]string{
			"ProfileVisibility": {"public", "friends", "private"},
		},
	)
	if err != nil {
		t.Fatalf("requestFieldWireExpression() error = %v", err)
	}
	want := "switch (request.profileVisibility) { ProfileVisibility.public => \"public\", ProfileVisibility.friends => \"friends\", ProfileVisibility.privateProfile => \"private\", }"
	if got != want {
		t.Fatalf("requestFieldWireExpression() = %q, want %q", got, want)
	}
}

func TestCanonicalRequestEnumMembersRejectsUnknownWireMapping(t *testing.T) {
	_, err := canonicalRequestEnumMembers(
		fieldDef{
			Name: "profileVisibility",
			ClientEnumMembers: map[string]string{
				"owner_only": "ownerOnly",
			},
		},
		[]string{"public", "friends", "private"},
	)
	if err == nil || !strings.Contains(err.Error(), "unknown canonical value") {
		t.Fatalf("error = %v, want unknown canonical value failure", err)
	}
}

func TestCanonicalRequestEnumMembersRejectsMemberCollision(t *testing.T) {
	_, err := canonicalRequestEnumMembers(
		fieldDef{
			Name: "state",
			ClientEnumMembers: map[string]string{
				"in_review": "accepted",
			},
		},
		[]string{"in_review", "accepted"},
	)
	if err == nil || !strings.Contains(err.Error(), "map to Dart member") {
		t.Fatalf("error = %v, want Dart member collision failure", err)
	}
}

func TestValidateCanonicalRequestEnumFieldRejectsDetachedMemberMapping(t *testing.T) {
	err := validateCanonicalRequestEnumField(
		fieldDef{
			Name:           "state",
			Type:           "String",
			ClientDartType: "String",
			ClientEnumMembers: map[string]string{
				"accepted": "accepted",
			},
		},
		map[string][]string{
			"ReviewState": {"accepted"},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "requires client_wire canonicalEnum") {
		t.Fatalf("error = %v, want detached mapping failure", err)
	}
}

func TestRequestModelFingerprintIncludesEnumMemberMapping(t *testing.T) {
	base := requestModelSpec{
		Name: "UpdatePrivacySettingsCommand",
		Fields: []fieldDef{{
			Name:           "profileVisibility",
			Type:           "ProfileVisibility",
			EnumRef:        "ProfileVisibility",
			ClientDartType: "ProfileVisibility",
			ClientWire:     "canonicalEnum",
		}},
	}
	mapped := base
	mapped.Fields = append([]fieldDef(nil), base.Fields...)
	mapped.Fields[0].ClientEnumMembers = map[string]string{
		"private": "privateProfile",
	}
	if requestModelFingerprint(base) == requestModelFingerprint(mapped) {
		t.Fatal("request model fingerprint ignores client_enum_members")
	}
}
