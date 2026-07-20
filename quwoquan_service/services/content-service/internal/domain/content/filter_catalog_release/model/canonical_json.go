package model

import (
	"bytes"
	"fmt"
	"math"
	"strconv"
	"unicode/utf8"
)

// encodeCanonicalCatalog 实现 sha256:qwq-filter-catalog-canonical-json。
// 字段按 Unicode scalar value 顺序写入；数组顺序由调用方按目录契约预先归一化。
func encodeCanonicalCatalog(payload canonicalCatalogPayload) ([]byte, error) {
	var encoded bytes.Buffer
	encoded.WriteString(`{"categories":[`)
	for index, category := range payload.Categories {
		if index > 0 {
			encoded.WriteByte(',')
		}
		if err := appendCanonicalCategory(&encoded, category); err != nil {
			return nil, err
		}
	}
	encoded.WriteString(`],"presets":[`)
	for index, preset := range payload.Presets {
		if index > 0 {
			encoded.WriteByte(',')
		}
		if err := appendCanonicalPreset(&encoded, preset); err != nil {
			return nil, err
		}
	}
	encoded.WriteString(`],"recommendedFallbackPresetIds":[`)
	for index, presetID := range payload.RecommendedFallbackPresetIDs {
		if index > 0 {
			encoded.WriteByte(',')
		}
		if err := appendCanonicalString(&encoded, presetID); err != nil {
			return nil, err
		}
	}
	encoded.WriteString(`]}`)
	return encoded.Bytes(), nil
}

func appendCanonicalCategory(
	encoded *bytes.Buffer,
	category FilterCategoryDefinition,
) error {
	encoded.WriteString(`{"categoryId":`)
	if err := appendCanonicalString(encoded, category.CategoryID); err != nil {
		return err
	}
	encoded.WriteString(`,"displayNameEn":`)
	if err := appendCanonicalOptionalString(encoded, category.DisplayNameEn); err != nil {
		return err
	}
	encoded.WriteString(`,"displayNameZhHans":`)
	if err := appendCanonicalString(encoded, category.DisplayNameZhHans); err != nil {
		return err
	}
	encoded.WriteString(`,"enabled":`)
	appendCanonicalBool(encoded, category.Enabled)
	encoded.WriteString(`,"sort":`)
	encoded.WriteString(strconv.Itoa(category.Sort))
	encoded.WriteByte('}')
	return nil
}

func appendCanonicalPreset(encoded *bytes.Buffer, preset FilterPresetDefinition) error {
	encoded.WriteString(`{"adjustments":`)
	appendCanonicalAdjustments(encoded, preset.Adjustments)
	encoded.WriteString(`,"categoryId":`)
	if err := appendCanonicalString(encoded, preset.CategoryID); err != nil {
		return err
	}
	encoded.WriteString(`,"defaultStrength":`)
	if err := appendCanonicalNumber(encoded, preset.DefaultStrength); err != nil {
		return err
	}
	encoded.WriteString(`,"displayNameEn":`)
	if err := appendCanonicalOptionalString(encoded, preset.DisplayNameEn); err != nil {
		return err
	}
	encoded.WriteString(`,"displayNameZhHans":`)
	if err := appendCanonicalString(encoded, preset.DisplayNameZhHans); err != nil {
		return err
	}
	encoded.WriteString(`,"enabled":`)
	appendCanonicalBool(encoded, preset.Enabled)
	encoded.WriteString(`,"presetId":`)
	if err := appendCanonicalString(encoded, preset.PresetID); err != nil {
		return err
	}
	encoded.WriteString(`,"sort":`)
	encoded.WriteString(strconv.Itoa(preset.Sort))
	encoded.WriteByte('}')
	return nil
}

func appendCanonicalAdjustments(
	encoded *bytes.Buffer,
	values FilterAdjustmentValues,
) {
	encoded.WriteString(`{"brightness":`)
	appendKnownCanonicalNumber(encoded, values.Brightness)
	encoded.WriteString(`,"contrast":`)
	appendKnownCanonicalNumber(encoded, values.Contrast)
	encoded.WriteString(`,"exposure":`)
	appendKnownCanonicalNumber(encoded, values.Exposure)
	encoded.WriteString(`,"fade":`)
	appendKnownCanonicalNumber(encoded, values.Fade)
	encoded.WriteString(`,"grain":`)
	appendKnownCanonicalNumber(encoded, values.Grain)
	encoded.WriteString(`,"highlight":`)
	appendKnownCanonicalNumber(encoded, values.Highlight)
	encoded.WriteString(`,"lightSense":`)
	appendKnownCanonicalNumber(encoded, values.LightSense)
	encoded.WriteString(`,"saturation":`)
	appendKnownCanonicalNumber(encoded, values.Saturation)
	encoded.WriteString(`,"shadow":`)
	appendKnownCanonicalNumber(encoded, values.Shadow)
	encoded.WriteString(`,"sharpen":`)
	appendKnownCanonicalNumber(encoded, values.Sharpen)
	encoded.WriteString(`,"structure":`)
	appendKnownCanonicalNumber(encoded, values.Structure)
	encoded.WriteString(`,"temperature":`)
	appendKnownCanonicalNumber(encoded, values.Temperature)
	encoded.WriteString(`,"texture":`)
	appendKnownCanonicalNumber(encoded, values.Texture)
	encoded.WriteString(`,"tint":`)
	appendKnownCanonicalNumber(encoded, values.Tint)
	encoded.WriteString(`,"vibrance":`)
	appendKnownCanonicalNumber(encoded, values.Vibrance)
	encoded.WriteByte('}')
}

func appendCanonicalOptionalString(encoded *bytes.Buffer, value *string) error {
	if value == nil {
		encoded.WriteString("null")
		return nil
	}
	return appendCanonicalString(encoded, *value)
}

func appendCanonicalString(encoded *bytes.Buffer, value string) error {
	if !utf8.ValidString(value) {
		return fmt.Errorf("%w: canonical string is not valid UTF-8", ErrInvalidArgument)
	}
	encoded.WriteByte('"')
	for _, character := range value {
		switch character {
		case '"', '\\':
			encoded.WriteByte('\\')
			encoded.WriteRune(character)
		case '\b':
			encoded.WriteString(`\b`)
		case '\t':
			encoded.WriteString(`\t`)
		case '\n':
			encoded.WriteString(`\n`)
		case '\f':
			encoded.WriteString(`\f`)
		case '\r':
			encoded.WriteString(`\r`)
		default:
			if character < 0x20 {
				encoded.WriteString(`\u00`)
				const hexadecimal = "0123456789abcdef"
				encoded.WriteByte(hexadecimal[character>>4])
				encoded.WriteByte(hexadecimal[character&0x0f])
				continue
			}
			encoded.WriteRune(character)
		}
	}
	encoded.WriteByte('"')
	return nil
}

func appendCanonicalBool(encoded *bytes.Buffer, value bool) {
	if value {
		encoded.WriteString("true")
		return
	}
	encoded.WriteString("false")
}

func appendCanonicalNumber(encoded *bytes.Buffer, value float64) error {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Errorf("%w: canonical number must be finite", ErrInvalidArgument)
	}
	appendKnownCanonicalNumber(encoded, value)
	return nil
}

func appendKnownCanonicalNumber(encoded *bytes.Buffer, value float64) {
	if value == 0 {
		encoded.WriteByte('0')
		return
	}
	encoded.WriteString(strconv.FormatFloat(value, 'f', -1, 64))
}
