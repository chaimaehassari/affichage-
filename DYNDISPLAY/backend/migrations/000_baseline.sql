-- =============================================================================
-- 000_baseline.sql — SCHEMA DE BASE DynDisplay
-- =============================================================================
-- Ce fichier cree TOUTES les tables de fondation du schema metier :
--   audit_logs, ftp_profiles, general_settings, layout_zones, layouts, media,
--   password_history, password_reset_tokens, permissions, post_configurations,
--   posts, profiles, schedules, screen_group_posts, screen_groups, sites,
--   sync_items, sync_jobs, user_permissions, user_zone_access, users, zone_media
--
-- Il correspond a l'etat du schema AVANT la migration 003. Les migrations
-- 003..025 s'y appliquent ensuite par-dessus, dans l'ordre numerique.
--
-- ORIGINE : ce schema n'existait dans AUCUN script du depot (la serie des
-- migrations demarrait a 003, sans 001 ni 002). Il a ete RECONSTITUE depuis la
-- base de developpement en annulant sur une base jetable l'apport de chaque
-- migration 003..025, puis verifie : reconstruire une base vierge avec
--   000_baseline.sql + 003..025
-- redonne un schema SEMANTIQUEMENT IDENTIQUE a la base de developpement
-- (26 tables, 219 colonnes, 79 index, 84 contraintes, 24 sequences).
--
-- IDEMPOTENCE : tables, sequences, index et contraintes sont tous crees sous
-- garde IF NOT EXISTS / DO $$ ... IF, comme les migrations 008 a 025. Une
-- table schema_migrations perdue ne rend donc pas la base irrecuperable.
-- Generateur : deploy/verify/make_baseline_idempotent.py
-- Verification : deploy/verify/verify_baseline.py
--
-- Ne PAS editer a la main : toute evolution passe par une NOUVELLE migration
-- numerotee (026, 027...). Ce fichier doit rester le point de depart stable.
-- =============================================================================
--
-- PostgreSQL database dump
--



SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.audit_logs (    audit_id bigint NOT NULL,
    user_id bigint,
    action character varying(100) NOT NULL,
    entity_type character varying(100),
    entity_id bigint,
    description character varying(1000),
    ip_address character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: audit_logs_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.audit_logs_audit_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_audit_id_seq OWNED BY public.audit_logs.audit_id;


--
-- Name: ftp_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.ftp_profiles (    ftp_profile_id bigint NOT NULL,
    name character varying(150) NOT NULL,
    server_address character varying(255) NOT NULL,
    is_anonymous boolean DEFAULT false NOT NULL,
    username character varying(150),
    password_hash character varying(255),
    security_mode character varying(30) DEFAULT 'NONE'::character varying NOT NULL,
    ignore_certificate_errors boolean DEFAULT false NOT NULL,
    port integer,
    connection_timeout integer,
    passive_connection boolean DEFAULT true NOT NULL,
    transfer_mode character varying(20) DEFAULT 'BINARY'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT chk_security_mode CHECK (((security_mode)::text = ANY ((ARRAY['NONE'::character varying, 'FTPS'::character varying, 'SFTP'::character varying, 'FTPES'::character varying])::text[]))),
    CONSTRAINT chk_transfer_mode CHECK (((transfer_mode)::text = ANY ((ARRAY['ASCII'::character varying, 'BINARY'::character varying])::text[])))
);


--
-- Name: ftp_profiles_ftp_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.ftp_profiles_ftp_profile_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ftp_profiles_ftp_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ftp_profiles_ftp_profile_id_seq OWNED BY public.ftp_profiles.ftp_profile_id;


--
-- Name: general_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.general_settings (    setting_id bigint NOT NULL,
    setting_key character varying(100) NOT NULL,
    setting_value character varying(1000),
    description character varying(255),
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: general_settings_setting_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.general_settings_setting_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: general_settings_setting_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.general_settings_setting_id_seq OWNED BY public.general_settings.setting_id;


--
-- Name: layout_zones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.layout_zones (    layout_zone_id bigint NOT NULL,
    layout_id bigint NOT NULL,
    zone_number integer NOT NULL,
    position_x numeric(5,2) NOT NULL,
    position_y numeric(5,2) NOT NULL,
    width numeric(5,2) NOT NULL,
    height numeric(5,2) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT chk_layout_zone_number CHECK (((zone_number >= 1) AND (zone_number <= 8)))
);


--
-- Name: layout_zones_layout_zone_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.layout_zones_layout_zone_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: layout_zones_layout_zone_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.layout_zones_layout_zone_id_seq OWNED BY public.layout_zones.layout_zone_id;


--
-- Name: layouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.layouts (    layout_id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    name character varying(150) DEFAULT 'Layout'::character varying NOT NULL
);


--
-- Name: layouts_layout_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.layouts_layout_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: layouts_layout_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.layouts_layout_id_seq OWNED BY public.layouts.layout_id;


--
-- Name: media; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.media (    media_id bigint NOT NULL,
    name character varying(255) NOT NULL,
    original_filename character varying(255) NOT NULL,
    media_type character varying(20) NOT NULL,
    mime_type character varying(100),
    file_extension character varying(20),
    file_size bigint,
    sftp_path character varying(500) NOT NULL,
    checksum character varying(128),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT chk_media_type CHECK (((media_type)::text = ANY (ARRAY['IMAGE'::text, 'VIDEO'::text, 'DOCUMENT'::text, 'OTHER'::text])))
);


--
-- Name: media_media_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.media_media_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: media_media_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.media_media_id_seq OWNED BY public.media.media_id;


--
-- Name: password_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.password_history (    password_history_id bigint NOT NULL,
    user_id bigint NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: password_history_password_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.password_history_password_history_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_history_password_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.password_history_password_history_id_seq OWNED BY public.password_history.password_history_id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.password_reset_tokens (    reset_token_id bigint NOT NULL,
    user_id bigint NOT NULL,
    token character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: password_reset_tokens_reset_token_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.password_reset_tokens_reset_token_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_reset_tokens_reset_token_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.password_reset_tokens_reset_token_id_seq OWNED BY public.password_reset_tokens.reset_token_id;


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.permissions (    permission_id bigint NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(150) NOT NULL,
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: permissions_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.permissions_permission_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: permissions_permission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.permissions_permission_id_seq OWNED BY public.permissions.permission_id;


--
-- Name: post_configurations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.post_configurations (    configuration_id bigint NOT NULL,
    post_id bigint NOT NULL,
    layout_id bigint,
    loop_enabled boolean DEFAULT true NOT NULL,
    schedule_enabled boolean DEFAULT false NOT NULL,
    display_enabled boolean DEFAULT true NOT NULL,
    version_number integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: post_configurations_configuration_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.post_configurations_configuration_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: post_configurations_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.post_configurations_configuration_id_seq OWNED BY public.post_configurations.configuration_id;


--
-- Name: posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.posts (    post_id bigint NOT NULL,
    site_id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    player_type character varying(30),
    ip_address character varying(50),
    is_active boolean DEFAULT true NOT NULL,
    is_online boolean DEFAULT false NOT NULL,
    is_up_to_date boolean DEFAULT false NOT NULL,
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    media_id bigint,
    last_heartbeat_at timestamp with time zone
);


--
-- Name: posts_post_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.posts_post_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: posts_post_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.posts_post_id_seq OWNED BY public.posts.post_id;


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.profiles (    profile_id bigint NOT NULL,
    name character varying(50) NOT NULL,
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: profiles_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.profiles_profile_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: profiles_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.profiles_profile_id_seq OWNED BY public.profiles.profile_id;


--
-- Name: schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.schedules (    schedule_id bigint NOT NULL,
    post_id bigint NOT NULL,
    name character varying(150) NOT NULL,
    start_date date,
    end_date date,
    start_time time without time zone,
    end_time time without time zone,
    days_of_week character varying(50),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT chk_schedule_dates CHECK (((end_date IS NULL) OR (start_date IS NULL) OR (end_date >= start_date)))
);


--
-- Name: schedules_schedule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.schedules_schedule_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: schedules_schedule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.schedules_schedule_id_seq OWNED BY public.schedules.schedule_id;


--
-- Name: screen_group_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.screen_group_posts (    group_post_id bigint NOT NULL,
    group_id bigint NOT NULL,
    post_id bigint NOT NULL
);


--
-- Name: screen_group_posts_group_post_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.screen_group_posts_group_post_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: screen_group_posts_group_post_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.screen_group_posts_group_post_id_seq OWNED BY public.screen_group_posts.group_post_id;


--
-- Name: screen_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.screen_groups (    group_id bigint NOT NULL,
    name character varying(150) NOT NULL,
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: screen_groups_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.screen_groups_group_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: screen_groups_group_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.screen_groups_group_id_seq OWNED BY public.screen_groups.group_id;


--
-- Name: sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.sites (    site_id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    address character varying(255),
    description character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: sites_site_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.sites_site_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sites_site_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sites_site_id_seq OWNED BY public.sites.site_id;


--
-- Name: sync_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.sync_items (    sync_item_id bigint NOT NULL,
    sync_job_id bigint NOT NULL,
    media_id bigint,
    item_type character varying(30) NOT NULL,
    item_path character varying(500),
    status character varying(30) NOT NULL,
    progress_percent integer DEFAULT 0 NOT NULL,
    CONSTRAINT chk_sync_item_progress CHECK (((progress_percent >= 0) AND (progress_percent <= 100)))
);


--
-- Name: sync_items_sync_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.sync_items_sync_item_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_items_sync_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_items_sync_item_id_seq OWNED BY public.sync_items.sync_item_id;


--
-- Name: sync_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.sync_jobs (    sync_job_id bigint NOT NULL,
    post_id bigint NOT NULL,
    status character varying(30) NOT NULL,
    progress_percent integer DEFAULT 0 NOT NULL,
    transfer_speed bigint DEFAULT 0 NOT NULL,
    estimated_remaining_seconds bigint,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    error_message character varying(1000),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_sync_progress CHECK (((progress_percent >= 0) AND (progress_percent <= 100)))
);


--
-- Name: sync_jobs_sync_job_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.sync_jobs_sync_job_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_jobs_sync_job_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_jobs_sync_job_id_seq OWNED BY public.sync_jobs.sync_job_id;


--
-- Name: user_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_permissions (    user_permission_id bigint NOT NULL,
    user_id bigint NOT NULL,
    permission_id bigint NOT NULL,
    can_view boolean DEFAULT false NOT NULL,
    can_create boolean DEFAULT false NOT NULL,
    can_update boolean DEFAULT false NOT NULL,
    can_delete boolean DEFAULT false NOT NULL
);


--
-- Name: user_permissions_user_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.user_permissions_user_permission_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_permissions_user_permission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_permissions_user_permission_id_seq OWNED BY public.user_permissions.user_permission_id;


--
-- Name: user_zone_access; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.user_zone_access (    user_zone_access_id bigint NOT NULL,
    user_id bigint NOT NULL,
    zone_number integer NOT NULL,
    is_allowed boolean DEFAULT true NOT NULL,
    CONSTRAINT chk_user_zone_number CHECK (((zone_number >= 1) AND (zone_number <= 8)))
);


--
-- Name: user_zone_access_user_zone_access_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.user_zone_access_user_zone_access_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_zone_access_user_zone_access_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_zone_access_user_zone_access_id_seq OWNED BY public.user_zone_access.user_zone_access_id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.users (    user_id bigint NOT NULL,
    profile_id bigint NOT NULL,
    login character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    must_change_password boolean DEFAULT true NOT NULL,
    suspended_at timestamp with time zone,
    failed_attempts integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    last_login_at timestamp with time zone,
    last_password_change_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    user_code character varying(50)
);


--
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.users_user_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.users.user_id;


--
-- Name: zone_media; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.zone_media (    zone_media_id bigint NOT NULL,
    post_id bigint NOT NULL,
    zone_number integer NOT NULL,
    media_id bigint NOT NULL,
    display_order integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    CONSTRAINT chk_zone_media_zone CHECK (((zone_number >= 1) AND (zone_number <= 8)))
);


--
-- Name: zone_media_zone_media_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE IF NOT EXISTS public.zone_media_zone_media_id_seq    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_media_zone_media_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_media_zone_media_id_seq OWNED BY public.zone_media.zone_media_id;


--
-- Name: audit_logs audit_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN audit_id SET DEFAULT nextval('public.audit_logs_audit_id_seq'::regclass);


--
-- Name: ftp_profiles ftp_profile_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ftp_profiles ALTER COLUMN ftp_profile_id SET DEFAULT nextval('public.ftp_profiles_ftp_profile_id_seq'::regclass);


--
-- Name: general_settings setting_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.general_settings ALTER COLUMN setting_id SET DEFAULT nextval('public.general_settings_setting_id_seq'::regclass);


--
-- Name: layout_zones layout_zone_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.layout_zones ALTER COLUMN layout_zone_id SET DEFAULT nextval('public.layout_zones_layout_zone_id_seq'::regclass);


--
-- Name: layouts layout_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.layouts ALTER COLUMN layout_id SET DEFAULT nextval('public.layouts_layout_id_seq'::regclass);


--
-- Name: media media_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media ALTER COLUMN media_id SET DEFAULT nextval('public.media_media_id_seq'::regclass);


--
-- Name: password_history password_history_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_history ALTER COLUMN password_history_id SET DEFAULT nextval('public.password_history_password_history_id_seq'::regclass);


--
-- Name: password_reset_tokens reset_token_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens ALTER COLUMN reset_token_id SET DEFAULT nextval('public.password_reset_tokens_reset_token_id_seq'::regclass);


--
-- Name: permissions permission_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions ALTER COLUMN permission_id SET DEFAULT nextval('public.permissions_permission_id_seq'::regclass);


--
-- Name: post_configurations configuration_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.post_configurations ALTER COLUMN configuration_id SET DEFAULT nextval('public.post_configurations_configuration_id_seq'::regclass);


--
-- Name: posts post_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.posts ALTER COLUMN post_id SET DEFAULT nextval('public.posts_post_id_seq'::regclass);


--
-- Name: profiles profile_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles ALTER COLUMN profile_id SET DEFAULT nextval('public.profiles_profile_id_seq'::regclass);


--
-- Name: schedules schedule_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules ALTER COLUMN schedule_id SET DEFAULT nextval('public.schedules_schedule_id_seq'::regclass);


--
-- Name: screen_group_posts group_post_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screen_group_posts ALTER COLUMN group_post_id SET DEFAULT nextval('public.screen_group_posts_group_post_id_seq'::regclass);


--
-- Name: screen_groups group_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screen_groups ALTER COLUMN group_id SET DEFAULT nextval('public.screen_groups_group_id_seq'::regclass);


--
-- Name: sites site_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sites ALTER COLUMN site_id SET DEFAULT nextval('public.sites_site_id_seq'::regclass);


--
-- Name: sync_items sync_item_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_items ALTER COLUMN sync_item_id SET DEFAULT nextval('public.sync_items_sync_item_id_seq'::regclass);


--
-- Name: sync_jobs sync_job_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_jobs ALTER COLUMN sync_job_id SET DEFAULT nextval('public.sync_jobs_sync_job_id_seq'::regclass);


--
-- Name: user_permissions user_permission_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_permissions ALTER COLUMN user_permission_id SET DEFAULT nextval('public.user_permissions_user_permission_id_seq'::regclass);


--
-- Name: user_zone_access user_zone_access_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zone_access ALTER COLUMN user_zone_access_id SET DEFAULT nextval('public.user_zone_access_user_zone_access_id_seq'::regclass);


--
-- Name: users user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN user_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- Name: zone_media zone_media_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_media ALTER COLUMN zone_media_id SET DEFAULT nextval('public.zone_media_zone_media_id_seq'::regclass);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'audit_logs'
                     AND con.conname = 'audit_logs_pkey') THEN
        ALTER TABLE ONLY public.audit_logs ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (audit_id);
    END IF;
END $$;

--
-- Name: ftp_profiles ftp_profiles_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'ftp_profiles'
                     AND con.conname = 'ftp_profiles_name_key') THEN
        ALTER TABLE ONLY public.ftp_profiles ADD CONSTRAINT ftp_profiles_name_key UNIQUE (name);
    END IF;
END $$;

--
-- Name: ftp_profiles ftp_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'ftp_profiles'
                     AND con.conname = 'ftp_profiles_pkey') THEN
        ALTER TABLE ONLY public.ftp_profiles ADD CONSTRAINT ftp_profiles_pkey PRIMARY KEY (ftp_profile_id);
    END IF;
END $$;

--
-- Name: general_settings general_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'general_settings'
                     AND con.conname = 'general_settings_pkey') THEN
        ALTER TABLE ONLY public.general_settings ADD CONSTRAINT general_settings_pkey PRIMARY KEY (setting_id);
    END IF;
END $$;

--
-- Name: general_settings general_settings_setting_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'general_settings'
                     AND con.conname = 'general_settings_setting_key_key') THEN
        ALTER TABLE ONLY public.general_settings ADD CONSTRAINT general_settings_setting_key_key UNIQUE (setting_key);
    END IF;
END $$;

--
-- Name: layout_zones layout_zones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'layout_zones'
                     AND con.conname = 'layout_zones_pkey') THEN
        ALTER TABLE ONLY public.layout_zones ADD CONSTRAINT layout_zones_pkey PRIMARY KEY (layout_zone_id);
    END IF;
END $$;

--
-- Name: layouts layouts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'layouts'
                     AND con.conname = 'layouts_pkey') THEN
        ALTER TABLE ONLY public.layouts ADD CONSTRAINT layouts_pkey PRIMARY KEY (layout_id);
    END IF;
END $$;

--
-- Name: media media_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'media'
                     AND con.conname = 'media_pkey') THEN
        ALTER TABLE ONLY public.media ADD CONSTRAINT media_pkey PRIMARY KEY (media_id);
    END IF;
END $$;

--
-- Name: media media_sftp_path_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'media'
                     AND con.conname = 'media_sftp_path_key') THEN
        ALTER TABLE ONLY public.media ADD CONSTRAINT media_sftp_path_key UNIQUE (sftp_path);
    END IF;
