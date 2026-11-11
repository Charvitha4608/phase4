-- Wife Carrying World Championships: schema for MySQL 8.4
-- Baseline: Team 28's Phase 3 schema (26 relations). Every addition or change
-- is marked "DC-n" and explained in the Design Changes section of README.md.
-- Run with: mysql -u <user> -p < schema.sql

DROP DATABASE IF EXISTS wife_carrying_db;
CREATE DATABASE wife_carrying_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE wife_carrying_db;

-- ---------------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------------
CREATE TABLE COUNTRY (
    country_code CHAR(3)     NOT NULL,
    name         VARCHAR(80) NOT NULL,
    continent    ENUM('Africa','Asia','Australia','Europe','North America','South America') NOT NULL,
    PRIMARY KEY (country_code),
    CONSTRAINT uq_country_name UNIQUE (name)
);

CREATE TABLE VENUE (
    venue_id       INT AUTO_INCREMENT,
    name           VARCHAR(120) NOT NULL,
    street         VARCHAR(120) NOT NULL,
    city           VARCHAR(80)  NOT NULL,
    postal_code    VARCHAR(12)  NULL,
    country_code   CHAR(3)      NOT NULL,
    capacity       INT          NULL,
    track_length_m DECIMAL(6,2) NULL,
    PRIMARY KEY (venue_id),
    CONSTRAINT chk_venue_capacity CHECK (capacity IS NULL OR capacity > 0),
    CONSTRAINT chk_venue_track    CHECK (track_length_m IS NULL OR track_length_m > 0)
);

CREATE TABLE ORGANISER (
    organiser_id INT AUTO_INCREMENT,
    name         VARCHAR(120) NOT NULL,
    legal_form   VARCHAR(40)  NOT NULL,
    founded_year SMALLINT     NULL,
    PRIMARY KEY (organiser_id)
);

CREATE TABLE RACE_CATEGORY (
    cat_code              VARCHAR(10)  NOT NULL,
    name                  VARCHAR(60)  NOT NULL,
    distance_m            DECIMAL(6,2) NOT NULL,
    min_weight_carried_kg DECIMAL(5,2) NOT NULL,
    has_water_obstacle    BOOLEAN      NOT NULL,
    has_dry_obstacles     BOOLEAN      NOT NULL,
    max_team_size         TINYINT      NOT NULL,
    min_age_carrier       TINYINT      NOT NULL,
    min_age_carried       TINYINT      NOT NULL,
    PRIMARY KEY (cat_code),
    CONSTRAINT uq_category_name UNIQUE (name),
    CONSTRAINT chk_cat_distance CHECK (distance_m > 0),
    CONSTRAINT chk_cat_weight   CHECK (min_weight_carried_kg > 0),
    CONSTRAINT chk_cat_team     CHECK (max_team_size >= 2),
    CONSTRAINT chk_cat_ages     CHECK (min_age_carrier >= 18 AND min_age_carried >= 17)
);

