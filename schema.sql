-- Full SQL schema for the LinkedIn Auto-Poster backend.
-- Run this in the Supabase SQL Editor (or via psql) to create all tables.
-- Designed to match models.py exactly.

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    linkedin_id VARCHAR(255) UNIQUE,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    password_hash VARCHAR(255),
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    headline VARCHAR(255),
    avatar_url VARCHAR(1000),
    linkedin_url VARCHAR(1000),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITHOUT TIME ZONE,
    openai_api_key TEXT,
    linkedin_client_id TEXT,
    linkedin_client_secret TEXT,
    linkedin_org_urn VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_linkedin_id ON users(linkedin_id);

-- Settings table (one row per user)
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    company_name VARCHAR(255),
    company_context TEXT,
    default_model VARCHAR(50) DEFAULT 'gpt-4o',
    default_target VARCHAR(50) DEFAULT 'profile',
    default_inspiration VARCHAR(50) DEFAULT 'manual',
    post_time VARCHAR(10) DEFAULT '09:00',
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    email_notifications INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_settings_user_id ON settings(user_id);

-- Inspiration posts table
CREATE TABLE IF NOT EXISTS inspiration_posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source VARCHAR(50) DEFAULT 'manual',
    title VARCHAR(500),
    content TEXT NOT NULL,
    url VARCHAR(1000),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_inspiration_user_id_created ON inspiration_posts(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_inspiration_user_id_source ON inspiration_posts(user_id, source);

-- Drafts table
CREATE TABLE IF NOT EXISTS drafts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    model VARCHAR(50),
    target VARCHAR(50),
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    published_at TIMESTAMP WITHOUT TIME ZONE,
    linkedin_post_id VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS ix_drafts_user_id_created ON drafts(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_drafts_user_id_status ON drafts(user_id, status);

-- Row Level Security (RLS) policies for Supabase.
-- Enable RLS on all user-owned tables so users can only read/write their own data.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspiration_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE drafts ENABLE ROW LEVEL SECURITY;

-- Users can read/update only their own user row.
CREATE POLICY user_self_select ON users
    FOR SELECT USING (auth.uid()::text = linkedin_id OR auth.uid()::text = email);

CREATE POLICY user_self_update ON users
    FOR UPDATE USING (auth.uid()::text = linkedin_id OR auth.uid()::text = email);

-- Settings, inspiration, drafts: scoped by user_id.
CREATE POLICY settings_user_select ON settings FOR SELECT USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY settings_user_insert ON settings FOR INSERT WITH CHECK (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY settings_user_update ON settings FOR UPDATE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY settings_user_delete ON settings FOR DELETE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));

CREATE POLICY inspiration_user_select ON inspiration_posts FOR SELECT USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY inspiration_user_insert ON inspiration_posts FOR INSERT WITH CHECK (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY inspiration_user_update ON inspiration_posts FOR UPDATE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY inspiration_user_delete ON inspiration_posts FOR DELETE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));

CREATE POLICY drafts_user_select ON drafts FOR SELECT USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY drafts_user_insert ON drafts FOR INSERT WITH CHECK (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY drafts_user_update ON drafts FOR UPDATE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
CREATE POLICY drafts_user_delete ON drafts FOR DELETE USING (user_id IN (SELECT id FROM users WHERE auth.uid()::text = email));
