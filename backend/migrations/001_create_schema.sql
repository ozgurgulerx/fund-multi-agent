-- IC Autopilot Database Schema
-- Migration 001: Create schema
-- This creates a NEW schema and does NOT touch any existing schemas like nport_funds

-- Create the ic_autopilot schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS ic_autopilot;

-- Grant usage on schema (adjust role as needed)
-- GRANT USAGE ON SCHEMA ic_autopilot TO your_app_role;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ic_autopilot TO your_app_role;

COMMENT ON SCHEMA ic_autopilot IS 'Investment Committee Autopilot - workflow runs and artifacts';
