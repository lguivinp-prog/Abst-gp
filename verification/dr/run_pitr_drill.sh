#!/bin/sh
set -e

DRILL_DIR="/tmp/pitr_drill"
BACKUP_DIR="${DRILL_DIR}/basebackup"
RESTORE_DIR="${DRILL_DIR}/restored_cluster"
LOG_FILE="${DRILL_DIR}/pitr_drill.log"
RESTORE_LOG="${DRILL_DIR}/restored_cluster.log"

# Cleanup previous drill runs
pg_ctl -D "$RESTORE_DIR" stop 2>/dev/null || true
pkill -f "postgres.*5433" 2>/dev/null || true
rm -rf "$DRILL_DIR"
mkdir -p "$DRILL_DIR" "$BACKUP_DIR" "$RESTORE_DIR"

echo "=== PITR END-TO-END DRILL STARTING ===" > "$LOG_FILE"
date -u +"%Y-%m-%dT%H:%M:%SZ" >> "$LOG_FILE"

# STEP 0: Prepare Schema & Insert T0 Baseline Data
echo "--- STEP 0: Inserting T0 Baseline Data ---" | tee -a "$LOG_FILE"
psql -U dr_user -d dr_db -c "
DROP TABLE IF EXISTS dr_pitr_records CASCADE;
CREATE TABLE dr_pitr_records (
    id SERIAL PRIMARY KEY,
    stage VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    inserted_at TIMESTAMPTZ DEFAULT clock_timestamp()
);
INSERT INTO dr_pitr_records (stage, description) VALUES ('T0_BASELINE', 'Baseline state before physical base backup');
" | tee -a "$LOG_FILE"

# STEP 1: Execute Physical Base Backup (pg_basebackup)
echo "--- STEP 1: Running Physical Base Backup (pg_basebackup) ---" | tee -a "$LOG_FILE"
rm -rf "$BACKUP_DIR"
pg_basebackup -h localhost -p 5432 -U dr_user -D "$BACKUP_DIR" -Fp -P -v --manifest-checksums=SHA256 2>&1 | tee -a "$LOG_FILE"

echo "--- STEP 1.1: Verifying Base Backup with pg_verifybackup ---" | tee -a "$LOG_FILE"
pg_verifybackup --exit-on-error "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"

# STEP 2: Commit Target Critical Data & Record Recovery Target (T2)
echo "--- STEP 2: Inserting T2 Target Data & Capturing Recovery Target ---" | tee -a "$LOG_FILE"
sleep 1
psql -U dr_user -d dr_db -c "
INSERT INTO dr_pitr_records (stage, description) VALUES ('T2_TARGET_DATA', 'Critical production transaction committed prior to disaster');
" | tee -a "$LOG_FILE"

# Capture exact target timestamp and target LSN immediately after T2 commit
TARGET_LSN=$(psql -U dr_user -d dr_db -t -A -c "SELECT pg_current_wal_lsn();")
TARGET_TIME=$(psql -U dr_user -d dr_db -t -A -c "SELECT clock_timestamp()::text;")

echo "TARGET_TIME (Point-in-Time target): $TARGET_TIME" | tee -a "$LOG_FILE"
echo "TARGET_LSN (Point-in-Time target LSN): $TARGET_LSN" | tee -a "$LOG_FILE"

# STEP 3: Disaster / Data Corruption Simulation (T3)
echo "--- STEP 3: Simulating Disaster / Destructive Action at T3 ---" | tee -a "$LOG_FILE"
sleep 2
psql -U dr_user -d dr_db -c "
INSERT INTO dr_pitr_records (stage, description) VALUES ('T3_CORRUPTION', 'Destructive corruption event after T2 target');
" | tee -a "$LOG_FILE"

# Force WAL switch and archive segment
echo "--- STEP 3.1: Flushing WAL to Archive ---" | tee -a "$LOG_FILE"
SWITCH_RESULT=$(psql -U dr_user -d dr_db -t -A -c "SELECT pg_switch_wal();")
echo "Flushed WAL: $SWITCH_RESULT" | tee -a "$LOG_FILE"
sleep 2

# STEP 4: Provision Restored Cluster from Physical Base Backup
echo "--- STEP 4: Restoring Physical Base Backup to New Isolated Cluster ---" | tee -a "$LOG_FILE"
rm -rf "$RESTORE_DIR"
cp -a "$BACKUP_DIR" "$RESTORE_DIR"
chmod 0700 "$RESTORE_DIR"

# STEP 5: Configure PITR (recovery.signal, restore_command, recovery_target_time, recovery_target_action)
echo "--- STEP 5: Configuring PITR Parameters in Restored Cluster ---" | tee -a "$LOG_FILE"
touch "$RESTORE_DIR/recovery.signal"
rm -f "$RESTORE_DIR/standby.signal"

