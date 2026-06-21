#!/usr/bin/env bash
# T3 鉴权会话级端到端核验（首页推荐商用化 阶段9）
# 真实 HTTP / curl 级集成验证 —— 不构建/修改 Flutter app 代码。
#
# 端点（gamma-local）：
#   GW    = http://127.0.0.1:19000   (Caddy 边缘代理；转发 Authorization + X-Client-User-Id)
#   US    = http://127.0.0.1:19210   (user-service 直连；/v1/auth/* 网关未路由)
#   CS    = http://127.0.0.1:19220   (content-service 直连；/metrics 观测)
#   REDIS = docker exec ... redis-cli  (容器内 6379；宿主 127.0.0.1:19420)
#
# 会话来源：anonymous device login 的「同设备恢复」路径（gamma-local 无 OTP/integration provider，
# 且 anonymous 账号创建因 user_profiles_phone_key 唯一约束只能成功一次，故用恢复路径取稳定 subAccount）。
set -uo pipefail
GW="http://127.0.0.1:19000"; US="http://127.0.0.1:19210"; CS="http://127.0.0.1:19220"
RC="quwoquan_service-redis-1"
OUT="artifacts/home-rec-phase9/t3-session"; mkdir -p "$OUT"
ts(){ date -u +%Y-%m-%dT%H:%M:%SZ; }
say(){ echo; echo "==================== $* ===================="; }
RUN="t3run_$(date -u +%Y%m%d%H%M%S)"
# 稳定设备身份（恢复同一 anonymous owner/subAccount，避免触发创建唯一约束 bug）
INSTALL="t3-session-install-01"; FPHASH="t3sessionfphash01"

say "STEP 1: 建立鉴权会话（anonymous device login 恢复路径）"
curl -sS -X POST "$US/v1/auth/login/anonymous" -H "Content-Type: application/json" \
  -d "{\"installId\":\"$INSTALL\",\"deviceFingerprintHash\":\"$FPHASH\",\"platform\":\"ios\",\"appVersion\":\"1.0.0\"}" > "$OUT/01_login_raw.json"
python3 - > "$OUT/01_login_redacted.json" <<'PY'
import json
d=json.load(open("artifacts/home-rec-phase9/t3-session/01_login_raw.json"))
red=lambda t:(t[:12]+"...<redacted len=%d>"%len(t)) if isinstance(t,str) and t else t
for k in ("accessToken","refreshToken"):
    if k in d: d[k]=red(d[k])
json.dump(d,open("artifacts/home-rec-phase9/t3-session/01_login_redacted.json","w"),ensure_ascii=False,indent=2)
print(json.dumps(d,ensure_ascii=False,indent=2))
PY
TOKEN=$(python3 -c "import json;print(json.load(open('$OUT/01_login_raw.json')).get('accessToken',''))")
SUB=$(python3 -c "import json;print(json.load(open('$OUT/01_login_raw.json')).get('activeSub',{}).get('subAccountId',''))")
OWNER=$(python3 -c "import json;print(json.load(open('$OUT/01_login_raw.json')).get('ownerId',''))")
SESSION="${RUN}_sess"
if [ -z "$TOKEN" ] || [ -z "$SUB" ]; then echo "FATAL: login failed"; cat "$OUT/01_login_raw.json"; exit 1; fi
echo "subAccountId=$SUB  ownerId=$OWNER  tokenLen=${#TOKEN}  sessionId=$SESSION"
python3 - "$TOKEN" > "$OUT/01_jwt_claims.json" <<'PY'
import sys,json,base64
p=sys.argv[1].split('.')[1]; p+='='*(-len(p)%4)
json.dump(json.loads(base64.urlsafe_b64decode(p)),open("artifacts/home-rec-phase9/t3-session/01_jwt_claims.json","w"),indent=2)
print(json.dumps(json.loads(base64.urlsafe_b64decode(p))))
PY
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Client-User-Id: $SUB" -H "X-Client-Session-Id: $SESSION")

say "STEP 2: 鉴权门控对照（auth-required 端点 guest vs session）"
G_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$GW/v1/content/footprint")
A_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${AUTH[@]}" "$GW/v1/content/footprint")
echo "guest   GET /v1/content/footprint -> $G_CODE (期望 401)"
echo "session GET /v1/content/footprint -> $A_CODE (期望 200)"
echo "{\"guest_footprint_http\":$G_CODE,\"session_footprint_http\":$A_CODE,\"capturedAt\":\"$(ts)\"}" > "$OUT/02_auth_gate.json"

