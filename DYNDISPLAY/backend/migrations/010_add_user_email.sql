-- Adds an email column to users for password-reset delivery (Forgot Password / reset link).

ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users(email);

COMMENT ON COLUMN users.email IS 'Adresse e-mail de l''utilisateur (réception des e-mails de réinitialisation du mot de passe)';