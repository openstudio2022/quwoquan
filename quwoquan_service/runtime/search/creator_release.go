package search

// wire 唯一来源：contracts/metadata/_shared/types.yaml#CreatorSearch*。
// 本包只提供跨服务传输值及其 canonical 校验，不拥有账户、release 或准备状态。
import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"time"
)

type creatorQueryBindingKey struct{}

func WithCreatorQueryBinding(ctx context.Context, binding *ReleaseQueryPreparationBinding) context.Context {
	return context.WithValue(ctx, creatorQueryBindingKey{}, binding)
}
func CreatorQueryBinding(ctx context.Context) *ReleaseQueryPreparationBinding {
	binding, _ := ctx.Value(creatorQueryBindingKey{}).(*ReleaseQueryPreparationBinding)
	return binding
}

var ErrCreatorSourceInvalid = errors.New("Creator source closure invalid")
var ErrCreatorProjectionConflict = errors.New("Creator projection source conflict")

var creatorDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type ReleaseCandidateBinding struct {
	Environment    string `json:"environment" bson:"environment"`
	SourceOwner    string `json:"sourceOwner" bson:"sourceOwner"`
	ReleaseID      string `json:"releaseId" bson:"releaseId"`
	ManifestDigest string `json:"manifestDigest" bson:"manifestDigest"`
}
type ReleaseQueryPreparationBinding struct {
	Release                   ReleaseCandidateBinding `json:"release" bson:"release"`
	Slice                     string                  `json:"slice" bson:"slice"`
	SchemaGeneration          string                  `json:"schemaGeneration" bson:"schemaGeneration"`
	ProviderBindingGeneration string                  `json:"providerBindingGeneration" bson:"providerBindingGeneration"`
}
type CreatorSearchPublicSnapshot struct {
	ObjectType       string   `json:"objectType" bson:"objectType"`
	ObjectID         string   `json:"objectId" bson:"objectId"`
	CreatorID        string   `json:"creatorId" bson:"creatorId"`
	PersonaID        string   `json:"personaId" bson:"personaId"`
	AuthorID         string   `json:"authorId" bson:"authorId"`
	UserHandle       string   `json:"userHandle" bson:"userHandle"`
	DisplayName      string   `json:"displayName" bson:"displayName"`
	Bio              *string  `json:"bio" bson:"bio"`
	AvatarURL        *string  `json:"avatarUrl" bson:"avatarUrl"`
	AvatarAssetID    *string  `json:"avatarAssetId" bson:"avatarAssetId"`
	AvatarAccessMode *string  `json:"avatarAccessMode" bson:"avatarAccessMode"`
	IdentityTags     []string `json:"identityTags" bson:"identityTags"`
	PostCount        int64    `json:"postCount" bson:"postCount"`
	SourceVersion    int64    `json:"sourceVersion" bson:"sourceVersion"`
	ProfileDigest    string   `json:"profileDigest" bson:"profileDigest"`
	SourceDigest     string   `json:"sourceDigest" bson:"sourceDigest"`
	UpdatedAt        string   `json:"updatedAt" bson:"updatedAt"`
}
type CreatorSearchCandidateSnapshot struct {
	Release             ReleaseCandidateBinding       `json:"release" bson:"release"`
	SourceClosureDigest string                        `json:"sourceClosureDigest" bson:"sourceClosureDigest"`
	ObjectSetDigest     string                        `json:"objectSetDigest" bson:"objectSetDigest"`
	SnapshotDigest      string                        `json:"snapshotDigest" bson:"snapshotDigest"`
	Profiles            []CreatorSearchPublicSnapshot `json:"profiles" bson:"profiles"`
}
type ReleaseQueryClassEvidence struct {
	QueryClass      string `json:"queryClass" bson:"queryClass"`
	ObjectSetDigest string `json:"objectSetDigest" bson:"objectSetDigest"`
	DocumentsDigest string `json:"documentsDigest" bson:"documentsDigest"`
}
type ReleaseQueryReadinessProof struct {
	Binding                ReleaseQueryPreparationBinding `json:"binding" bson:"binding"`
	SourceClosureDigest    string                         `json:"sourceClosureDigest" bson:"sourceClosureDigest"`
	ObjectSetDigest        string                         `json:"objectSetDigest" bson:"objectSetDigest"`
	SnapshotDigest         string                         `json:"snapshotDigest" bson:"snapshotDigest"`
	DocumentsDigest        string                         `json:"documentsDigest" bson:"documentsDigest"`
	CheckpointVersion      int64                          `json:"checkpointVersion" bson:"checkpointVersion"`
	QueryClasses           []ReleaseQueryClassEvidence    `json:"queryClasses" bson:"queryClasses"`
	PremiumAdmissionDigest *string                        `json:"premiumAdmissionDigest" bson:"premiumAdmissionDigest"`
	PremiumObjectSetDigest *string                        `json:"premiumObjectSetDigest" bson:"premiumObjectSetDigest"`
	VerifiedAt             string                         `json:"verifiedAt" bson:"verifiedAt"`
	ValidUntil             string                         `json:"validUntil" bson:"validUntil"`
	ProofDigest            string                         `json:"proofDigest" bson:"proofDigest"`
}

