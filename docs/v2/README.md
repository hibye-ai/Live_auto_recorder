# Live Auto Recorder 2.0 preview

This is an additive, opt-in implementation on top of the existing recording
engines. It is not a production 2.0 release declaration. The root version remains
unchanged until the release gates below have been met.

## Deployment boundaries

- One application process/container per data directory. The v2 OS instance lock
  is acquired before recording engines start. Do not run multiple Uvicorn workers.
- SQLite and job metadata require host-local persistent storage. A NAS's own
  local disk is suitable; an SMB/NFS-mounted SQLite WAL database is not.
- Existing media directories and recording names are preserved. Register media
  and archive roots before processing. A missing or unsafe root blocks the job.
- All new media outputs retain their original inputs. New archive jobs are
  local/NAS copies. Remote rclone jobs remain legacy operations and are not
  represented as safely migrated v2 jobs.
- Windows can use the legacy recorder; the v2 durable media worker fails closed
  where POSIX no-follow file-descriptor guarantees are unavailable.
- Keep the default loopback binding. Additional hostnames require
  `LAR_ALLOWED_HOSTS`; v2 mode rejects foreign Host/Origin browser requests.
  This is not an internet-facing multi-user authentication system.

## Integrated v1 interface

The existing v1 dashboard, sidebar, recording controls and advanced settings stay
at their original routes. Broadcast library and job status are embedded features
at `/broadcasts` and `/jobs` using the same console. The separate v2 application
shell has been removed. Old `/v2` links redirect to the matching console route.

Build `frontend` with `npm ci && npm run build`, then start the normal Python
entrypoint. The built files are `/static/library/library.js` and `library.css`;
Docker compiles these in its build stage without a Node runtime server.

Reading existing broadcasts does not require `LAR_V2_ENABLED`. With the default
`false`, file existence and validation remain unknown unless actually observed,
and durable jobs are explicitly unavailable. The existing recorder, advanced
settings, file browser, and legacy operations remain the normal control surfaces.
Enabling the durable engine is a separate opt-in with the storage/rollback
requirements below. Opening the library does not enable it or run a migration.

## Persistence and restart

New job/channel state uses a sidecar v2 SQLite database. The existing recording
catalog remains the compatibility source for ongoing engine events; normalized
v2 artifacts retain legacy identity mappings. This is an additive projection,
not a destructive schema replacement or bidirectional configuration sync.

Jobs are committed before execution. Attempts carry generation-fenced leases.
Expired leases alone do not authorize relaunch: process identity and absence
must be established. Uncertain ownership blocks execution. Cancellation of a
running operation is a request until process termination is confirmed.

Temporary output belongs to its attempt. Validated output is published without
replacing a destination. Publication intent is durable before the file appears;
unresolved publication is reconciled on restart. Database and NAS writes are
not a cross-filesystem transaction, and power-loss zero loss is not promised.

Notification delivery keeps the existing durable queue. An acknowledgement
lost between external delivery and database commit may duplicate a notification.
V2 verification does not trigger legacy delete-after-archive policies.

## Rollback

Before enabling v2, stop recording, keep the current image digest, and create and
verify a consistent SQLite/configuration backup. Keep secrets private and leave
recording files in place. Run the migration dry-run first; inspect rejected rows
and counts. Do not overwrite the only backup.

Before new writes, restore the previous image plus pre-migration data after
stopping the application. After v2 has produced new media or state, preserve the
v2 database and inventory all new files before any rollback. Restore previous
metadata from backup and re-index new media explicitly. Merely disabling the engine
flag is not a downgrade or a configuration rollback. No automatic reverse
schema conversion is provided.

## Safe read-only deployment preflight

Before enabling `LAR_V2_ENABLED`, run `python scripts/check_v2_readiness.py --data-dir data --recordings-root recordings` on the host. This verifies the existing mount marker, data directory locality and free space **without creating or deleting any files**. For NAS volumes, pass the real host-mounted directory and `--expected-marker` to pin its identity. Passing preflight does not replace real recording/NAS release tests. See [release validation](RELEASE_VALIDATION.md).

## Release gates still requiring real hardware

Do not promote this preview on unit-test counts alone. A release requires:

1. Actual CHZZK and YouTube record/stop/reconnect/verify/merge smoke tests on both
   amd64 and arm64. A multiarch image build does not prove ARM64 runtime behavior.
2. At least 24 hours on a representative NAS with recording plus postprocessing,
   tracking memory/CPU/I/O/WAL growth and queue delay.
3. Real mount disappearance/return, full disk and process/container-kill tests
   across claim, output, publication and database commit boundaries.
4. A stopped-service backup/restore rehearsal with representative existing data,
   recording path reconciliation and validated backup integrity.
5. Review of the preserved legacy advanced controls and unsupported transitions
   before claiming full screen or feature parity.

See `IMPLEMENTATION.md` for the twelve implementation slices and exact local
verification evidence. No remote push, PR, production deployment, or release is
implied by this preview.

## Storage marker and capture-crash reconciliation

