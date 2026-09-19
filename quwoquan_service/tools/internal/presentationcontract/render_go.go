package presentationcontract

import (
	"fmt"
	"go/format"
	"strconv"
	"strings"
)

// RenderGo 生成同包 helper，复用对象生成器已有的 ClientContentPresentationContract 类型。
func (m Model) RenderGo(packageName string) ([]byte, error) {
	var b strings.Builder
	fmt.Fprintf(&b, "// Code generated from contracts/metadata/_shared/types.yaml. DO NOT EDIT.\npackage %s\n", packageName)
	b.WriteString(`
import (
 "bytes"
 "crypto/sha256"
 "encoding/json"
 "fmt"
 "io"
 "sort"
)
`)
	for _, baseline := range []bool{false, true} {
		name := "Compiled"
		if baseline {
			name = "MissingDeclaration"
		}
		digest, err := m.Digest(m.Collections(baseline))
		if err != nil {
			return nil, err
		}
		fmt.Fprintf(&b, "const %sContentPresentationContractDigest = %q\n", name, digest)
		fmt.Fprintf(&b, "func %sContentPresentationContract() ClientContentPresentationContract { return ClientContentPresentationContract{\n", name)
		for _, f := range m.Fields {
			values := f.Values
			if baseline {
				values = f.Baseline
			}
			fmt.Fprintf(&b, "%s: []%s{%s},\n", goName(f.Name), f.EnumRef, quoted(values))
		}
		fmt.Fprintf(&b, "ContractDigest: %sContentPresentationContractDigest,\n} }\n", name)
	}
	b.WriteString("func CanonicalClientContentPresentationContract(c ClientContentPresentationContract) ([]byte,error) {\n normalized:=map[string][]string{}\n")
	for _, f := range m.Fields {
		fmt.Fprintf(&b, "{\n values:=c.%s\n if values==nil || len(values)>%d{return nil,fmt.Errorf(%q)}\n", goName(f.Name), f.MaxItems, f.Name+": expected bounded non-null array")
		fmt.Fprintf(&b, "allowed:=map[string]bool{%s}\n", boolMap(f.Values))
		b.WriteString("seen:=map[string]bool{}\n ordered:=make([]string,0,len(values))\n for _,member:=range values {v:=string(member);if !allowed[v] || seen[v]{return nil,fmt.Errorf(\"invalid or duplicate capability member %q\",v)};seen[v]=true;ordered=append(ordered,v)}\n sort.Strings(ordered)\n")
		fmt.Fprintf(&b, "normalized[%q]=ordered\n}\n", f.Name)
	}
	b.WriteString(`
 var buf bytes.Buffer
 enc:=json.NewEncoder(&buf);enc.SetEscapeHTML(false)
 if err:=enc.Encode(normalized);err!=nil{return nil,err}
 return bytes.TrimSuffix(buf.Bytes(),[]byte("\n")),nil
}

func DigestClientContentPresentationContract(c ClientContentPresentationContract) (string,error) {
 raw,err:=CanonicalClientContentPresentationContract(c);if err!=nil{return "",err}
 return fmt.Sprintf("sha256:%x",sha256.Sum256(raw)),nil
}

// ValidateClientContentPresentationContract 只验证声明完整性；摘要不是授权凭据。
func ValidateClientContentPresentationContract(c ClientContentPresentationContract) error {
 digest,err:=DigestClientContentPresentationContract(c);if err!=nil{return err}
 if c.ContractDigest!=digest{return fmt.Errorf("client presentation contract digest mismatch")}
 return nil
}

// DecodeClientContentPresentationContract 仅无字节代表整份声明缺席；null 与非法对象均拒绝。
func DecodeClientContentPresentationContract(raw []byte) (ClientContentPresentationContract,error) {
 if len(raw)==0{return MissingDeclarationContentPresentationContract(),nil}
 var c ClientContentPresentationContract
 if bytes.Equal(bytes.TrimSpace(raw),[]byte("null")){return c,fmt.Errorf("client presentation contract must be an object")}
 // 先逐字段解码以拒绝重复键；标准 json.Unmarshal 本身采用 last-wins。
 d:=json.NewDecoder(bytes.NewReader(raw))
 token,err:=d.Token();if err!=nil || token!=json.Delim('{'){return c,fmt.Errorf("client presentation contract must be an object")}
 fields:=map[string]json.RawMessage{}
 for d.More(){
  key,err:=d.Token();if err!=nil{return c,err};name,ok:=key.(string);if !ok{return c,fmt.Errorf("invalid object key")}
  if _,exists:=fields[name];exists{return c,fmt.Errorf("duplicate capability field %q",name)}
  switch name {case "contentTypes", "listObjectKinds", "openSurfaces", "presentationRecipes", "contractDigest": default:return c,fmt.Errorf("unknown capability field %q",name)}
  var value json.RawMessage;if err:=d.Decode(&value);err!=nil{return c,err};fields[name]=value
 }
 if _,err:=d.Token();err!=nil{return c,err}
 var extra any;if err:=d.Decode(&extra);err!=io.EOF{return c,fmt.Errorf("trailing capability JSON")}
 if len(fields)!=5{return c,fmt.Errorf("expected all capability fields and digest")}
 strict:=json.NewDecoder(bytes.NewReader(raw));strict.DisallowUnknownFields()
 if err:=strict.Decode(&c);err!=nil{return c,err}
 if err:=ValidateClientContentPresentationContract(c);err!=nil{return c,err}
 return c,nil
}
`)
	return format.Source([]byte(b.String()))
}

func goName(s string) string { return strings.ToUpper(s[:1]) + s[1:] }
func quoted(values []string) string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = strconv.Quote(v)
	}
	return strings.Join(out, ",")
}
func boolMap(values []string) string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = strconv.Quote(v) + ":true"
	}
	return strings.Join(out, ",")
}