func CreatorCanonicalDigest(value any, omit string) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var canonical any
	if err = decoder.Decode(&canonical); err != nil {
		return "", err
	}
	if omit != "" {
		object, ok := canonical.(map[string]any)
		if !ok {
			return "", fmt.Errorf("canonical object required")
		}
		delete(object, omit)
	}
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	if err = encoder.Encode(canonical); err != nil {
		return "", err
	}
	return fmt.Sprintf("sha256:%x", sha256.Sum256(bytes.TrimSuffix(buf.Bytes(), []byte("\n")))), nil
}
func (b ReleaseCandidateBinding) Validate() error {
	if b.Environment != "alpha" && b.Environment != "beta" && b.Environment != "gamma" && b.Environment != "prod" {
		return fmt.Errorf("invalid release environment")
	}
	if b.SourceOwner != "qwq_data" || strings.TrimSpace(b.ReleaseID) == "" || len([]byte(b.ReleaseID)) > 160 || !creatorDigestPattern.MatchString(b.ManifestDigest) {
		return fmt.Errorf("invalid release binding")
	}
	return nil
}
func (b ReleaseQueryPreparationBinding) Validate(environment, generation string) error {
	if err := b.Release.Validate(); err != nil {
		return err
	}
	if b.Release.Environment != environment || (b.Slice != "creator_search" && b.Slice != "post_search" && b.Slice != "homepage_search" && b.Slice != "recommendation") || !creatorDigestPattern.MatchString(b.SchemaGeneration) || !creatorDigestPattern.MatchString(generation) || b.ProviderBindingGeneration != generation {
		return fmt.Errorf("preparation deployment binding mismatch")
	}
	return nil
}
func (b ReleaseQueryPreparationBinding) ID() string {
	digest, _ := CreatorCanonicalDigest(b, "")
	return digest
}
func validCreatorTime(raw string) bool {
	t, err := time.Parse(time.RFC3339Nano, raw)
	return err == nil && !t.IsZero() && t.UTC().Format(time.RFC3339Nano) == raw
}
func (p CreatorSearchPublicSnapshot) Validate() error {
	if p.ObjectType != ObjectTypeUserProfile || p.ObjectID != p.PersonaID || strings.TrimSpace(p.ObjectID) == "" || strings.TrimSpace(p.CreatorID) == "" || strings.TrimSpace(p.AuthorID) == "" || strings.TrimSpace(p.UserHandle) == "" || strings.TrimSpace(p.DisplayName) == "" || p.IdentityTags == nil || len(p.IdentityTags) > 100 || p.PostCount < 0 || p.SourceVersion < 1 || !creatorDigestPattern.MatchString(p.ProfileDigest) || !validCreatorTime(p.UpdatedAt) {
		return fmt.Errorf("invalid creator public snapshot")
	}
	if p.AvatarURL != nil || p.AvatarAssetID != nil || p.AvatarAccessMode != nil {
		if p.AvatarURL == nil || p.AvatarAssetID == nil || p.AvatarAccessMode == nil || strings.TrimSpace(*p.AvatarURL) == "" || strings.TrimSpace(*p.AvatarAssetID) == "" || (*p.AvatarAccessMode != "public" && *p.AvatarAccessMode != "signed_grant") {
			return fmt.Errorf("incomplete creator avatar binding")
		}
	}
	digest, err := CreatorCanonicalDigest(p, "sourceDigest")
	if err != nil || digest != p.SourceDigest {
		return fmt.Errorf("creator public digest mismatch")
	}
	return nil
}
func (s CreatorSearchCandidateSnapshot) ObjectDigest() string {
	rows := make([]map[string]string, 0, len(s.Profiles))
	for _, p := range s.Profiles {
		rows = append(rows, map[string]string{"objectType": p.ObjectType, "objectId": p.ObjectID})
	}
	digest, _ := CreatorCanonicalDigest(rows, "")
	return digest
}
func (s *CreatorSearchCandidateSnapshot) Seal() error {
	sort.Slice(s.Profiles, func(i, j int) bool { return s.Profiles[i].ObjectID < s.Profiles[j].ObjectID })
	for i := range s.Profiles {
		d, err := CreatorCanonicalDigest(s.Profiles[i], "sourceDigest")
		if err != nil {
			return err
		}
		s.Profiles[i].SourceDigest = d
	}
	s.ObjectSetDigest = s.ObjectDigest()
	d, err := CreatorCanonicalDigest(s, "snapshotDigest")
	s.SnapshotDigest = d
	return err
}
func (s CreatorSearchCandidateSnapshot) Validate() error {
	if err := s.Release.Validate(); err != nil {
		return err
	}
	if !creatorDigestPattern.MatchString(s.SourceClosureDigest) || s.Profiles == nil || len(s.Profiles) > 500 {
		return fmt.Errorf("invalid creator closure")
	}
	seen := map[string]bool{}
	previous := ""
	for _, p := range s.Profiles {
		if err := p.Validate(); err != nil {
			return err
		}
		if p.ObjectID <= previous {
			return fmt.Errorf("creator objects must be unique and sorted")
		}
		previous = p.ObjectID
		for _, key := range []string{"creator:" + p.CreatorID, "author:" + p.AuthorID, "persona:" + p.PersonaID} {
			if seen[key] {
				return fmt.Errorf("duplicate creator identity")
			}
			seen[key] = true
		}
	}
	d, err := CreatorCanonicalDigest(s, "snapshotDigest")
	if err != nil || d != s.SnapshotDigest || s.ObjectDigest() != s.ObjectSetDigest {
		return fmt.Errorf("creator closure digest mismatch")
	}
	return nil
}
func (p *ReleaseQueryReadinessProof) Seal() error {
	d, err := CreatorCanonicalDigest(p, "proofDigest")
	p.ProofDigest = d
	return err
}
func (p ReleaseQueryReadinessProof) Validate(binding ReleaseQueryPreparationBinding, snapshot SearchReleaseCandidateSnapshot) error {
	if err := snapshot.Validate(); err != nil {
		return err
	}
	digest, err := CreatorCanonicalDigest(p, "proofDigest")
	if err != nil || digest != p.ProofDigest || p.Binding != binding || p.SnapshotDigest != snapshot.SnapshotDigest() || p.SourceClosureDigest != snapshot.SourceClosureDigest() || p.ObjectSetDigest != snapshot.ObjectSetDigest() || p.CheckpointVersion < 1 || !creatorDigestPattern.MatchString(p.DocumentsDigest) || !validCreatorTime(p.VerifiedAt) || !validCreatorTime(p.ValidUntil) || p.PremiumAdmissionDigest != nil || p.PremiumObjectSetDigest != nil {
		return fmt.Errorf("invalid release query proof")
	}
	start, _ := time.Parse(time.RFC3339Nano, p.VerifiedAt)
	end, _ := time.Parse(time.RFC3339Nano, p.ValidUntil)
	if !end.After(start) {
		return fmt.Errorf("invalid proof time window")
	}
	expected := map[string]bool{"result": true, "suggest": true, "retrieval": true, "ids": true, "count": true, "facet": true}
	for _, row := range p.QueryClasses {
		if !expected[row.QueryClass] || row.ObjectSetDigest != p.ObjectSetDigest || row.DocumentsDigest != p.DocumentsDigest {
			return fmt.Errorf("incomplete query-class evidence")
		}
		delete(expected, row.QueryClass)
	}
	if len(expected) != 0 {
		return fmt.Errorf("missing query-class evidence")
	}
	return nil
}

