-- IC Autopilot Database Schema
-- Migration 002: Create runs table
-- Primary table for IC workflow run metadata

CREATE TABLE IF NOT EXISTS ic_autopilot.runs (
    -- Primary identifier
    run_id VARCHAR(50) PRIMARY KEY,

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),

    -- Run configuration
    mandate_id VARCHAR(100) NOT NULL,
    seed INTEGER DEFAULT 42,
    config JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    -- Progress tracking
    current_stage VARCHAR(50),
    stages_completed INTEGER DEFAULT 0,
    total_stages INTEGER DEFAULT 10,
    progress_pct REAL DEFAULT 0 CHECK (progress_pct >= 0 AND progress_pct <= 100),

    -- Selection result
    selected_candidate VARCHAR(10) CHECK (selected_candidate IN ('A', 'B', 'C')),

    -- Error handling
    error_message TEXT,
    error_stage VARCHAR(50),

    -- Metrics
    event_count INTEGER DEFAULT 0,
    artifact_count INTEGER DEFAULT 0,

    -- Audit
    requested_by VARCHAR(100),
    tags TEXT[],
    metadata JSONB DEFAULT '{}'
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_status ON ic_autopilot.runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON ic_autopilot.runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_mandate ON ic_autopilot.runs(mandate_id);
CREATE INDEX IF NOT EXISTS idx_runs_tags ON ic_autopilot.runs USING GIN(tags);

-- Comments
COMMENT ON TABLE ic_autopilot.runs IS 'IC workflow run metadata and status tracking';
COMMENT ON COLUMN ic_autopilot.runs.run_id IS 'Unique identifier for the workflow run';
COMMENT ON COLUMN ic_autopilot.runs.mandate_id IS 'Investment mandate template ID';
COMMENT ON COLUMN ic_autopilot.runs.seed IS 'Random seed for reproducibility';
COMMENT ON COLUMN ic_autopilot.runs.config IS 'Run-specific configuration overrides';
COMMENT ON COLUMN ic_autopilot.runs.selected_candidate IS 'Final selected portfolio candidate (A/B/C)';