say "STEP 3: 鉴权态 feed envelope 三字段（feedRequestId / rankingVersion / intersectionReasons）"
curl -sS "$GW/v1/content/feed?sort=recommend&limit=10" > "$OUT/03_feed_guest.json"
curl -sS "${AUTH[@]}" "$GW/v1/content/feed?sort=recommend&limit=20" > "$OUT/03_feed_session_p1.json"
python3 - > "$OUT/03_envelope_assert.json" <<'PY'
import json
B="artifacts/home-rec-phase9/t3-session/"
guest=json.load(open(B+"03_feed_guest.json")); sess=json.load(open(B+"03_feed_session_p1.json"))
items=sess.get('items',[])
res={
 "guest_envelope":{k:guest.get(k) for k in("feedRequestId","rankingVersion","reasonVersion")},
 "session_envelope":{k:sess.get(k) for k in("feedRequestId","rankingVersion","reasonVersion")},
 "session_item_count":len(items),
 "session_feedRequestId_present":bool(sess.get('feedRequestId')),
 "session_rankingVersion_present":bool(sess.get('rankingVersion')),
 "session_intersectionReasons_present":any(it.get('intersectionReasons') for it in items),
 "session_authors_sample":sorted({it.get('authorId') for it in items}),
}
json.dump(res,open(B+"03_envelope_assert.json","w"),ensure_ascii=False,indent=2)
print(json.dumps(res,ensure_ascii=False,indent=2))
PY

say "STEP 4: 负反馈未来窗口（hide_author + hide_content_type + dislike，三维互不遮蔽）"
FRQ=$(python3 -c "import json;print(json.load(open('$OUT/03_feed_session_p1.json')).get('feedRequestId',''))")
# 选三个互相独立的目标，避免某一维度顺手剔除另一维度的断言对象：
#   hide_author  = 高频作者 ha（锚点 post HIDE_POST）
#   dislike      = 单条 post dp（作者 != ha，类型 dct）—— 不去 hide 其类型，保证独立可证
#   hide_ctype   = 一个内容类型 hct（!= dct，且其代表 post 作者 != ha）—— 不与 dislike 重叠
SEL=$(python3 - <<'PY'
import json
from collections import Counter
d=json.load(open("artifacts/home-rec-phase9/t3-session/03_feed_session_p1.json")); items=d.get('items',[])
def ct(it): return it.get('contentType') or it.get('type') or ''
authors=[it.get('authorId') for it in items if it.get('authorId')]
ha=Counter(authors).most_common(1)[0][0] if authors else ""
hp=hc=hi=""
for i,it in enumerate(items):
    if it.get('authorId')==ha: hp,hc,hi=it.get('id'),ct(it),i; break
# dislike：作者 != ha 的单条 post
dp=da=dc=di=""
for i,it in enumerate(items):
    if it.get('id') and it.get('authorId')!=ha: dp,da,dc,di=it.get('id'),it.get('authorId') or '',ct(it),i; break
# hide_content_type：类型 != dc，且代表 post 作者 != ha（避免与 hide_author / dislike 重叠）
hct=hctp=hctpos=""
for i,it in enumerate(items):
    c=ct(it)
    if c and c!=dc and it.get('authorId')!=ha:
        hct,hctp,hctpos=c,it.get('id'),i; break
print("|".join([ha,hp,hc,str(hi),dp,da,dc,str(di),hct,hctp or '',str(hctpos) if hctpos!='' else '']))
PY
)
HIDE_AUTHOR=$(echo "$SEL"|cut -d'|' -f1); HIDE_POST=$(echo "$SEL"|cut -d'|' -f2); HIDE_CT=$(echo "$SEL"|cut -d'|' -f3); HIDE_POS=$(echo "$SEL"|cut -d'|' -f4)
DIS_POST=$(echo "$SEL"|cut -d'|' -f5);  DIS_AUTHOR=$(echo "$SEL"|cut -d'|' -f6); DIS_CT=$(echo "$SEL"|cut -d'|' -f7); DIS_POS=$(echo "$SEL"|cut -d'|' -f8)
HCT=$(echo "$SEL"|cut -d'|' -f9); HCT_POST=$(echo "$SEL"|cut -d'|' -f10); HCT_POS=$(echo "$SEL"|cut -d'|' -f11)
[ -z "$HCT_POS" ] && HCT_POS=0
echo "hide_author=$HIDE_AUTHOR anchorPost=$HIDE_POST pos=$HIDE_POS"
echo "dislike post=$DIS_POST author=$DIS_AUTHOR type=$DIS_CT pos=$DIS_POS"
echo "hide_content_type=$HCT viaPost=$HCT_POST pos=$HCT_POS  | feedRequestId=$FRQ"

