package httpcodec

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDecodeStrictJSONRequiresOneKnownShape(t *testing.T) {
	var body struct {
		Name string `json:"name"`
	}
	request := httptest.NewRequest("POST", "/", strings.NewReader(`{"name":"one"}`))
	if err := DecodeStrictJSON(request, &body); err != nil || body.Name != "one" {
		t.Fatalf("decode body=%+v err=%v", body, err)
	}
	request = httptest.NewRequest("POST", "/", strings.NewReader(`{"name":"one","unknown":true}`))
	if err := DecodeStrictJSON(request, &body); err == nil {
		t.Fatal("unknown field must fail")
	}
	request = httptest.NewRequest("POST", "/", strings.NewReader(`{"name":"one"}{"name":"two"}`))
	if err := DecodeStrictJSON(request, &body); err == nil {
		t.Fatal("multiple JSON values must fail")
	}
}

func TestParsePositiveEntityTag(t *testing.T) {
	for _, raw := range []string{`7`, `"7"`, `W/"7"`} {
		if version, err := ParsePositiveEntityTag(raw); err != nil || version != 7 {
			t.Fatalf("raw=%q version=%d err=%v", raw, version, err)
		}
	}
	if _, err := ParsePositiveEntityTag("0"); err == nil {
		t.Fatal("zero version must fail")
	}
}
