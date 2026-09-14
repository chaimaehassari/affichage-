-- Adds sync_profile_id to sync_jobs for auto-scheduled (deferred) sync jobs.
-- Value comes from the global setting sync_auto_profile_id (FTP profile used
-- for automatic scheduled synchronization).

ALTER TABLE sync_jobs ADD COLUMN IF NOT EXISTS sync_profile_id INTEGER REFERENCES ftp_profiles(ftp_profile_id);

COMMENT ON COLUMN sync_jobs.sync_profile_id IS 'Profil FTP à utiliser pour la synchro, issu du réglage sync_auto_profile_id';