use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::{
    fs,
    io::Write,
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};
use subtle::ConstantTimeEq;

#[derive(Clone, Serialize, Deserialize)]
pub struct Auth {
    pub salt: String,
    pub password_hash: String,
    pub key: String,
}

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn private_file(path: &Path, content: &[u8]) -> std::io::Result<()> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?
        .write_all(content)
}

impl Auth {
    pub fn load(data: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        fs::create_dir_all(data)?;
        fs::set_permissions(data, fs::Permissions::from_mode(0o700))?;
        let path = data.join("auth.json");
        if path.exists() {
            let auth: Self = serde_json::from_slice(&fs::read(path)?)?;
            if hex::decode(&auth.password_hash)?.len() != 32
                || auth.salt.is_empty()
                || auth.key.len() < 32
            {
                return Err("Invalid existing authentication data".into());
            }
            return Ok(auth);
        }
        let password = hex::encode(rand::random::<[u8; 18]>());
        let salt = hex::encode(rand::random::<[u8; 16]>());
        let mut hash = [0u8; 32];
        pbkdf2::pbkdf2_hmac::<Sha256>(password.as_bytes(), salt.as_bytes(), 600_000, &mut hash);
        let auth = Self {
            salt,
            password_hash: hex::encode(hash),
            key: hex::encode(rand::random::<[u8; 32]>()),
        };
        private_file(
            &data.join("admin-password.txt"),
            format!("{password}\n").as_bytes(),
        )?;
        private_file(&path, &serde_json::to_vec(&auth)?)?;
        Ok(auth)
    }
    pub fn password_matches(&self, password: &str) -> bool {
        let mut hash = [0u8; 32];
        // Preserve Python's legacy format: salt and HMAC key are ASCII hex strings.
        pbkdf2::pbkdf2_hmac::<Sha256>(
            password.as_bytes(),
            self.salt.as_bytes(),
            600_000,
            &mut hash,
        );
        hex::decode(&self.password_hash)
            .is_ok_and(|expected| bool::from(hash.as_slice().ct_eq(&expected)))
    }
    pub fn token(&self) -> String {
        let body = format!(
            "{}.{}",
            now() + 30 * 86400,
            hex::encode(rand::random::<[u8; 12]>())
        );
        let mut mac = Hmac::<Sha256>::new_from_slice(self.key.as_bytes())
            .expect("HMAC supports any key length");
        mac.update(body.as_bytes());
        format!("{body}.{}", hex::encode(mac.finalize().into_bytes()))
    }
    pub fn valid_token(&self, token: &str) -> bool {
        let Some((body, signature)) = token.rsplit_once('.') else {
            return false;
        };
        let Some((expires, nonce)) = body.split_once('.') else {
            return false;
        };
        if nonce.is_empty() || !expires.parse::<u64>().is_ok_and(|n| n > now()) {
            return false;
        }
        let Ok(signature) = hex::decode(signature) else {
            return false;
        };
        let mut mac = Hmac::<Sha256>::new_from_slice(self.key.as_bytes())
            .expect("HMAC supports any key length");
        mac.update(body.as_bytes());
        mac.verify_slice(&signature).is_ok()
    }
}
