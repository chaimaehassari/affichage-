-- 017: Gestion globale des utilisateurs
-- Association directe « User → Admin responsable » pour la gestion unifiée.
ALTER TABLE users
    ADD COLUMN admin_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;

CREATE INDEX idx_users_admin_id ON users(admin_id);