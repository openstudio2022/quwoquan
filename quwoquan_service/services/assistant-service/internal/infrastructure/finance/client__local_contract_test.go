package finance

import (
	"reflect"
	"testing"
)

func TestNormalizeSymbolsUsesTypedRequestSymbolsAndQuery(t *testing.T) {
	got := normalizeSymbols(
		[]string{"600519.SH", "invalid", "AAPL"},
		"关注 600519.SH、TSLA 和普通文字",
	)
	want := []string{"600519.SH", "AAPL", "TSLA"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("symbols=%#v, want %#v", got, want)
	}
}