END $$;

--
-- Name: password_history password_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'password_history'
                     AND con.conname = 'password_history_pkey') THEN
        ALTER TABLE ONLY public.password_history ADD CONSTRAINT password_history_pkey PRIMARY KEY (password_history_id);
    END IF;
END $$;

--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'password_reset_tokens'
                     AND con.conname = 'password_reset_tokens_pkey') THEN
        ALTER TABLE ONLY public.password_reset_tokens ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (reset_token_id);
    END IF;
END $$;

--
-- Name: password_reset_tokens password_reset_tokens_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'password_reset_tokens'
                     AND con.conname = 'password_reset_tokens_token_key') THEN
        ALTER TABLE ONLY public.password_reset_tokens ADD CONSTRAINT password_reset_tokens_token_key UNIQUE (token);
    END IF;
END $$;

--
-- Name: permissions permissions_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'permissions'
                     AND con.conname = 'permissions_code_key') THEN
        ALTER TABLE ONLY public.permissions ADD CONSTRAINT permissions_code_key UNIQUE (code);
    END IF;
END $$;

--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'permissions'
                     AND con.conname = 'permissions_pkey') THEN
        ALTER TABLE ONLY public.permissions ADD CONSTRAINT permissions_pkey PRIMARY KEY (permission_id);
    END IF;