// DecodeCreatorValue 限制未知字段、重复键和尾随值；字段必填性由各值 Validate 闭合。
func DecodeCreatorValue(reader io.Reader, target any) error {
	raw, err := io.ReadAll(io.LimitReader(reader, 4<<20+1))
	if err != nil {
		return err
	}
	if len(raw) > 4<<20 {
		return fmt.Errorf("creator payload exceeds bound")
	}
	tokens := json.NewDecoder(bytes.NewReader(raw))
	if err = checkCreatorJSON(tokens); err != nil {
		return err
	}
	if _, err = tokens.Token(); err != io.EOF {
		return fmt.Errorf("trailing creator JSON")
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(target); err != nil {
		return err
	}
	var shape any
	if err := json.Unmarshal(raw, &shape); err != nil {
		return err
	}
	return requireCreatorFields(shape, reflect.TypeOf(target))
}

// 所有contract字段都必须出现，NULLABLE只能显式null；不把false/0当缺字段。
func requireCreatorFields(shape any, typ reflect.Type) error {
	if typ.Kind() == reflect.Pointer {
		if shape == nil {
			return nil
		}
		return requireCreatorFields(shape, typ.Elem())
	}
	switch typ.Kind() {
	case reflect.Struct:
		if typ == reflect.TypeOf(time.Time{}) {
			return nil
		}
		object, ok := shape.(map[string]any)
		if !ok {
			return fmt.Errorf("creator value must be object")
		}
		for i := 0; i < typ.NumField(); i++ {
			field := typ.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			if name == "" || name == "-" {
				continue
			}
			value, found := object[name]
			if !found {
				return fmt.Errorf("missing creator field %s", name)
			}
			if value == nil && field.Type.Kind() != reflect.Pointer {
				return fmt.Errorf("null creator field %s", name)
			}
			if err := requireCreatorFields(value, field.Type); err != nil {
				return err
			}
		}
	case reflect.Slice:
		if shape == nil {
			return fmt.Errorf("creator array cannot be null")
		}
		rows, ok := shape.([]any)
		if !ok {
			return fmt.Errorf("creator array required")
		}
		for _, row := range rows {
			if err := requireCreatorFields(row, typ.Elem()); err != nil {
				return err
			}
		}
	}
	return nil
}

func checkCreatorJSON(d *json.Decoder) error {
	t, err := d.Token()
	if err != nil {
		return err
	}
	delimiter, ok := t.(json.Delim)
	if !ok {
		return nil
	}
	if delimiter == '{' {
		seen := map[string]bool{}
		for d.More() {
			key, err := d.Token()
			if err != nil {
				return err
			}
			k, ok := key.(string)
			if !ok || seen[k] {
				return fmt.Errorf("duplicate JSON field")
			}
			seen[k] = true
			if err = checkCreatorJSON(d); err != nil {
				return err
			}
		}
	} else if delimiter == '[' {
		for d.More() {
			if err = checkCreatorJSON(d); err != nil {
				return err
			}
		}
	} else {
		return fmt.Errorf("unexpected JSON delimiter")
	}
	_, err = d.Token()
	return err
}
