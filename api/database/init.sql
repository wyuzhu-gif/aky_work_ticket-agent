-- =============================================================================
-- 作业票智能审查系统 - MySQL 8.0 初始化脚本
-- 数据库: special_operations
-- 表: 7 张 (动火/受限空间/盲板抽堵作业票主表 + 关联表)
-- 规范: GB 30871-2022 危险化学品企业特殊作业安全规范
--
-- 替换: 原 PostgreSQL 版本 (text[] / bigserial / timestamp 等)
-- 主要差异:
--   * text[]              -> JSON
--   * bigserial           -> BIGINT AUTO_INCREMENT PRIMARY KEY
--   * timestamp (无时区) -> DATETIME
--   * CREATE EXTENSION    -> 删除 (MySQL 原生 UUID())
--   * CREATE INDEX IF NOT EXISTS -> 不支持, MySQL 8.0 用 IF NOT EXISTS 写在
--     CREATE INDEX 里, 但 v8.0.29+ 才支持; 安全做法是手动 DROP IF EXISTS
--     统一在部署脚本里加: DROP TABLE IF EXISTS ...
-- =============================================================================

-- 创建数据库 (执行前先确保有权限)
-- CREATE DATABASE special_operations DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE special_operations;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS hot_work_permits;
DROP TABLE IF EXISTS hot_work_gas_analysis;
DROP TABLE IF EXISTS confined_space_permits;
DROP TABLE IF EXISTS confined_space_gas_analysis;
DROP TABLE IF EXISTS permit_blind_plate;
DROP TABLE IF EXISTS work_safety_checks;
DROP TABLE IF EXISTS safety_check_items;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- 1. safety_check_items (安全检查项目字典表)
-- =============================================================================
CREATE TABLE safety_check_items (
    id            INT          NOT NULL AUTO_INCREMENT,
    code          VARCHAR(20)  NOT NULL,
    description   TEXT         NOT NULL,
    applicable_to JSON         NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='安全检查项目字典';

-- =============================================================================
-- 2. work_safety_checks (作业安全检查明细表, 关联任意 permit_id)
-- =============================================================================
CREATE TABLE work_safety_checks (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    permit_id     BIGINT       NOT NULL,
    permit_type   VARCHAR(20)  NOT NULL,
    check_item_id INT          NOT NULL,
    is_confirmed  TINYINT(1)   NOT NULL,
    confirmed_by  VARCHAR(50),
    confirmed_at  DATETIME,
    params        JSON,
    evidence_url  VARCHAR(255),
    PRIMARY KEY (id),
    KEY idx_wsc_permit (permit_id, permit_type),
    KEY idx_wsc_item (check_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='作业安全检查明细';

-- =============================================================================
-- 3. hot_work_permits (动火作业票主表)
-- =============================================================================
CREATE TABLE hot_work_permits (
    id                              BIGINT        NOT NULL AUTO_INCREMENT,
    permit_code                     VARCHAR(50)   NOT NULL,
    work_id                         TEXT          NOT NULL,
    apply_unit                      VARCHAR(100),
    apply_time                      DATETIME,
    work_content                    TEXT,
    work_location                   TEXT,
    work_level                      VARCHAR(10)  COMMENT '一级/二级/三级/特级',
    work_method                     VARCHAR(50),
    fire_worker_info                TEXT,
    work_unit                       TEXT,
    work_owner_name                 VARCHAR(50),
    work_owner_phone                VARCHAR(20),
    gas_analysis_time               DATETIME,
    gas_analyst_name                VARCHAR(50),
    gas_analysis_result             VARCHAR(50),
    related_permit_ids              TEXT,
    risk_identification             TEXT,
    start_time                      DATETIME,
    end_time                        DATETIME,
    safety_disclosure_person        VARCHAR(50),
    safety_disclosure_time          DATETIME,
    accept_person                   VARCHAR(50),
    accept_time                     DATETIME,
    attendant                       VARCHAR(50),
    approval_owner_opinion          VARCHAR(200),
    approval_owner_sign             VARCHAR(50),
    approval_owner_time             DATETIME,
    approval_unit_opinion           VARCHAR(200),
    approval_unit_sign              VARCHAR(50),
    approval_unit_time              DATETIME,
    approval_safety_opinion         VARCHAR(200),
    approval_safety_sign            VARCHAR(50),
    approval_safety_time            DATETIME,
    approval_fire_leader_opinion    VARCHAR(200),
    approval_fire_leader_sign       VARCHAR(50),
    approval_fire_leader_time       DATETIME,
    shift_leader_check_result       VARCHAR(200),
    shift_leader_sign               VARCHAR(50),
    shift_leader_time               DATETIME,
    completion_acceptance_result    VARCHAR(200),
    completion_acceptance_sign      VARCHAR(50),
    completion_acceptance_time      DATETIME,
    status                          VARCHAR(20)  COMMENT 'DRAFT/PENDING/APPROVED/IN_PROGRESS/COMPLETED/REJECTED/CANCELLED',
    create_time                     DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hwp_permit_code (permit_code),
    KEY idx_hwp_status (status),
    KEY idx_hwp_start_time (start_time),
    KEY idx_hwp_apply_unit (apply_unit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='动火作业票主表';

-- =============================================================================
-- 4. hot_work_gas_analysis (动火气体分析表)
-- =============================================================================
CREATE TABLE hot_work_gas_analysis (
    id                  BIGINT        NOT NULL AUTO_INCREMENT,
    permit_id           BIGINT,
    analysis_round      INT,
    sample_time         DATETIME,
    representative_gas  VARCHAR(100),
    analysis_result     VARCHAR(100),
    analyst_name        VARCHAR(50),
    create_time         DATETIME      DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hwga_permit (permit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='动火气体分析';

-- =============================================================================
-- 5. confined_space_permits (受限空间作业票主表)
-- =============================================================================
CREATE TABLE confined_space_permits (
    id                       BIGINT        NOT NULL AUTO_INCREMENT,
    permit_code              VARCHAR(50)   NOT NULL,
    work_id                  TEXT          NOT NULL,
    apply_unit               VARCHAR(100),
    apply_time               DATETIME,
    space_name               VARCHAR(100),
    original_medium          VARCHAR(100),
    work_content             TEXT,
    work_unit                VARCHAR(100),
    worker_names             TEXT,
    supervisor_name          VARCHAR(50),
    work_owner_name          VARCHAR(50),
    related_permit_ids       TEXT,
    risk_identification      TEXT,
    last_gas_analysis_time   DATETIME,
    last_oxygen_val          VARCHAR(20),
    last_toxic_gas_val       VARCHAR(50),
    last_flammable_gas_val   VARCHAR(50),
    gas_analyst_name         VARCHAR(50),
    start_time               DATETIME,
    end_time                 DATETIME,
    safety_disclosure_person VARCHAR(50),
    accept_person            VARCHAR(50),
    disclosure_time          DATETIME,
    approval_owner_sign      VARCHAR(50),
    approval_owner_time      DATETIME,
    approval_unit_sign       VARCHAR(50),
    approval_unit_time       DATETIME,
    completion_acceptance_sign   VARCHAR(50),
    completion_acceptance_time   DATETIME,
    status                   VARCHAR(20),
    create_time              DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_csp_permit_code (permit_code),
    KEY idx_csp_status (status),
    KEY idx_csp_start_time (start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='受限空间作业票主表';

-- =============================================================================
-- 6. confined_space_gas_analysis (受限空间气体分析表)
-- =============================================================================
CREATE TABLE confined_space_gas_analysis (
    id                    BIGINT        NOT NULL AUTO_INCREMENT,
    permit_id             BIGINT,
    analysis_round        INT,
    sample_time           DATETIME,
    analysis_location     VARCHAR(100),
    oxygen_content        VARCHAR(20),
    toxic_gas_name        VARCHAR(100),
    toxic_gas_criteria    VARCHAR(50),
    toxic_gas_value       VARCHAR(50),
    flammable_gas_name    VARCHAR(100),
    flammable_gas_criteria VARCHAR(50),
    flammable_gas_value   VARCHAR(50),
    analyst_name          VARCHAR(50),
    create_time           DATETIME      DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_csga_permit (permit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='受限空间气体分析';

-- =============================================================================
-- 7. permit_blind_plate (盲板抽堵作业票主表)
-- =============================================================================
CREATE TABLE permit_blind_plate (
    id                       BIGINT        NOT NULL AUTO_INCREMENT,
    ticket_code              VARCHAR(50),
    apply_unit               VARCHAR(100),
    work_unit                VARCHAR(100),
    work_type                VARCHAR(20),
    equipment_name           VARCHAR(100),
    medium                   VARCHAR(50),
    temperature              VARCHAR(50),
    pressure                 VARCHAR(50),
    blind_material           VARCHAR(50),
    blind_spec               VARCHAR(50),
    blind_code               VARCHAR(50),
    start_time               DATETIME,
    blind_location_desc      TEXT,
    creator                  VARCHAR(50),
    create_date              DATE,
    work_leader              VARCHAR(50),
    worker                   VARCHAR(50),
    guardian                 VARCHAR(50),
    related_permits          TEXT,
    risk_identification      TEXT,
    safety_brief_person      VARCHAR(50),
    safety_accept_person     VARCHAR(50),
    leader_opinion           TEXT,
    leader_sign              VARCHAR(50),
    leader_sign_time         DATETIME,
    unit_opinion             TEXT,
    unit_sign                VARCHAR(50),
    unit_sign_time           DATETIME,
    completion_sign          VARCHAR(50),
    completion_time          DATETIME,
    created_at               DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pbp_ticket_code (ticket_code),
    KEY idx_pbp_work_type (work_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='盲板抽堵作业票主表';

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
-- 验证: 应能列出 7 张表
-- =============================================================================
-- SELECT table_name, table_comment
-- FROM information_schema.tables
-- WHERE table_schema = DATABASE()
-- ORDER BY table_name;