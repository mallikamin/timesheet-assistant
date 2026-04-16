-- Supabase Schema for Task Management (Phase 2)
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/vsbhiuozqyxxvqwxwyuh/sql

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  project TEXT NOT NULL,
  assignees TEXT[] DEFAULT '{}',  -- Array of assignee names: {"Tariq Munir", "Lauren Pallotta"}
  status TEXT DEFAULT 'To Do',
  priority TEXT DEFAULT 'Medium',
  due_date DATE DEFAULT CURRENT_DATE,
  budget FLOAT DEFAULT 0.0,
  hours_logged FLOAT DEFAULT 0.0,
  description TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  attachments JSONB DEFAULT '[]',  -- [{name: "file.pdf", url: "https://..."}, ...]
  subtasks JSONB DEFAULT '[]',  -- [{title: "Subtask 1", done: false}, ...]
  parent_task_id TEXT,  -- For future subtask hierarchy (optional)
  created_by TEXT DEFAULT 'System',
  created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_assignees ON tasks USING GIN(assignees);  -- For array contains queries

-- Sample query to verify (uncomment after creating table):
-- SELECT id, title, assignees, status, due_date FROM tasks ORDER BY created_at DESC LIMIT 5;

-- To drop and recreate (use with caution):
-- DROP TABLE IF EXISTS tasks CASCADE;