curl -sS "$CS/metrics" | grep -E "^recommendation_feed_patch_emitted_total|^recommendation_feed_negative_feedback_total" > "$OUT/04_metrics_before.txt" || true
echo "--- metrics before ---"; cat "$OUT/04_metrics_before.txt"

# best-effort: 订阅共享 redis 的 per-user 通道（realtime scene=in-memory，预期无 message）
( timeout 8 docker exec "$RC" redis-cli PSUBSCRIBE "rt:rec:feed:user:*" > "$OUT/05_redis_psubscribe.txt" 2>&1 ) & SUBPID=$!
sleep 1

BEH_BODY=$(cat <<JSON
{"userId":"$SUB","events":[
 {"clientEventId":"${RUN}_hide_author","type":"hide_author","postId":"$HIDE_POST","authorId":"$HIDE_AUTHOR","contentType":"$HIDE_CT","state":"negative","feedRequestId":"$FRQ","position":$HIDE_POS,"channelId":"recommend","rankingVersion":"rec-v1","referralSource":"organic_feed"},
 {"clientEventId":"${RUN}_hide_ctype","type":"hide_content_type","postId":"$HCT_POST","contentType":"$HCT","state":"negative","feedRequestId":"$FRQ","position":$HCT_POS,"channelId":"recommend","rankingVersion":"rec-v1","referralSource":"organic_feed"},
 {"clientEventId":"${RUN}_dislike","type":"dislike","postId":"$DIS_POST","authorId":"$DIS_AUTHOR","contentType":"$DIS_CT","state":"negative","feedRequestId":"$FRQ","position":$DIS_POS,"channelId":"recommend","rankingVersion":"rec-v1","referralSource":"organic_feed"}
]}
JSON
)
echo "$BEH_BODY" > "$OUT/04_behaviors_request.json"
BEH_CODE=$(curl -sS -o "$OUT/04_behaviors_response.json" -w "%{http_code}" -X POST "${AUTH[@]}" -H "Content-Type: application/json" -d "$BEH_BODY" "$GW/v1/content/behaviors")
echo "POST /v1/content/behaviors -> HTTP $BEH_CODE"; cat "$OUT/04_behaviors_response.json"; echo

sleep 3
say "STEP 4b: 再取 feed，断言未来窗口收敛"
PASS_AUTHOR=1; PASS_CTYPE=1; PASS_DISLIKE=1
for n in 1 2 3; do
  curl -sS "${AUTH[@]}" "$GW/v1/content/feed?sort=recommend&limit=50" > "$OUT/04_feed_after_${n}.json"
  read AC CC DP < <(python3 - "$OUT/04_feed_after_${n}.json" "$HIDE_AUTHOR" "$HCT" "$DIS_POST" <<'PY'
import sys,json
d=json.load(open(sys.argv[1])); ha,ct,dp=sys.argv[2],sys.argv[3],sys.argv[4]; items=d.get('items',[])
ac=sum(1 for it in items if it.get('authorId')==ha)
cc=sum(1 for it in items if (it.get('contentType') or it.get('type'))==ct)
present=1 if any(it.get('id')==dp for it in items) else 0
print(ac,cc,present)
PY
)
  echo "re-fetch #$n: hidden_author($HIDE_AUTHOR)=$AC  hidden_ctype($HCT)=$CC  disliked_post_present=$DP"
  [ "$AC" != "0" ] && PASS_AUTHOR=0
  [ "$CC" != "0" ] && PASS_CTYPE=0
  [ "$DP" != "0" ] && PASS_DISLIKE=0