cat << EOF >> "$RESTORE_DIR/postgresql.auto.conf"
port = 5433
restore_command = 'test -f /var/lib/postgresql/archive/%f && cp /var/lib/postgresql/archive/%f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
recovery_target_inclusive = 'true'
EOF

echo "postgresql.auto.conf configured with target time: $TARGET_TIME" | tee -a "$LOG_FILE"

# STEP 6: Start Restored PostgreSQL Cluster on Port 5433
echo "--- STEP 6: Starting Isolated Restored PostgreSQL Instance on Port 5433 ---" | tee -a "$LOG_FILE"
pg_ctl -D "$RESTORE_DIR" -l "$RESTORE_LOG" -o "-p 5433" start | tee -a "$LOG_FILE"

# Wait for recovery to complete and promote
echo "Waiting for recovery and promotion..." | tee -a "$LOG_FILE"
PROMOTED=0
for i in $(seq 1 30); do
    if pg_isready -h localhost -p 5433 -U dr_user -d dr_db 2>/dev/null; then
        IS_RECOVERY=$(psql -h localhost -p 5433 -U dr_user -d dr_db -t -A -c "SELECT pg_is_in_recovery();" 2>/dev/null || echo "error")
        if [ "$IS_RECOVERY" = "f" ]; then
            echo "Restored instance is UP, PROMOTED and accepting connections (pg_is_in_recovery = false)!" | tee -a "$LOG_FILE"
            PROMOTED=1
            break
        fi
    fi
    sleep 1
done

if [ "$PROMOTED" -ne 1 ]; then
    echo "ERROR: Restored instance failed to promote in 30 seconds!" | tee -a "$LOG_FILE"
    cat "$RESTORE_LOG" | tee -a "$LOG_FILE"
    exit 1
fi

# STEP 7: Validate Data Integrity on Restored Instance (Port 5433)
echo "--- STEP 7: Validating Data and Timeline Integrity on Restored Cluster ---" | tee -a "$LOG_FILE"
psql -h localhost -p 5433 -U dr_user -d dr_db -c "SELECT id, stage, description, inserted_at FROM dr_pitr_records ORDER BY id ASC;" | tee -a "$LOG_FILE"

HAS_T0=$(psql -h localhost -p 5433 -U dr_user -d dr_db -t -A -c "SELECT count(*) FROM dr_pitr_records WHERE stage = 'T0_BASELINE';")
HAS_T2=$(psql -h localhost -p 5433 -U dr_user -d dr_db -t -A -c "SELECT count(*) FROM dr_pitr_records WHERE stage = 'T2_TARGET_DATA';")
HAS_T3=$(psql -h localhost -p 5433 -U dr_user -d dr_db -t -A -c "SELECT count(*) FROM dr_pitr_records WHERE stage = 'T3_CORRUPTION';")

echo "Validation Summary: HAS_T0=$HAS_T0 (expected 1), HAS_T2=$HAS_T2 (expected 1), HAS_T3=$HAS_T3 (expected 0)" | tee -a "$LOG_FILE"

if [ "$HAS_T0" -ne 1 ] || [ "$HAS_T2" -ne 1 ] || [ "$HAS_T3" -ne 0 ]; then
    echo "ERROR: Data validation failed! T0=$HAS_T0, T2=$HAS_T2, T3=$HAS_T3" | tee -a "$LOG_FILE"
    exit 1
fi

# STEP 8: Inspect Timeline & Control Data
echo "--- STEP 8: Inspecting Timeline & Control Data ---" | tee -a "$LOG_FILE"
CONTROL_DATA=$(pg_controldata "$RESTORE_DIR")
echo "$CONTROL_DATA" >> "$LOG_FILE"

TIMELINE_ID=$(echo "$CONTROL_DATA" | grep "Latest checkpoint's TimeLineID:" | awk '{print $NF}')
DB_STATE=$(echo "$CONTROL_DATA" | grep "Database cluster state:" | cut -d: -f2 | xargs)

echo "Restored Timeline ID: $TIMELINE_ID" | tee -a "$LOG_FILE"
echo "Restored DB State: $DB_STATE" | tee -a "$LOG_FILE"

# Output WAL Replay log lines
echo "--- RESTORE LOG ENTRIES (WAL REPLAY) ---" | tee -a "$LOG_FILE"
cat "$RESTORE_LOG" | tee -a "$LOG_FILE"

# STEP 9: Stop Isolated Restored Cluster
echo "--- STEP 9: Stopping Restored Instance ---" | tee -a "$LOG_FILE"
pg_ctl -D "$RESTORE_DIR" stop | tee -a "$LOG_FILE"

echo "=== PITR DRILL COMPLETED SUCCESSFULLY ===" | tee -a "$LOG_FILE"