END $$;

--
-- Name: post_configurations post_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'post_configurations'
                     AND con.conname = 'post_configurations_pkey') THEN
        ALTER TABLE ONLY public.post_configurations ADD CONSTRAINT post_configurations_pkey PRIMARY KEY (configuration_id);
    END IF;
END $$;

--
-- Name: posts posts_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'posts'
                     AND con.conname = 'posts_code_key') THEN
        ALTER TABLE ONLY public.posts ADD CONSTRAINT posts_code_key UNIQUE (code);
    END IF;
END $$;

--
-- Name: posts posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'posts'
                     AND con.conname = 'posts_pkey') THEN
        ALTER TABLE ONLY public.posts ADD CONSTRAINT posts_pkey PRIMARY KEY (post_id);
    END IF;
END $$;

--
-- Name: profiles profiles_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'profiles'
                     AND con.conname = 'profiles_name_key') THEN
        ALTER TABLE ONLY public.profiles ADD CONSTRAINT profiles_name_key UNIQUE (name);
    END IF;
END $$;

--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'profiles'
                     AND con.conname = 'profiles_pkey') THEN
        ALTER TABLE ONLY public.profiles ADD CONSTRAINT profiles_pkey PRIMARY KEY (profile_id);
    END IF;
END $$;

--
-- Name: schedules schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'schedules'
                     AND con.conname = 'schedules_pkey') THEN
        ALTER TABLE ONLY public.schedules ADD CONSTRAINT schedules_pkey PRIMARY KEY (schedule_id);
    END IF;
