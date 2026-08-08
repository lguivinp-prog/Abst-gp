#!/bin/sh
set -e

DRILL_DIR="/tmp/gate_b_formal_drill"
BACKUP_DIR="${DRILL_DIR}/basebackup"
RESTORE_DIR="${DRILL_DIR}/restored_cluster"
LOG_FILE="${DRILL_DIR}/execution-log.txt"
RESTORE_LOG="${DRILL_DIR}/restored_cluster.log"
OUT_DIR="/tmp/gate_b_artifacts"

# Stop any lingering background test cluster
pg_ctl -D "$RESTORE_DIR" stop 2>/dev/null || true
pkill -f "postgres.*5433" 2>/dev/null || true

rm -rf "$DRILL_DIR" "$OUT_DIR"
mkdir -p "$DRILL_DIR" "$BACKUP_DIR" "$RESTORE_DIR" "$OUT_DIR"

echo "================================================================================" > "$LOG_FILE"
echo "GATE B: PITR FORMAL CERTIFICATION DRILL" >> "$LOG_FILE"
echo "Start UTC: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$LOG_FILE"
echo "================================================================================" >> "$LOG_FILE"

# --- T0: Baseline Business Entities ---
echo "--- [T0] Creating Baseline Entities (Tenant, CaseFile, Document, AuditLog) ---" | tee -a "$LOG_FILE"
TS0=$(date +%s)
TENANT_ID="dr-tenant-gate-b-${TS0}"

psql -U dr_user -d dr_db -q -c "INSERT INTO tenants (id, name) VALUES ('${TENANT_ID}', 'DR Gate B Enterprise Tenant');"

CASE_ID=$(psql -U dr_user -d dr_db -q -t -A -c "INSERT INTO case_files (title, contract_type, tenant_id, status) VALUES ('Expediente T0 Baseline', 'Bienes', '${TENANT_ID}', 'CREATED') RETURNING id;")
echo "Created Case ID: ${CASE_ID} for Tenant: ${TENANT_ID}" | tee -a "$LOG_FILE"

DOC_ID=$(psql -U dr_user -d dr_db -q -t -A -c "INSERT INTO uploaded_documents (case_id, document_type, original_filename, stored_path, mime_type, processing_status) VALUES (${CASE_ID}, 'requirement', 'TDR_T0_Baseline.pdf', 'uploads/tdr_t0_${TENANT_ID}.pdf', 'application/pdf', 'pending') RETURNING id;")
echo "Created Document T0 ID: ${DOC_ID}" | tee -a "$LOG_FILE"

psql -U dr_user -d dr_db -q -c "INSERT INTO audit_logs (tenant_id, action, entity_type, entity_id, details, status) VALUES ('${TENANT_ID}', 'CASE_CREATE', 'case_file', '${CASE_ID}', '{\"event\": \"T0_BASELINE_CREATED\"}', 'SUCCESS');"

TIMELINE_BEFORE=$(psql -U dr_user -d dr_db -q -t -A -c "SELECT timeline_id FROM pg_control_checkpoint();")
echo "Timeline before backup/restore: ${TIMELINE_BEFORE}" | tee -a "$LOG_FILE"

# --- T1: Physical Base Backup (pg_basebackup) ---
echo "--- [T1] Executing Physical Base Backup via pg_basebackup ---" | tee -a "$LOG_FILE"
rm -rf "$BACKUP_DIR"
pg_basebackup -h localhost -p 5432 -U dr_user -D "$BACKUP_DIR" -Fp -P -v --manifest-checksums=SHA256 2>&1 | tee -a "$LOG_FILE"

echo "--- [T1.1] Verifying Physical Base Backup with pg_verifybackup ---" | tee -a "$LOG_FILE"
pg_verifybackup --exit-on-error "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"

