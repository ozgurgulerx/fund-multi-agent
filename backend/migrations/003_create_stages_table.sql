-- IC Autopilot Database Schema
-- Migration 003: Create stages table
-- Stage-level checkpoints for each workflow run

CREATE TABLE IF NOT EXISTS ic_autopilot.stages (
    -- Composite primary key
    run_id VARCHAR(50) NOT NULL REFERENCES ic_autopilot.runs(run_id) ON DELETE CASCADE,
    stage_id VARCHAR(50) NOT NULL,

    -- Stage metadata
    stage_name VARCHAR(100),
    stage_order INTEGER NOT NULL,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'repaired')),

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    -- Progress
    progress_pct REAL DEFAULT 0 CHECK (progress_pct >= 0 AND progress_pct <= 100),

    -- Artifacts produced by this stage
    artifacts TEXT[],

    -- Error handling
    error_message TEXT,
    repair_attempts INTEGER DEFAULT 0,

    PRIMARY KEY (run_id, stage_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_stages_run ON ic_autopilot.stages(run_id);
CREATE INDEX IF NOT EXISTS idx_stages_status ON ic_autopilot.stages(status);

-- Comments
COMMENT ON TABLE ic_autopilot.stages IS 'Stage-level checkpoints for IC workflow runs';
COMMENT ON COLUMN ic_autopilot.stages.stage_order IS 'Execution order (1-10)';
COMMENT ON COLUMN ic_autopilot.stages.artifacts IS 'Array of artifact IDs produced by this stage';
COMMENT ON COLUMN ic_autopilot.stages.repair_attempts IS 'Number of repair attempts made for this stage';
