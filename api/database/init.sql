-- =============================================================================
-- 作业票智能审查系统 - PostgreSQL 初始化脚本
-- 数据库: special_operations
-- 表: 7 张 (动火/受限空间/盲板抽堵作业票主表 + 关联表)
-- 规范: GB 30871-2022 危险化学品企业特殊作业安全规范
-- =============================================================================

-- 创建数据库
-- CREATE DATABASE special_operations ENCODING 'UTF8';

-- \c special_operations

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- 1. safety_check_items (安全检查项目字典表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS safety_check_items (
    id            int          NOT NULL,
    code          varchar(20)  NOT NULL,
    description   text         NOT NULL,
    applicable_to text[]       NOT NULL,
    PRIMARY KEY (id)
);

-- =============================================================================
-- 2. work_safety_checks (作业安全检查明细表, 关联任意 permit_id)
-- =============================================================================
CREATE TABLE IF NOT EXISTS work_safety_checks (
    permit_id         bigint       NOT NULL,
    permit_type       varchar(20)  NOT NULL,
    check_item_id     int          NOT NULL,
    is_confirmed      boolean      NOT NULL,
    confirmed_by      varchar(50),
    confirmed_at      timestamp,
    params            jsonb,
    evidence_url      varchar(255)
);

CREATE INDEX IF NOT EXISTS idx_wsc_permit ON work_safety_checks(permit_id, permit_type);
CREATE INDEX IF NOT EXISTS idx_wsc_item   ON work_safety_checks(check_item_id);

-- =============================================================================
-- 3. hot_work_permits (动火作业票主表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS hot_work_permits (
    id                              bigint        NOT NULL,
    permit_code                     varchar(50)   NOT NULL,
    work_id                         text          NOT NULL,
    apply_unit                      varchar(100),
    apply_time                      timestamp,
    work_content                    text,
    work_location                   text,
    work_level                      varchar(10),  -- 一级/二级/三级/特级
    work_method                     varchar(50),
    fire_worker_info                text,
    work_unit                       text,
    work_owner_name                 varchar(50),
    work_owner_phone                varchar(20),
    gas_analysis_time               timestamp,
    gas_analyst_name                varchar(50),
    gas_analysis_result             varchar(50),
    related_permit_ids              text,
    risk_identification             text,
    start_time                      timestamp,
    end_time                        timestamp,
    safety_disclosure_person        varchar(50),
    safety_disclosure_time          timestamp,
    accept_person                   varchar(50),
    accept_time                     timestamp,
    attendant                       varchar(50),
    approval_owner_opinion          varchar(200),
    approval_owner_sign             varchar(50),
    approval_owner_time             timestamp,
    approval_unit_opinion           varchar(200),
    approval_unit_sign              varchar(50),
    approval_unit_time              timestamp,
    approval_safety_opinion         varchar(200),
    approval_safety_sign            varchar(50),
    approval_safety_time            timestamp,
    approval_fire_leader_opinion    varchar(200),
    approval_fire_leader_sign       varchar(50),
    approval_fire_leader_time       timestamp,
    shift_leader_check_result       varchar(200),
    shift_leader_sign               varchar(50),
    shift_leader_time               timestamp,
    completion_acceptance_result    varchar(200),
    completion_acceptance_sign      varchar(50),
    completion_acceptance_time      timestamp,
    status                          varchar(20),  -- DRAFT/PENDING/APPROVED/IN_PROGRESS/COMPLETED/REJECTED/CANCELLED
    create_time                     timestamp,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_hwp_permit_code   ON hot_work_permits(permit_code);
CREATE INDEX IF NOT EXISTS idx_hwp_status        ON hot_work_permits(status);
CREATE INDEX IF NOT EXISTS idx_hwp_start_time    ON hot_work_permits(start_time);
CREATE INDEX IF NOT EXISTS idx_hwp_apply_unit    ON hot_work_permits(apply_unit);

-- =============================================================================
-- 4. hot_work_gas_analysis (动火气体分析表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS hot_work_gas_analysis (
    id                bigint        NOT NULL,
    permit_id         bigint,
    analysis_round    int,
    sample_time       timestamp,
    representative_gas varchar(100),
    analysis_result   varchar(100),
    analyst_name      varchar(50),
    create_time       timestamp,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_hwga_permit ON hot_work_gas_analysis(permit_id);

-- =============================================================================
-- 5. confined_space_permits (受限空间作业票主表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS confined_space_permits (
    id                       bigint        NOT NULL,
    permit_code              varchar(50)   NOT NULL,
    work_id                  text          NOT NULL,
    apply_unit               varchar(100),
    apply_time               timestamp,
    space_name               varchar(100),
    original_medium          varchar(100),
    work_content             text,
    work_unit                varchar(100),
    worker_names             text,
    supervisor_name          varchar(50),
    work_owner_name          varchar(50),
    related_permit_ids       text,
    risk_identification      text,
    last_gas_analysis_time   timestamp,
    last_oxygen_val          varchar(20),
    last_toxic_gas_val       varchar(50),
    last_flammable_gas_val   varchar(50),
    gas_analyst_name         varchar(50),
    start_time               timestamp,
    end_time                 timestamp,
    safety_disclosure_person varchar(50),
    accept_person            varchar(50),
    disclosure_time          timestamp,
    approval_owner_sign      varchar(50),
    approval_owner_time      timestamp,
    approval_unit_sign       varchar(50),
    approval_unit_time       timestamp,
    completion_acceptance_sign   varchar(50),
    completion_acceptance_time   timestamp,
    status                   varchar(20),
    create_time              timestamp,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_csp_permit_code   ON confined_space_permits(permit_code);
CREATE INDEX IF NOT EXISTS idx_csp_status        ON confined_space_permits(status);
CREATE INDEX IF NOT EXISTS idx_csp_start_time    ON confined_space_permits(start_time);

-- =============================================================================
-- 6. confined_space_gas_analysis (受限空间气体分析表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS confined_space_gas_analysis (
    id                    bigint        NOT NULL,
    permit_id             bigint,
    analysis_round        int,
    sample_time           timestamp,
    analysis_location     varchar(100),
    oxygen_content        varchar(20),
    toxic_gas_name        varchar(100),
    toxic_gas_criteria    varchar(50),
    toxic_gas_value       varchar(50),
    flammable_gas_name    varchar(100),
    flammable_gas_criteria varchar(50),
    flammable_gas_value   varchar(50),
    analyst_name          varchar(50),
    create_time           timestamp,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_csga_permit ON confined_space_gas_analysis(permit_id);

-- =============================================================================
-- 7. permit_blind_plate (盲板抽堵作业票主表)
-- =============================================================================
CREATE TABLE IF NOT EXISTS permit_blind_plate (
    id                       bigint        NOT NULL,
    ticket_code              varchar(50),
    apply_unit               varchar(100),
    work_unit                varchar(100),
    work_type                varchar(20),
    equipment_name           varchar(100),
    medium                   varchar(50),
    temperature              varchar(50),
    pressure                 varchar(50),
    blind_material           varchar(50),
    blind_spec               varchar(50),
    blind_code               varchar(50),
    start_time               timestamp,
    blind_location_desc      text,
    creator                  varchar(50),
    create_date              date,
    work_leader              varchar(50),
    worker                   varchar(50),
    guardian                 varchar(50),
    related_permits          text,
    risk_identification      text,
    safety_brief_person      varchar(50),
    safety_accept_person     varchar(50),
    leader_opinion           text,
    leader_sign              varchar(50),
    leader_sign_time         timestamp,
    unit_opinion             text,
    unit_sign                varchar(50),
    unit_sign_time           timestamp,
    completion_sign          varchar(50),
    completion_time          timestamp,
    created_at               timestamp,
    updated_at               timestamp,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_pbp_ticket_code ON permit_blind_plate(ticket_code);
CREATE INDEX IF NOT EXISTS idx_pbp_status       ON permit_blind_plate(work_type);

-- =============================================================================
-- 状态机 (status 字段取值)
-- =============================================================================
-- DRAFT          草稿
-- PENDING        待审批
-- APPROVED       已批准
-- IN_PROGRESS    进行中
-- COMPLETED      已完成
-- REJECTED       已拒绝
-- CANCELLED      已取消

-- =============================================================================
-- 验证
-- =============================================================================
-- 验证: 应能列出 7 张表
-- SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