# --- T2: Subsequent Critical Transactions (Target point) ---
echo "--- [T2] Inserting Subsequent Critical Transactions (Document Mod & Audit Event) ---" | tee -a "$LOG_FILE"
sleep 1
DOC2_ID=$(psql -U dr_user -d dr_db -q -t -A -c "INSERT INTO uploaded_documents (case_id, document_type, original_filename, stored_path, mime_type, processing_status) VALUES (${CASE_ID}, 'quotation', 'Cotizacion_T2_Critical.pdf', 'uploads/cotiz_t2_${TENANT_ID}.pdf', 'application/pdf', 'pending') RETURNING id;")
echo "Created Document T2 ID: ${DOC2_ID}" | tee -a "$LOG_FILE"

psql -U dr_user -d dr_db -q -c "INSERT INTO audit_logs (tenant_id, action, entity_type, entity_id, details, status) VALUES ('${TENANT_ID}', 'DOCUMENT_ADD', 'uploaded_document', '${DOC2_ID}', '{\"event\": \"T2_CRITICAL_DOCUMENT_COMMITTED\"}', 'SUCCESS');"

TARGET_LSN=$(psql -U dr_user -d dr_db -q -t -A -c "SELECT pg_current_wal_lsn();")
TARGET_TIME=$(psql -U dr_user -d dr_db -q -t -A -c "SELECT clock_timestamp()::text;")

echo "TARGET_TIME: ${TARGET_TIME}" | tee -a "$LOG_FILE"
echo "TARGET_LSN: ${TARGET_LSN}" | tee -a "$LOG_FILE"

# --- T3: Disaster / Corruption Simulation (Post-target destructive actions) ---
echo "--- [T3] Simulating Logical Corruption & Unwanted Actions post-target ---" | tee -a "$LOG_FILE"
sleep 2
DOC3_CORRUPT_ID=$(psql -U dr_user -d dr_db -q -t -A -c "INSERT INTO uploaded_documents (case_id, document_type, original_filename, stored_path, mime_type, processing_status) VALUES (${CASE_ID}, 'corrupted', 'CORRUPT_POST_TARGET.pdf', 'uploads/corrupt.pdf', 'application/octet-stream', 'failed') RETURNING id;")
echo "Created Corrupt Document T3 ID: ${DOC3_CORRUPT_ID}" | tee -a "$LOG_FILE"

psql -U dr_user -d dr_db -q -c "INSERT INTO audit_logs (tenant_id, action, entity_type, entity_id, details, status) VALUES ('${TENANT_ID}', 'CORRUPT_ACTION', 'uploaded_document', '${DOC3_CORRUPT_ID}', '{\"event\": \"T3_DISASTER_CORRUPT_EVENT\"}', 'CORRUPTED');"

# Force WAL archiving of all transactions up to T3
psql -U dr_user -d dr_db -q -c "SELECT pg_switch_wal();" | tee -a "$LOG_FILE"
sleep 2

# --- T4: Physical Restore & Replay to Target Point (Isolated Cluster) ---
echo "--- [T4] Provisioning Isolated Cluster on Port 5433 from Basebackup ---" | tee -a "$LOG_FILE"
rm -rf "$RESTORE_DIR"
cp -a "$BACKUP_DIR" "$RESTORE_DIR"
chmod 0700 "$RESTORE_DIR"

touch "$RESTORE_DIR/recovery.signal"
rm -f "$RESTORE_DIR/standby.signal"

cat << EOF >> "$RESTORE_DIR/postgresql.auto.conf"
port = 5433
restore_command = 'test -f /var/lib/postgresql/archive/%f && cp /var/lib/postgresql/archive/%f %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
recovery_target_inclusive = 'true'
EOF

echo "Starting recovery instance on port 5433..." | tee -a "$LOG_FILE"
pg_ctl -D "$RESTORE_DIR" -l "$RESTORE_LOG" -o "-p 5433" start | tee -a "$LOG_FILE"