-- ---------------------------------------------------------------------------
-- People
-- ---------------------------------------------------------------------------
CREATE TABLE PERSON (
    person_id        INT AUTO_INCREMENT,
    first_name       VARCHAR(60)  NOT NULL,
    last_name        VARCHAR(60)  NULL,                   -- DC-9
    email            VARCHAR(120) NULL,                   -- DC-9 (UNIQUE still applies)
    gender           ENUM('F','M','X') NULL,
    date_of_birth    DATE         NULL,                   -- DC-9
    role_type        ENUM('COMPETITOR','OFFICIAL') NULL,
    nationality_code CHAR(3)      NULL,                   -- DC-9
    PRIMARY KEY (person_id),
    CONSTRAINT uq_person_email UNIQUE (email),
    CONSTRAINT fk_person_nationality FOREIGN KEY (nationality_code)
        REFERENCES COUNTRY(country_code) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_person_last_name ON PERSON (last_name);

CREATE TABLE PERSON_PHONE (
    person_id    INT         NOT NULL,
    phone_number VARCHAR(30) NOT NULL,
    PRIMARY KEY (person_id, phone_number),
    CONSTRAINT fk_phone_person FOREIGN KEY (person_id)
        REFERENCES PERSON(person_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE COMPETITOR (                                 -- DC-2: bib_number and role moved out
    person_id         INT          NOT NULL,
    weight_kg         DECIMAL(5,2) NULL,                  -- DC-9
    career_start_year SMALLINT     NULL,
    PRIMARY KEY (person_id),
    CONSTRAINT chk_competitor_weight CHECK (weight_kg IS NULL OR weight_kg > 0),
    CONSTRAINT fk_competitor_person FOREIGN KEY (person_id)
        REFERENCES PERSON(person_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE OFFICIAL (
    person_id           INT NOT NULL,
    certification_level TINYINT NOT NULL,
    official_role       ENUM('JURY','TIMEKEEPER','EQUIPMENT_INSPECTOR','STARTER') NOT NULL,
    PRIMARY KEY (person_id),
    CONSTRAINT chk_official_level CHECK (certification_level BETWEEN 1 AND 3),
    CONSTRAINT fk_official_person FOREIGN KEY (person_id)
        REFERENCES PERSON(person_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------------
-- Teams and pairs
-- ---------------------------------------------------------------------------
CREATE TABLE TEAM (
    team_id           INT AUTO_INCREMENT,
    name              VARCHAR(120) NOT NULL,
    founded_year      SMALLINT     NULL,
    home_country_code CHAR(3)      NULL,
    parent_team_id    INT          NULL,
    PRIMARY KEY (team_id),
    CONSTRAINT uq_team_name UNIQUE (name),
    CONSTRAINT fk_team_country FOREIGN KEY (home_country_code)
        REFERENCES COUNTRY(country_code) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_team_parent FOREIGN KEY (parent_team_id)
        REFERENCES TEAM(team_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE COMPETES_FOR (
    competitor_id INT NOT NULL,
    team_id       INT NOT NULL,
    PRIMARY KEY (competitor_id, team_id),
    CONSTRAINT fk_cf_competitor FOREIGN KEY (competitor_id)
        REFERENCES COMPETITOR(person_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cf_team FOREIGN KEY (team_id)
        REFERENCES TEAM(team_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- RESTRICT on these keys: a pair is part of the historical record, and MySQL
-- does not allow a CHECK on a column whose foreign key has a CASCADE action.
CREATE TABLE PAIR (
    carrier_id  INT      NOT NULL,
    carried_id  INT      NOT NULL,
    formed_year SMALLINT NULL,
    is_active   BOOLEAN  NOT NULL DEFAULT TRUE,
    PRIMARY KEY (carrier_id, carried_id),
    CONSTRAINT chk_pair_distinct CHECK (carrier_id <> carried_id),            -- C9
    CONSTRAINT fk_pair_carrier FOREIGN KEY (carrier_id)
        REFERENCES COMPETITOR(person_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_pair_carried FOREIGN KEY (carried_id)
        REFERENCES COMPETITOR(person_id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX idx_pair_carried ON PAIR (carried_id);

CREATE TABLE REPRESENTS (                                 -- DC-10: no maximum of two countries
    carrier_id   INT     NOT NULL,
    carried_id   INT     NOT NULL,
    country_code CHAR(3) NOT NULL,
    PRIMARY KEY (carrier_id, carried_id, country_code),
    CONSTRAINT fk_rep_pair FOREIGN KEY (carrier_id, carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_rep_country FOREIGN KEY (country_code)
        REFERENCES COUNTRY(country_code) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_rep_country ON REPRESENTS (country_code);

-- ---------------------------------------------------------------------------
-- Championships
-- ---------------------------------------------------------------------------
CREATE TABLE CHAMPIONSHIP (
    champ_id        INT AUTO_INCREMENT,
    year            SMALLINT NOT NULL,
    edition_number  SMALLINT NULL,
    start_date      DATE     NULL,                        -- not published for older editions
    end_date        DATE     NULL,
    is_grand_prix   BOOLEAN  NOT NULL DEFAULT FALSE,
    spectator_count INT      NULL,
    venue_id        INT      NOT NULL,
    organiser_id    INT      NOT NULL,
    PRIMARY KEY (champ_id),
    CONSTRAINT chk_champ_dates CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    CONSTRAINT chk_champ_spectators CHECK (spectator_count IS NULL OR spectator_count >= 0),
    CONSTRAINT fk_champ_venue FOREIGN KEY (venue_id)
        REFERENCES VENUE(venue_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_champ_organiser FOREIGN KEY (organiser_id)
        REFERENCES ORGANISER(organiser_id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_champ_year ON CHAMPIONSHIP (year);

CREATE TABLE CHAMP_HOST_LANGUAGE (
    champ_id      INT         NOT NULL,
    host_language VARCHAR(40) NOT NULL,
    PRIMARY KEY (champ_id, host_language),
    CONSTRAINT fk_lang_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE HAS_CATEGORY (
    champ_id INT         NOT NULL,
    cat_code VARCHAR(10) NOT NULL,
    PRIMARY KEY (champ_id, cat_code),
    CONSTRAINT fk_hc_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_hc_cat FOREIGN KEY (cat_code)
        REFERENCES RACE_CATEGORY(cat_code) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE JUDGES (
    official_id INT         NOT NULL,
    champ_id    INT         NOT NULL,
    cat_code    VARCHAR(10) NOT NULL,
    PRIMARY KEY (official_id, champ_id, cat_code),
    CONSTRAINT fk_judges_official FOREIGN KEY (official_id)
        REFERENCES OFFICIAL(person_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_judges_offered FOREIGN KEY (champ_id, cat_code)             -- DC-11
        REFERENCES HAS_CATEGORY(champ_id, cat_code) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE RACE_HEAT (
    champ_id       INT         NOT NULL,
    cat_code       VARCHAR(10) NOT NULL,
    heat_number    SMALLINT    NOT NULL,
    round          ENUM('HEAT','FINAL') NOT NULL DEFAULT 'FINAL',             -- DC-3
    scheduled_time DATETIME    NULL,
    last_finish_at DATETIME    NULL,                                          -- DC-5
    status         ENUM('SCHEDULED','COMPLETED','CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
    PRIMARY KEY (champ_id, cat_code, heat_number),
    CONSTRAINT chk_heat_number CHECK (heat_number >= 1),
    CONSTRAINT fk_heat_offered FOREIGN KEY (champ_id, cat_code)               -- DC-11
        REFERENCES HAS_CATEGORY(champ_id, cat_code) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE PARTICIPATES_IN (
    carrier_id  INT         NOT NULL,
    carried_id  INT         NOT NULL,
    champ_id    INT         NOT NULL,
    cat_code    VARCHAR(10) NOT NULL,
    heat_number SMALLINT    NOT NULL,
    PRIMARY KEY (carrier_id, carried_id, champ_id, cat_code, heat_number),
    CONSTRAINT fk_part_pair FOREIGN KEY (carrier_id, carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_part_heat FOREIGN KEY (champ_id, cat_code, heat_number)
        REFERENCES RACE_HEAT(champ_id, cat_code, heat_number) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_part_heat ON PARTICIPATES_IN (champ_id, cat_code, heat_number);

CREATE TABLE RACE_RESULT (
    carrier_id          INT         NOT NULL,
    carried_id          INT         NOT NULL,
    champ_id            INT         NOT NULL,
    cat_code            VARCHAR(10) NOT NULL,
    heat_number         SMALLINT    NOT NULL,
    finish_time_ms      INT         NULL,                                     -- DC-7
    finish_status       ENUM('COMPLETED','DNF','DNS','DQ') NOT NULL DEFAULT 'COMPLETED',
    rank_in_heat        SMALLINT    NULL,
    diff_to_leader_ms   INT         NULL,
    drop_count          TINYINT     NULL,                                     -- DC-7
    composition_changed BOOLEAN     NOT NULL DEFAULT FALSE,                   -- DC-6
    PRIMARY KEY (carrier_id, carried_id, champ_id, cat_code, heat_number),
    CONSTRAINT chk_result_time CHECK (finish_time_ms IS NULL OR finish_time_ms > 0),
    CONSTRAINT chk_result_rank CHECK (rank_in_heat IS NULL OR rank_in_heat >= 1),
    CONSTRAINT chk_result_drops CHECK (drop_count IS NULL OR drop_count >= 0),
    -- Also guarantees "every result belongs to a pair that took part in that heat" (DC-11).
    CONSTRAINT fk_result_participation FOREIGN KEY (carrier_id, carried_id, champ_id, cat_code, heat_number)
        REFERENCES PARTICIPATES_IN(carrier_id, carried_id, champ_id, cat_code, heat_number)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_result_pair FOREIGN KEY (carrier_id, carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_result_heat FOREIGN KEY (champ_id, cat_code, heat_number)
        REFERENCES RACE_HEAT(champ_id, cat_code, heat_number) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_result_heat_rank ON RACE_RESULT (champ_id, cat_code, heat_number, rank_in_heat);

-- DC-1: registration per championship and category.
CREATE TABLE REGISTRATION (
    champ_id           INT          NOT NULL,
    cat_code           VARCHAR(10)  NOT NULL,
    carrier_id         INT          NOT NULL,
    carried_id         INT          NOT NULL,
    bib_number         SMALLINT     NULL,
    backpack_weight_kg DECIMAL(5,2) NOT NULL DEFAULT 0,
    fee_paid           DECIMAL(6,2) NULL,
    status             ENUM('CONFIRMED','CANCELLED','REPLACED') NOT NULL DEFAULT 'CONFIRMED',
    refund_amount      DECIMAL(6,2) NULL,
    registered_at      DATETIME     NULL,
    PRIMARY KEY (champ_id, cat_code, carrier_id, carried_id),
    CONSTRAINT uq_reg_bib UNIQUE (champ_id, cat_code, bib_number),            -- C4
    CONSTRAINT chk_reg_fee CHECK (fee_paid IS NULL OR fee_paid IN (55, 160)), -- C6
    CONSTRAINT chk_reg_backpack CHECK (backpack_weight_kg >= 0),
    CONSTRAINT fk_reg_offered FOREIGN KEY (champ_id, cat_code)
        REFERENCES HAS_CATEGORY(champ_id, cat_code) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_reg_pair FOREIGN KEY (carrier_id, carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- DC-4: the Team race has four people, so it cannot be a pair result.
CREATE TABLE TEAM_RESULT (
    champ_id          INT      NOT NULL,
    team_id           INT      NOT NULL,
    bib_number        SMALLINT NULL,
    finish_time_ms    INT      NULL,
    penalty_ms        INT      NOT NULL DEFAULT 0,
    finish_status     ENUM('COMPLETED','DNF','DNS','DQ') NOT NULL DEFAULT 'COMPLETED',
    rank_in_race      SMALLINT NULL,
    diff_to_leader_ms INT      NULL,
    PRIMARY KEY (champ_id, team_id),
    CONSTRAINT chk_team_time CHECK (finish_time_ms IS NULL OR finish_time_ms > 0),
    CONSTRAINT chk_team_penalty CHECK (penalty_ms >= 0),
    CONSTRAINT fk_tr_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tr_team FOREIGN KEY (team_id)
        REFERENCES TEAM(team_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------------
-- Protests
-- ---------------------------------------------------------------------------
CREATE TABLE PROTEST (
    champ_id           INT          NOT NULL,
    protest_seq        INT          NOT NULL,
    filed_at           DATETIME     NOT NULL,
    fee_paid           DECIMAL(6,2) NOT NULL,
    status             ENUM('PENDING','UNDER_REVIEW','UPHELD','REJECTED') NOT NULL DEFAULT 'PENDING',
    description        TEXT         NOT NULL,
    heat_cat_code      VARCHAR(10)  NOT NULL,
    heat_number        SMALLINT     NOT NULL,
    filer_carrier_id   INT          NOT NULL,
    filer_carried_id   INT          NOT NULL,
    against_carrier_id INT          NOT NULL,
    against_carried_id INT          NOT NULL,
    PRIMARY KEY (champ_id, protest_seq),
    CONSTRAINT chk_protest_fee CHECK (fee_paid = 150),                        -- C6
    CONSTRAINT fk_protest_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_protest_heat FOREIGN KEY (champ_id, heat_cat_code, heat_number)
        REFERENCES RACE_HEAT(champ_id, cat_code, heat_number) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_protest_filer FOREIGN KEY (filer_carrier_id, filer_carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_protest_against FOREIGN KEY (against_carrier_id, against_carried_id)
        REFERENCES PAIR(carrier_id, carried_id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE TABLE PROTEST_DECISION (
    champ_id         INT      NOT NULL,
    protest_seq      INT      NOT NULL,
    decision_seq     INT      NOT NULL,
    decision_text    TEXT     NOT NULL,
    decided_at       DATETIME NOT NULL,
    decision_outcome ENUM('UPHELD','REJECTED') NOT NULL,
    decided_by       INT      NOT NULL,
    PRIMARY KEY (champ_id, protest_seq, decision_seq),
    CONSTRAINT fk_decision_protest FOREIGN KEY (champ_id, protest_seq)
        REFERENCES PROTEST(champ_id, protest_seq) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_decision_official FOREIGN KEY (decided_by)
        REFERENCES OFFICIAL(person_id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX idx_decision_official ON PROTEST_DECISION (decided_by);

-- ---------------------------------------------------------------------------
-- Sponsors and press
-- ---------------------------------------------------------------------------
CREATE TABLE SPONSOR (
    sponsor_id      INT AUTO_INCREMENT,
    name            VARCHAR(120) NOT NULL,
    country         VARCHAR(80)  NULL,
    contact_email   VARCHAR(120) NULL,
    contact_phone   VARCHAR(30)  NULL,
    contact_address VARCHAR(200) NULL,
    PRIMARY KEY (sponsor_id),
    CONSTRAINT uq_sponsor_name UNIQUE (name)
);

CREATE TABLE SPONSOR_CATEGORY (
    sponsor_id           INT         NOT NULL,
    sponsorship_category VARCHAR(60) NOT NULL,
    PRIMARY KEY (sponsor_id, sponsorship_category),
    CONSTRAINT fk_sc_sponsor FOREIGN KEY (sponsor_id)
        REFERENCES SPONSOR(sponsor_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE SPONSORS (
    champ_id       INT         NOT NULL,
    sponsor_id     INT         NOT NULL,
    tier           VARCHAR(40) NOT NULL,
    contract_start DATE        NULL,
    contract_end   DATE        NULL,
    PRIMARY KEY (champ_id, sponsor_id),
    CONSTRAINT chk_contract CHECK (contract_end IS NULL OR contract_start IS NULL OR contract_end >= contract_start),
    CONSTRAINT fk_sponsors_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_sponsors_sponsor FOREIGN KEY (sponsor_id)
        REFERENCES SPONSOR(sponsor_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE PRESS_OUTLET (
    outlet_id       INT AUTO_INCREMENT,
    name            VARCHAR(120) NOT NULL,
    country         VARCHAR(80)  NULL,
    contact_email   VARCHAR(120) NULL,
    contact_phone   VARCHAR(30)  NULL,
    contact_address VARCHAR(200) NULL,
    PRIMARY KEY (outlet_id)
);
CREATE INDEX idx_outlet_name ON PRESS_OUTLET (name);

CREATE TABLE ACCREDITS (
    champ_id         INT     NOT NULL,
    outlet_id        INT     NOT NULL,
    drone_permission BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (champ_id, outlet_id),
    CONSTRAINT fk_acc_champ FOREIGN KEY (champ_id)
        REFERENCES CHAMPIONSHIP(champ_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_acc_outlet FOREIGN KEY (outlet_id)
        REFERENCES PRESS_OUTLET(outlet_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- DC-8: audit trail for D-1. No foreign key: the championship is gone by design.
CREATE TABLE CHAMPIONSHIP_DELETION_LOG (
    log_id     INT AUTO_INCREMENT,
    champ_id   INT          NOT NULL,
    year       SMALLINT     NOT NULL,
    deleted_by VARCHAR(120) NOT NULL,
    deleted_at DATETIME     NOT NULL,
    reason     VARCHAR(255) NOT NULL,
    PRIMARY KEY (log_id)
);

-- ---------------------------------------------------------------------------
-- Triggers: rules that span tables, which a MySQL CHECK cannot express.
-- Imported rows may have an unpublished birth date or weight (DC-9); these
-- checks apply whenever the value is known, and the web forms require it.
-- ---------------------------------------------------------------------------
DELIMITER //

CREATE TRIGGER trg_registration_rules BEFORE INSERT ON REGISTRATION
FOR EACH ROW
BEGIN
    DECLARE v_start DATE;
    DECLARE v_min_carrier, v_min_carried TINYINT;
    DECLARE v_min_weight DECIMAL(5,2);
    DECLARE v_dob_carrier, v_dob_carried DATE;
    DECLARE v_weight DECIMAL(5,2);

    SELECT start_date INTO v_start FROM CHAMPIONSHIP WHERE champ_id = NEW.champ_id;
    SELECT min_age_carrier, min_age_carried, min_weight_carried_kg
      INTO v_min_carrier, v_min_carried, v_min_weight
      FROM RACE_CATEGORY WHERE cat_code = NEW.cat_code;
    SELECT date_of_birth INTO v_dob_carrier FROM PERSON WHERE person_id = NEW.carrier_id;
    SELECT date_of_birth INTO v_dob_carried FROM PERSON WHERE person_id = NEW.carried_id;
    SELECT weight_kg INTO v_weight FROM COMPETITOR WHERE person_id = NEW.carried_id;

    IF v_start IS NOT NULL AND v_dob_carrier IS NOT NULL
       AND TIMESTAMPDIFF(YEAR, v_dob_carrier, v_start) < v_min_carrier THEN      -- C1
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carrier is younger than the minimum age for this category on the start date.';
    END IF;
    IF v_start IS NOT NULL AND v_dob_carried IS NOT NULL
       AND TIMESTAMPDIFF(YEAR, v_dob_carried, v_start) < v_min_carried THEN      -- C2
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carried competitor is younger than the minimum age for this category on the start date.';
    END IF;
    IF v_weight IS NOT NULL THEN                                                 -- C3
        SET NEW.backpack_weight_kg = GREATEST(v_min_weight - v_weight, 0);
    END IF;
END //

CREATE TRIGGER trg_registration_cancel BEFORE UPDATE ON REGISTRATION
FOR EACH ROW
BEGIN
    DECLARE v_start DATE;
    IF NEW.status = 'CANCELLED' AND OLD.status <> 'CANCELLED' THEN               -- C7, C15
        SELECT start_date INTO v_start FROM CHAMPIONSHIP WHERE champ_id = NEW.champ_id;
        IF v_start IS NOT NULL AND DATEDIFF(v_start, CURDATE()) >= 30 THEN
            SET NEW.refund_amount = IFNULL(NEW.fee_paid, 0) - 10;
        ELSE
            SET NEW.refund_amount = 0;
        END IF;
    END IF;
END //

CREATE TRIGGER trg_protest_rules BEFORE INSERT ON PROTEST
FOR EACH ROW
BEGIN
    DECLARE v_finish DATETIME;

    SELECT last_finish_at INTO v_finish FROM RACE_HEAT
     WHERE champ_id = NEW.champ_id AND cat_code = NEW.heat_cat_code AND heat_number = NEW.heat_number;
    IF v_finish IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No finish time is recorded for this heat, so a protest cannot be accepted.';
    END IF;
    IF NEW.filed_at < v_finish OR NEW.filed_at > v_finish + INTERVAL 15 MINUTE THEN  -- C5
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PROTEST_WINDOW_EXPIRED: a protest must be filed within 15 minutes of the last finish in the heat.';
    END IF;
    IF (NEW.filer_carrier_id, NEW.filer_carried_id) = (NEW.against_carrier_id, NEW.against_carried_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A pair cannot file a protest against itself.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM PARTICIPATES_IN
                    WHERE carrier_id = NEW.filer_carrier_id AND carried_id = NEW.filer_carried_id
                      AND champ_id = NEW.champ_id AND cat_code = NEW.heat_cat_code AND heat_number = NEW.heat_number)
       OR NOT EXISTS (SELECT 1 FROM PARTICIPATES_IN
                    WHERE carrier_id = NEW.against_carrier_id AND carried_id = NEW.against_carried_id
                      AND champ_id = NEW.champ_id AND cat_code = NEW.heat_cat_code AND heat_number = NEW.heat_number) THEN  -- C13
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Both pairs must have taken part in the protested heat.';
    END IF;
END //

CREATE TRIGGER trg_decision_jury BEFORE INSERT ON PROTEST_DECISION
FOR EACH ROW
BEGIN
    IF NOT EXISTS (SELECT 1 FROM OFFICIAL WHERE person_id = NEW.decided_by AND official_role = 'JURY') THEN  -- C13
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only an official with the JURY role may decide a protest.';
    END IF;
END //

CREATE TRIGGER trg_judges_certification BEFORE INSERT ON JUDGES
FOR EACH ROW
BEGIN
    DECLARE v_level TINYINT;
    DECLARE v_role VARCHAR(30);
    SELECT certification_level, official_role INTO v_level, v_role
      FROM OFFICIAL WHERE person_id = NEW.official_id;
    IF v_level < 2 OR (v_role = 'JURY' AND v_level < 3) THEN                     -- C11
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Official does not hold the certification level needed to judge.';
    END IF;
END //

DELIMITER ;
