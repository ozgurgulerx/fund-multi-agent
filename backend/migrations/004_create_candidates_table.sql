-- IC Autopilot Database Schema
-- Migration 004: Create candidates table
-- Tracks the three portfolio candidates (A, B, C) and their verification status

CREATE TABLE IF NOT EXISTS ic_autopilot.candidates (
    -- Composite primary key
    run_id VARCHAR(50) NOT NULL REFERENCES ic_autopilot.runs(run_id) ON DELETE CASCADE,
    candidate_id VARCHAR(10) NOT NULL CHECK (candidate_id IN ('A', 'B', 'C')),

    -- Verification status
    compliance_status VARCHAR(20) DEFAULT 'pending'
        CHECK (compliance_status IN ('pending', 'running', 'passed', 'failed', 'repaired')),
    redteam_status VARCHAR(20) DEFAULT 'pending'
        CHECK (redteam_status IN ('pending', 'running', 'passed', 'failed')),

    -- Verification results
    compliance_passed BOOLEAN,
    redteam_passed BOOLEAN,

    -- Repair tracking
    repair_attempts INTEGER DEFAULT 0,

    -- Selection
    is_selected BOOLEAN DEFAULT FALSE,
    rejection_reason TEXT,

    -- Scores (optimization score, compliance score, risk score, etc.)
    scores JSONB DEFAULT '{}',

    PRIMARY KEY (run_id, candidate_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_candidates_run ON ic_autopilot.candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_candidates_selected ON ic_autopilot.candidates(is_selected) WHERE is_selected = TRUE;

-- Comments
COMMENT ON TABLE ic_autopilot.candidates IS 'Portfolio candidate tracking for A/B/C generation and verification';
COMMENT ON COLUMN ic_autopilot.candidates.compliance_status IS 'Status of compliance rule verification';
COMMENT ON COLUMN ic_autopilot.candidates.redteam_status IS 'Status of adversarial stress testing';
COMMENT ON COLUMN ic_autopilot.candidates.scores IS 'JSON object with optimization_score, compliance_score, risk_score, etc.';