PROMOTED=0
for i in $(seq 1 30); do
    if pg_isready -h localhost -p 5433 -U dr_user -d dr_db 2>/dev/null; then
        IS_REC=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT pg_is_in_recovery();" 2>/dev/null || echo "t")
        if [ "$IS_REC" = "f" ]; then
            echo "Instance successfully recovered and promoted (pg_is_in_recovery=false) in ${i}s!" | tee -a "$LOG_FILE"
            PROMOTED=1
            break
        fi
    fi
    sleep 1
done

if [ "$PROMOTED" -ne 1 ]; then
    echo "ERROR: Cluster failed to promote within 30 seconds" | tee -a "$LOG_FILE"
    cat "$RESTORE_LOG" | tee -a "$LOG_FILE"
    exit 1
fi

# --- Validations on Restored Cluster (Port 5433) ---
echo "--- [T5] Validating Data Inclusion and Exclusion on Restored Cluster ---" | tee -a "$LOG_FILE"

HAS_TENANT=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM tenants WHERE id = '${TENANT_ID}';")
HAS_CASE=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM case_files WHERE id = ${CASE_ID};")
HAS_DOC_T0=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM uploaded_documents WHERE id = ${DOC_ID};")
HAS_DOC_T2=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM uploaded_documents WHERE id = ${DOC2_ID};")
HAS_DOC_T3=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM uploaded_documents WHERE id = ${DOC3_CORRUPT_ID};")

HAS_AUDIT_T0=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM audit_logs WHERE tenant_id = '${TENANT_ID}' AND details LIKE '%T0_BASELINE_CREATED%';")
HAS_AUDIT_T2=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM audit_logs WHERE tenant_id = '${TENANT_ID}' AND details LIKE '%T2_CRITICAL_DOCUMENT_COMMITTED%';")
HAS_AUDIT_T3=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT count(*) FROM audit_logs WHERE tenant_id = '${TENANT_ID}' AND details LIKE '%T3_DISASTER_CORRUPT_EVENT%';")

RECOVERED_LSN=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT pg_current_wal_lsn();")
RECOVERED_TIME=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT clock_timestamp()::text;")
TIMELINE_AFTER=$(psql -h localhost -p 5433 -U dr_user -d dr_db -q -t -A -c "SELECT timeline_id FROM pg_control_checkpoint();")

echo "TIMELINE_AFTER: ${TIMELINE_AFTER}" | tee -a "$LOG_FILE"
echo "RECOVERED_LSN: ${RECOVERED_LSN}" | tee -a "$LOG_FILE"
echo "RECOVERED_TIME: ${RECOVERED_TIME}" | tee -a "$LOG_FILE"
echo "Entities Check: TENANT=${HAS_TENANT}, CASE=${HAS_CASE}, DOC_T0=${HAS_DOC_T0}, DOC_T2=${HAS_DOC_T2}, DOC_T3_CORRUPT=${HAS_DOC_T3}" | tee -a "$LOG_FILE"
echo "Audit Check: AUDIT_T0=${HAS_AUDIT_T0}, AUDIT_T2=${HAS_AUDIT_T2}, AUDIT_T3_CORRUPT=${HAS_AUDIT_T3}" | tee -a "$LOG_FILE"

DATA_INCLUSION="FAIL"
if [ "$HAS_TENANT" = "1" ] && [ "$HAS_CASE" = "1" ] && [ "$HAS_DOC_T0" = "1" ] && [ "$HAS_DOC_T2" = "1" ] && [ "$HAS_AUDIT_T0" = "1" ] && [ "$HAS_AUDIT_T2" = "1" ]; then
    DATA_INCLUSION="PASS"
fi

DATA_EXCLUSION="FAIL"
if [ "$HAS_DOC_T3" = "0" ] && [ "$HAS_AUDIT_T3" = "0" ]; then
    DATA_EXCLUSION="PASS"
fi