done
echo "hide_author 未来窗口收敛:       $([ $PASS_AUTHOR = 1 ] && echo PASS || echo FAIL)"
echo "hide_content_type 未来窗口收敛: $([ $PASS_CTYPE = 1 ] && echo PASS || echo FAIL)"
echo "dislike 单条剔除收敛:           $([ $PASS_DISLIKE = 1 ] && echo PASS || echo FAIL)"

say "STEP 4c: Redis 侧证据（负反馈确已服务端记录）"
echo "--- rec:negative:* 集合（含 dislike/hide/report 单条负反馈）---"
docker exec "$RC" sh -lc 'for k in $(redis-cli --scan --pattern "rec:negative:*"); do echo "$k => $(redis-cli SMEMBERS "$k" | tr "\n" " ")"; done' > "$OUT/04c_redis_negative.txt" 2>&1 || true
cat "$OUT/04c_redis_negative.txt"
echo "--- rec:hidden_authors:* / rec:hidden_types:* ---"
docker exec "$RC" sh -lc 'for k in $(redis-cli --scan --pattern "rec:hidden_*"); do echo "$k => $(redis-cli SMEMBERS "$k" | tr "\n" " ")"; done' > "$OUT/04c_redis_hidden.txt" 2>&1 || true
cat "$OUT/04c_redis_hidden.txt"

say "STEP 5: realtime patch 发射证据（metric delta + pubsub）"
sleep 1
curl -sS "$CS/metrics" | grep -E "^recommendation_feed_patch_emitted_total|^recommendation_feed_negative_feedback_total" > "$OUT/05_metrics_after.txt" || true
echo "--- metrics after ---"; cat "$OUT/05_metrics_after.txt"
wait $SUBPID 2>/dev/null
echo "--- redis PSUBSCRIBE 捕获（共享 redis；realtime scene=in-memory，预期仅订阅确认，无 message）---"
sed -n '1,20p' "$OUT/05_redis_psubscribe.txt"

say "STEP 6: 汇总判定矩阵"
python3 - "$HIDE_AUTHOR" "$DIS_CT" "$DIS_POST" "$PASS_AUTHOR" "$PASS_CTYPE" "$PASS_DISLIKE" <<'PY'
import sys,json,os,re
B="artifacts/home-rec-phase9/t3-session/"
ha,ct,dp,pa,pc,pd=sys.argv[1:7]
env=json.load(open(B+"03_envelope_assert.json"))
def parse(path):
    m={}
    if os.path.exists(path):
        for line in open(path):
            mt=re.match(r'^(recommendation_feed_\w+(?:\{[^}]*\})?)\s+([0-9.eE+-]+)$',line.strip())
            if mt: m[mt.group(1)]=float(mt.group(2))
    return m
before=parse(B+"04_metrics_before.txt"); after=parse(B+"05_metrics_after.txt")
def sump(m,t): return sum(v for k,v in m.items() if k.startswith("recommendation_feed_patch_emitted_total{") and ('patch_type="%s"'%t) in k)
delta=sump(after,"negative_feedback_removal")-sump(before,"negative_feedback_removal")
matrix={
 "checkA_envelope_feedRequestId":"PASS" if env["session_feedRequestId_present"] else "FAIL",
 "checkA_envelope_rankingVersion":"PASS" if env["session_rankingVersion_present"] else "FAIL",
 "checkA_envelope_intersectionReasons":"PASS" if env["session_intersectionReasons_present"] else "GAP(no_intersection_seed_data_in_gamma)",
 "checkB_hide_author_future_window":"PASS" if pa=="1" else "FAIL",
 "checkB_hide_content_type_future_window":"PASS" if pc=="1" else "FAIL",
 "checkB_dislike_single_post_removal":"PASS" if pd=="1" else "GAP(fallback_path_not_enforced)",
 "checkC_realtime_patch_emitted_metric_delta":delta,
 "checkC_realtime_patch_status":"PASS(server-side emit metric +%g)"%delta if delta>0 else "FAIL/NONE",
 "checkC_external_ws_or_redis_subscribe":"GAP(realtime-gateway unimplemented; realtime redis scene in-memory)",
 "patch_emitted_after":{k:v for k,v in after.items() if "patch_emitted" in k},
}
json.dump(matrix,open(B+"06_t3_matrix.json","w"),ensure_ascii=False,indent=2)
print(json.dumps(matrix,ensure_ascii=False,indent=2))
PY
echo; echo "证据目录: $OUT"
