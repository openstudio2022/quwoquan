# V7 运行态终验证据 (2026-05-31 23:11:37)

## 静态门禁
- make gate: [gate] OK (gate-full2 静态段证绿)

## local-gamma T3/T4 (make gate-local-gamma)
[local-gamma:t3] status: passed
[gamma-patrol-matrix] run on iPhone 17 Pro (DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB, ios)
[local-gamma:t4] status: passed
[local-gamma] status: passed

## 4 探针 (含修复后的 user-service 19210)
19000: {"status":"ok","checks":{"mongodb":"ok","redis":"ok"}}

19100: {"status":"ok","checks":{"mongodb":"ok","redis":"ok"}}

19010: {"status":"ok","checks":{"mongodb":"ok","redis":"ok"}}

19210: {"status":"ok","checks":{"mongodb":"ok","postgres":"ok","red

## make test-contract
FAIL_count=0
ok_pkg_count=19
docker-unavailable graceful-skip(rtc/L2)=8

## 修复的 4 处运行态阻塞
1. start_media_origin media_root -> state/local/gamma/media (媒体源404)
2. Makefile 导出 LOCAL_GAMMA_USER_PORT=19210 (user-service发布端口对齐探针)
3. start_colima_tunnels 增加 user_port 隧道 (colima host 直达 user-service)
4. docker-compose.gamma-local healthcheck start_period 10s->240s (go-run首编译, 防compose中止gamma-proxy)