END $$;

--
-- Name: screen_group_posts screen_group_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_group_posts'
                     AND con.conname = 'screen_group_posts_pkey') THEN
        ALTER TABLE ONLY public.screen_group_posts ADD CONSTRAINT screen_group_posts_pkey PRIMARY KEY (group_post_id);
    END IF;
END $$;

--
-- Name: screen_groups screen_groups_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_groups'
                     AND con.conname = 'screen_groups_name_key') THEN
        ALTER TABLE ONLY public.screen_groups ADD CONSTRAINT screen_groups_name_key UNIQUE (name);
    END IF;
END $$;

--
-- Name: screen_groups screen_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_groups'
                     AND con.conname = 'screen_groups_pkey') THEN
        ALTER TABLE ONLY public.screen_groups ADD CONSTRAINT screen_groups_pkey PRIMARY KEY (group_id);
    END IF;
END $$;

--
-- Name: sites sites_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sites'
                     AND con.conname = 'sites_code_key') THEN
        ALTER TABLE ONLY public.sites ADD CONSTRAINT sites_code_key UNIQUE (code);
    END IF;
END $$;

--
-- Name: sites sites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sites'
                     AND con.conname = 'sites_pkey') THEN
        ALTER TABLE ONLY public.sites ADD CONSTRAINT sites_pkey PRIMARY KEY (site_id);
    END IF;