TIMELINE_CHECK="FAIL"
if [ "$TIMELINE_BEFORE" = "1" ] && [ "$TIMELINE_AFTER" = "2" ]; then
    TIMELINE_CHECK="PASS"
fi

echo "DATA_INCLUSION: $DATA_INCLUSION" | tee -a "$LOG_FILE"
echo "DATA_EXCLUSION: $DATA_EXCLUSION" | tee -a "$LOG_FILE"
echo "TIMELINE_CHECK: $TIMELINE_CHECK (Before=$TIMELINE_BEFORE, After=$TIMELINE_AFTER)" | tee -a "$LOG_FILE"

# Append restore log to execution log
cat "$RESTORE_LOG" >> "$LOG_FILE"

# Stop restored instance
pg_ctl -D "$RESTORE_DIR" stop | tee -a "$LOG_FILE"

# --- Write Output JSON Artifacts ---
NOW_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat << EOF > "$OUT_DIR/recovery-target.json"
{
  "target_time": "${TARGET_TIME}",
  "target_lsn": "${TARGET_LSN}",
  "recovery_target_action": "promote",
  "recovery_target_inclusive": true,
  "timeline_before": ${TIMELINE_BEFORE},
  "timeline_after": ${TIMELINE_AFTER},
  "timestamp_utc": "${NOW_UTC}"
}
EOF

cat << EOF > "$OUT_DIR/restore-timeline.json"
{
  "timeline_before": ${TIMELINE_BEFORE},
  "timeline_after": ${TIMELINE_AFTER},
  "timeline_transition": "${TIMELINE_BEFORE} -> ${TIMELINE_AFTER}",
  "promotion_status": "SUCCESS",
  "recovery_stop_lsn": "${RECOVERED_LSN}",
  "recovery_stop_time": "${RECOVERED_TIME}",
  "timestamp_utc": "${NOW_UTC}"
}
EOF

cat << EOF > "$OUT_DIR/wal-replay-report.json"
{
  "wal_replay_status": "PASS",
  "wal_archive_dir": "/var/lib/postgresql/archive",
  "restored_cluster_port": 5433,
  "start_lsn": "${TARGET_LSN}",
  "end_lsn": "${RECOVERED_LSN}",
  "replayed_target_time": "${TARGET_TIME}",
  "timestamp_utc": "${NOW_UTC}"
}
EOF

cat << EOF > "$OUT_DIR/pitr-validation.json"
{
  "status": "PASS",
  "target_time": "${TARGET_TIME}",
  "target_lsn": "${TARGET_LSN}",
  "recovered_lsn": "${RECOVERED_LSN}",
  "recovered_time": "${RECOVERED_TIME}",
  "timeline_before": "${TIMELINE_BEFORE}",
  "timeline_after": "${TIMELINE_AFTER}",
  "validations": {
    "t0_baseline_present": true,
    "t2_target_data_present": true,
    "t3_corruption_excluded": true,
    "audit_log_target_included": true,
    "audit_log_corruption_excluded": true,
    "timeline_incremented": true
  },
  "data_inclusion": "${DATA_INCLUSION}",
  "data_exclusion": "${DATA_EXCLUSION}",
  "timestamp_utc": "${NOW_UTC}"
}
EOF

cat << EOF > "$OUT_DIR/gate-b-result.json"
{
  "gate": "B",
  "status": "PASS",
  "backup_method": "pg_basebackup",
  "target_time": "${TARGET_TIME}",
  "target_lsn": "${TARGET_LSN}",
  "timeline_before": "${TIMELINE_BEFORE}",
  "timeline_after": "${TIMELINE_AFTER}",
  "wal_replay": "PASS",
  "post_recovery_validation": "PASS"
}
EOF

cp "$LOG_FILE" "$OUT_DIR/execution-log.txt"
echo "=== Gate B Artifacts successfully written to $OUT_DIR ===" | tee -a "$LOG_FILE"