V2 recording admission requires an existing `.lar-storage-id` file at
`RECORDINGS_ROOT`. Provision it deliberately on the intended mounted volume
before enabling v2. Do not create it automatically in an empty fallback mount
path. Set `LAR_V2_RECORDINGS_MARKER` to a different relative marker path and
`LAR_V2_RECORDINGS_MARKER_VALUE` to enforce a specific identity value. The worker
and capture admission both check it; a missing marker yields a visible block.
The path must be writable and have at least 64 MiB available; existing operations
policy can impose stricter free-space limits.

After an unclean app exit, `v2-capture-active.json` deliberately prevents any new
capture. Unlike new media jobs, the retained capture engines do not yet have a
fully gated durable launch contract. The marker covers the launch-to-PID-record
gap and includes known process identities. This is a safety block, not an
automatic recorder restart promise.

For recovery, stop the app; inspect and terminate any surviving recorder process
and descendants, confirming their PID/start-time/boot identity instead of killing
an unrelated reused PID. Preserve the marker and catalog for diagnosis. Only
once all prior capture processes are confirmed absent, move the marker aside
into a private diagnostic backup and restart. If ownership is uncertain, leave
the block in place. Normal verified shutdown removes the marker automatically.
Never remove it while the app is running. New durable verification/media jobs
recover independently through their fenced attempts/publication reconciliation.

Legacy automatic transcoding, detached split postprocessing, delete-after-merge,
delete-after-archive short-recording cleanup and legacy retention deletion are disabled in v2 mode. Use the
explicit durable merge/recovery controls; originals stay intact. Legacy live
configuration restore is blocked while v2 is enabled because it cannot reconcile
new intent/job state. Stop the service and follow the offline restore procedure.
Advanced bitrate transcoding and live restore parity are not claimed by this
preview.

## Reproducible local checks

From a Python environment with `requirements.txt` installed:

```
python scripts/test_regressions.py
python -m compileall -q app_entry.py lar_app module
python scripts/release.py check
python scripts/smoke_v2_media.py
python scripts/smoke_v2_app.py
cd frontend
npm ci
npm run build
npm test
npm run test:browser
```

The media smoke uses only temporary synthetic fixtures with real FFmpeg/FFprobe.
The app smoke copies code into a temporary empty-channel install, checks two
clean startup/shutdown cycles, then verifies a real SIGKILL/restart remains
blocked for capture reconciliation. Neither accesses a real platform account or
production recordings. Browser tests require a supported Chromium sandbox; their
absence must not be represented as visual/mobile validation.

---

## Korean release notes

기존 CHZZK·YouTube 녹화 엔진과 영상 경로를 유지한 채, 새 화면과 영속 작업 계층을 연결했습니다. 정식 2.0 출시판이 아니라 검토·시험용 미리보기입니다.

### 구현된 내용

- 기존 v1 화면에 방송 보관함·상세·작업 상태 통합 (별도 v2 셸 제거)
- 자동 녹화 의도와 실제 녹화 상태 분리, 중복 명령 방지
- 검증·복구본 생성·컨테이너 변환·합치기·로컬/NAS 보관 복사의 영속 작업
- 재시도·취소·실행권 검사·중단된 결과물 대조와 복구
- 원본 보존, 기존 결과 덮어쓰기 방지, 저장소 표식 확인
- 마이그레이션 사전 점검·백업·체크섬·이력 보존
- 설정 응답과 알림 테스트 오류에서 비밀값 노출 방지

### 중요한 사용 조건

기존 v1 화면과 메뉴를 유지하며 /broadcasts와 /jobs에서 새 기능을 확인합니다. 이전 /v2 주소는 해당 기존 화면으로 연결됩니다. LAR_V2_ENABLED=false에서도 기존 방송 이력을 조회할 수 있으며 영속 작업 기능은 비활성으로 표시됩니다. 영속 엔진을 별도로 켜려면 DB는 로컬 영속 디스크에 두고, RECORDINGS_ROOT의 실제 볼륨에 .lar-storage-id 표식을 준비해야 합니다. 화면 변경만으로 엔진을 켜거나 데이터를 이전하지 않습니다.

비정상 종료 뒤 기존 녹화 프로세스가 남았는지 확실하지 않으면 새 녹화를 차단합니다. 기존 프로세스의 종료를 확인한 뒤 오프라인 복구 절차를 따라야 합니다. 자동으로 중복 녹화를 시작하지 않도록 보수적으로 처리했습니다.

### 아직 완료로 보지 않는 범위

- 실제 CHZZK·YouTube 방송, ARM64 실행, NAS 장애·24시간 연속 시험
- 브라우저 캡처·모바일 조작·실제 앱 검사는 CI에서 실행하며, 현재 결과는 [PR #85](https://github.com/no-rahc/Live_auto_recorder/pull/85)의 정확한 커밋 검사와 첨부 화면을 참조
- 고급 비트레이트 인코딩과 실시간 설정 복원: 새 작업 계층으로 완전 이관하지 않음
- 일부 고급 설정·채널 편집 화면과 원격 rclone 보관: 기존 기능 유지
- 비정상 종료된 녹화 엔진의 완전 자동 재개: 안전한 수동 대조 절차 적용

운영 서버·기기·원격 저장소에는 배포하거나 반영하지 않았습니다. TEST_RESULTS.txt는 초기 엔진 미리보기의 과거 검증 기록이며, 현재 통합 화면 검증은 PR의 CI 결과를 기준으로 합니다.