END $$;

--
-- Name: sync_items sync_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sync_items'
                     AND con.conname = 'sync_items_pkey') THEN
        ALTER TABLE ONLY public.sync_items ADD CONSTRAINT sync_items_pkey PRIMARY KEY (sync_item_id);
    END IF;
END $$;

--
-- Name: sync_jobs sync_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sync_jobs'
                     AND con.conname = 'sync_jobs_pkey') THEN
        ALTER TABLE ONLY public.sync_jobs ADD CONSTRAINT sync_jobs_pkey PRIMARY KEY (sync_job_id);
    END IF;
END $$;

--
-- Name: screen_group_posts uq_group_post; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_group_posts'
                     AND con.conname = 'uq_group_post') THEN
        ALTER TABLE ONLY public.screen_group_posts ADD CONSTRAINT uq_group_post UNIQUE (group_id, post_id);
    END IF;
END $$;

--
-- Name: layouts uq_layout_name; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'layouts'
                     AND con.conname = 'uq_layout_name') THEN
        ALTER TABLE ONLY public.layouts ADD CONSTRAINT uq_layout_name UNIQUE (name);
    END IF;
END $$;

--
-- Name: layout_zones uq_layout_zone; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'layout_zones'
                     AND con.conname = 'uq_layout_zone') THEN
        ALTER TABLE ONLY public.layout_zones ADD CONSTRAINT uq_layout_zone UNIQUE (layout_id, zone_number);
    END IF;
END $$;

--
-- Name: post_configurations uq_post_configuration; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'post_configurations'
                     AND con.conname = 'uq_post_configuration') THEN
        ALTER TABLE ONLY public.post_configurations ADD CONSTRAINT uq_post_configuration UNIQUE (post_id);
    END IF;
END $$;

--
-- Name: user_permissions uq_user_permission; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_permissions'
                     AND con.conname = 'uq_user_permission') THEN
        ALTER TABLE ONLY public.user_permissions ADD CONSTRAINT uq_user_permission UNIQUE (user_id, permission_id);
    END IF;
END $$;

--
-- Name: user_zone_access uq_user_zone; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_zone_access'
                     AND con.conname = 'uq_user_zone') THEN
        ALTER TABLE ONLY public.user_zone_access ADD CONSTRAINT uq_user_zone UNIQUE (user_id, zone_number);
    END IF;
END $$;

--
-- Name: user_permissions user_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_permissions'
                     AND con.conname = 'user_permissions_pkey') THEN
        ALTER TABLE ONLY public.user_permissions ADD CONSTRAINT user_permissions_pkey PRIMARY KEY (user_permission_id);
    END IF;
END $$;

--
-- Name: user_zone_access user_zone_access_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_zone_access'
                     AND con.conname = 'user_zone_access_pkey') THEN
        ALTER TABLE ONLY public.user_zone_access ADD CONSTRAINT user_zone_access_pkey PRIMARY KEY (user_zone_access_id);
    END IF;
END $$;

--
-- Name: users users_login_key; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'users'
                     AND con.conname = 'users_login_key') THEN
        ALTER TABLE ONLY public.users ADD CONSTRAINT users_login_key UNIQUE (login);
    END IF;
END $$;

--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'users'
                     AND con.conname = 'users_pkey') THEN
        ALTER TABLE ONLY public.users ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);
    END IF;
END $$;

--
-- Name: zone_media zone_media_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'zone_media'
                     AND con.conname = 'zone_media_pkey') THEN
        ALTER TABLE ONLY public.zone_media ADD CONSTRAINT zone_media_pkey PRIMARY KEY (zone_media_id);
    END IF;
END $$;

--
-- Name: idx_audit_logs_user; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_audit_logs_user') THEN
        CREATE INDEX idx_audit_logs_user ON public.audit_logs USING btree (user_id);
    END IF;
END $$;

--
-- Name: idx_group_posts_group; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_group_posts_group') THEN
        CREATE INDEX idx_group_posts_group ON public.screen_group_posts USING btree (group_id);
    END IF;
END $$;

--
-- Name: idx_group_posts_post; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_group_posts_post') THEN
        CREATE INDEX idx_group_posts_post ON public.screen_group_posts USING btree (post_id);
    END IF;
END $$;

