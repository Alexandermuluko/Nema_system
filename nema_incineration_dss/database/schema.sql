-- PostgreSQL reference schema for the NEMA DSS application.
-- Django migrations are the authoritative schema mechanism.
-- Run this only when you understand that Django will subsequently manage the tables.
CREATE TABLE IF NOT EXISTS core_userprofile (
    id BIGSERIAL PRIMARY KEY,
    role VARCHAR(20) NOT NULL DEFAULT 'OFFICER',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS core_dataset (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    file VARCHAR(100) NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    column_count INTEGER NOT NULL DEFAULT 0 CHECK (column_count >= 0),
    columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    preprocessing_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    preview JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_by_id INTEGER NULL
);

CREATE TABLE IF NOT EXISTS core_mlmodel (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    algorithm VARCHAR(40) NOT NULL,
    target_column VARCHAR(255) NOT NULL,
    feature_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_file VARCHAR(100) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id INTEGER NULL
);

CREATE TABLE IF NOT EXISTS core_prediction (
    id BIGSERIAL PRIMARY KEY,
    target_column VARCHAR(255) NOT NULL,
    predicted_value DOUBLE PRECISION NULL,
    actual_value DOUBLE PRECISION NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(30) NOT NULL DEFAULT 'Completed',
    dataset_id BIGINT NOT NULL,
    model_id BIGINT NULL,
    created_by_id INTEGER NULL
);

CREATE TABLE IF NOT EXISTS core_report (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    report_type VARCHAR(30) NOT NULL DEFAULT 'SUMMARY',
    date_from DATE NULL,
    date_to DATE NULL,
    content JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dataset_id BIGINT NULL,
    model_id BIGINT NULL,
    generated_by_id INTEGER NULL
);