--
-- Name: idx_layout_zones_layout; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_layout_zones_layout') THEN
        CREATE INDEX idx_layout_zones_layout ON public.layout_zones USING btree (layout_id);
    END IF;
END $$;

--
-- Name: idx_password_history_user; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_password_history_user') THEN
        CREATE INDEX idx_password_history_user ON public.password_history USING btree (user_id);
    END IF;
END $$;

--
-- Name: idx_posts_site; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_posts_site') THEN
        CREATE INDEX idx_posts_site ON public.posts USING btree (site_id);
    END IF;
END $$;

--
-- Name: idx_reset_tokens_user; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_reset_tokens_user') THEN
        CREATE INDEX idx_reset_tokens_user ON public.password_reset_tokens USING btree (user_id);
    END IF;
END $$;

--
-- Name: idx_schedules_post; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_schedules_post') THEN
        CREATE INDEX idx_schedules_post ON public.schedules USING btree (post_id);
    END IF;
END $$;

--
-- Name: idx_sync_items_job; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_sync_items_job') THEN
        CREATE INDEX idx_sync_items_job ON public.sync_items USING btree (sync_job_id);
    END IF;
END $$;

--
-- Name: idx_sync_items_media; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_sync_items_media') THEN
        CREATE INDEX idx_sync_items_media ON public.sync_items USING btree (media_id);
    END IF;
END $$;

--
-- Name: idx_sync_jobs_post; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_sync_jobs_post') THEN
        CREATE INDEX idx_sync_jobs_post ON public.sync_jobs USING btree (post_id);
    END IF;
END $$;

--
-- Name: idx_user_permissions_permission; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_user_permissions_permission') THEN
        CREATE INDEX idx_user_permissions_permission ON public.user_permissions USING btree (permission_id);
    END IF;
END $$;

--
-- Name: idx_user_permissions_user; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_user_permissions_user') THEN
        CREATE INDEX idx_user_permissions_user ON public.user_permissions USING btree (user_id);
    END IF;
END $$;

--
-- Name: idx_user_zone_access_user; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_user_zone_access_user') THEN
        CREATE INDEX idx_user_zone_access_user ON public.user_zone_access USING btree (user_id);
    END IF;
END $$;

--
-- Name: idx_users_profile; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_users_profile') THEN
        CREATE INDEX idx_users_profile ON public.users USING btree (profile_id);
    END IF;
END $$;

--
-- Name: idx_zone_media_media; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_zone_media_media') THEN
        CREATE INDEX idx_zone_media_media ON public.zone_media USING btree (media_id);
    END IF;
END $$;

--
-- Name: idx_zone_media_post; Type: INDEX; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relname = 'idx_zone_media_post') THEN
        CREATE INDEX idx_zone_media_post ON public.zone_media USING btree (post_id);
    END IF;
END $$;

--
-- Name: audit_logs fk_audit_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'audit_logs'
                     AND con.conname = 'fk_audit_user') THEN
        ALTER TABLE ONLY public.audit_logs ADD CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;
    END IF;
END $$;

--
-- Name: screen_group_posts fk_group_post_group; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_group_posts'
                     AND con.conname = 'fk_group_post_group') THEN
        ALTER TABLE ONLY public.screen_group_posts ADD CONSTRAINT fk_group_post_group FOREIGN KEY (group_id) REFERENCES public.screen_groups(group_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: screen_group_posts fk_group_post_post; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'screen_group_posts'
                     AND con.conname = 'fk_group_post_post') THEN
        ALTER TABLE ONLY public.screen_group_posts ADD CONSTRAINT fk_group_post_post FOREIGN KEY (post_id) REFERENCES public.posts(post_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: layout_zones fk_layout_zones_layout; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'layout_zones'
                     AND con.conname = 'fk_layout_zones_layout') THEN
        ALTER TABLE ONLY public.layout_zones ADD CONSTRAINT fk_layout_zones_layout FOREIGN KEY (layout_id) REFERENCES public.layouts(layout_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: password_history fk_password_history_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'password_history'
                     AND con.conname = 'fk_password_history_user') THEN
        ALTER TABLE ONLY public.password_history ADD CONSTRAINT fk_password_history_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: post_configurations fk_post_config_layout; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'post_configurations'
                     AND con.conname = 'fk_post_config_layout') THEN
        ALTER TABLE ONLY public.post_configurations ADD CONSTRAINT fk_post_config_layout FOREIGN KEY (layout_id) REFERENCES public.layouts(layout_id) ON DELETE SET NULL;
    END IF;
END $$;

--
-- Name: post_configurations fk_post_config_post; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'post_configurations'
                     AND con.conname = 'fk_post_config_post') THEN
        ALTER TABLE ONLY public.post_configurations ADD CONSTRAINT fk_post_config_post FOREIGN KEY (post_id) REFERENCES public.posts(post_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: posts fk_posts_media; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'posts'
                     AND con.conname = 'fk_posts_media') THEN
        ALTER TABLE ONLY public.posts ADD CONSTRAINT fk_posts_media FOREIGN KEY (media_id) REFERENCES public.media(media_id);
    END IF;
END $$;

--
-- Name: posts fk_posts_site; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'posts'
                     AND con.conname = 'fk_posts_site') THEN
        ALTER TABLE ONLY public.posts ADD CONSTRAINT fk_posts_site FOREIGN KEY (site_id) REFERENCES public.sites(site_id) ON DELETE RESTRICT;
    END IF;
END $$;

--
-- Name: password_reset_tokens fk_reset_token_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'password_reset_tokens'
                     AND con.conname = 'fk_reset_token_user') THEN
        ALTER TABLE ONLY public.password_reset_tokens ADD CONSTRAINT fk_reset_token_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: schedules fk_schedule_post; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'schedules'
                     AND con.conname = 'fk_schedule_post') THEN
        ALTER TABLE ONLY public.schedules ADD CONSTRAINT fk_schedule_post FOREIGN KEY (post_id) REFERENCES public.posts(post_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: sync_items fk_sync_item_job; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sync_items'
                     AND con.conname = 'fk_sync_item_job') THEN
        ALTER TABLE ONLY public.sync_items ADD CONSTRAINT fk_sync_item_job FOREIGN KEY (sync_job_id) REFERENCES public.sync_jobs(sync_job_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: sync_items fk_sync_item_media; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sync_items'
                     AND con.conname = 'fk_sync_item_media') THEN
        ALTER TABLE ONLY public.sync_items ADD CONSTRAINT fk_sync_item_media FOREIGN KEY (media_id) REFERENCES public.media(media_id) ON DELETE SET NULL;
    END IF;
END $$;

--
-- Name: sync_jobs fk_sync_job_post; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'sync_jobs'
                     AND con.conname = 'fk_sync_job_post') THEN
        ALTER TABLE ONLY public.sync_jobs ADD CONSTRAINT fk_sync_job_post FOREIGN KEY (post_id) REFERENCES public.posts(post_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: user_permissions fk_user_permissions_permission; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_permissions'
                     AND con.conname = 'fk_user_permissions_permission') THEN
        ALTER TABLE ONLY public.user_permissions ADD CONSTRAINT fk_user_permissions_permission FOREIGN KEY (permission_id) REFERENCES public.permissions(permission_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: user_permissions fk_user_permissions_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_permissions'
                     AND con.conname = 'fk_user_permissions_user') THEN
        ALTER TABLE ONLY public.user_permissions ADD CONSTRAINT fk_user_permissions_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: user_zone_access fk_user_zone_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'user_zone_access'
                     AND con.conname = 'fk_user_zone_user') THEN
        ALTER TABLE ONLY public.user_zone_access ADD CONSTRAINT fk_user_zone_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- Name: users fk_users_profile; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'users'
                     AND con.conname = 'fk_users_profile') THEN
        ALTER TABLE ONLY public.users ADD CONSTRAINT fk_users_profile FOREIGN KEY (profile_id) REFERENCES public.profiles(profile_id);
    END IF;
END $$;

--
-- Name: zone_media fk_zone_media_media; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'zone_media'
                     AND con.conname = 'fk_zone_media_media') THEN
        ALTER TABLE ONLY public.zone_media ADD CONSTRAINT fk_zone_media_media FOREIGN KEY (media_id) REFERENCES public.media(media_id) ON DELETE RESTRICT;
    END IF;
END $$;

--
-- Name: zone_media fk_zone_media_post; Type: FK CONSTRAINT; Schema: public; Owner: -
--

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid = con.conrelid
                   JOIN pg_namespace n ON n.oid = rel.relnamespace
                   WHERE n.nspname = 'public' AND rel.relname = 'zone_media'
                     AND con.conname = 'fk_zone_media_post') THEN
        ALTER TABLE ONLY public.zone_media ADD CONSTRAINT fk_zone_media_post FOREIGN KEY (post_id) REFERENCES public.posts(post_id) ON DELETE CASCADE;
    END IF;
END $$;

--
-- PostgreSQL database dump complete
--


