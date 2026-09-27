mod auth;
mod model;

use auth::{Auth, now};
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Request, State, rejection::JsonRejection},
    http::{HeaderMap, HeaderValue, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use model::Schedule;
use rusqlite::{Connection, TransactionBehavior, params};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::Duration,
};
use tower_http::services::ServeDir;

#[derive(Clone)]
struct AppState {
    db: Arc<Mutex<Connection>>,
    auth: Auth,
    attempts: Arc<Mutex<HashMap<String, Vec<u64>>>>,
    origin: String,
    secure: bool,
    revision: String,
}

struct ApiError(StatusCode, String);
impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error": self.1}))).into_response()
    }
}
type ApiResult = Result<Response, ApiError>;
fn internal(error: impl std::fmt::Display) -> ApiError {
    eprintln!("Server error: {error}");
    ApiError(
        StatusCode::INTERNAL_SERVER_ERROR,
        "服务暂时不可用，请稍后重试".into(),
    )
}
fn body<T>(value: Result<Json<T>, JsonRejection>) -> Result<T, ApiError> {
    value
        .map(|Json(v)| v)
        .map_err(|e| ApiError(e.status(), "请求格式无效或超出大小限制".into()))
}

impl AppState {
    fn new(
        data: PathBuf,
        origin: String,
        revision: String,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let auth = Auth::load(&data)?;
        let db = Connection::open(data.join("schedule.sqlite3"))?;
        db.busy_timeout(Duration::from_secs(10))?;
        db.execute_batch("PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, saved_at TEXT DEFAULT CURRENT_TIMESTAMP, body TEXT NOT NULL);")?;
        db.execute(
            "INSERT OR IGNORE INTO schedule VALUES (1, 1, ?1)",
            [serde_json::to_string(&Schedule::empty())?],
        )?;
        Ok(Self {
            db: Arc::new(Mutex::new(db)),
            auth,
            attempts: Arc::new(Mutex::new(HashMap::new())),
            secure: origin.starts_with("https://"),
            origin: origin.trim_end_matches('/').to_owned(),
            revision,
        })
    }
    fn cookie_name(&self) -> &str {
        if self.secure {
            "__Host-timetable"
        } else {
            "timetable_session"
        }
    }
    fn authenticated(&self, headers: &HeaderMap) -> bool {
        headers
            .get("cookie")
            .and_then(|v| v.to_str().ok())
            .is_some_and(|cookies| {
                cookies
                    .split(';')
                    .filter_map(|s| s.trim().split_once('='))
                    .any(|(name, token)| name == self.cookie_name() && self.auth.valid_token(token))
            })
    }
    fn cookie(&self, token: &str, age: u64) -> HeaderValue {
        HeaderValue::from_str(&format!(
            "{}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{}",
            self.cookie_name(),
            if self.secure { "; Secure" } else { "" }
        ))
        .expect("Generated ASCII cookie")
    }
}

async fn guard(State(state): State<AppState>, req: Request, next: Next) -> Response {
    let api = req.uri().path().starts_with("/api/");
    let mut blocked = None;
    if api && !["GET", "HEAD", "OPTIONS"].contains(&req.method().as_str()) {
        let origin_ok = req
            .headers()
            .get("origin")
            .is_none_or(|v| v.to_str().is_ok_and(|v| v == state.origin));
        let cross_site = req
            .headers()
            .get("sec-fetch-site")
            .is_some_and(|v| v == "cross-site");
        if !origin_ok || cross_site {
            blocked = Some(ApiError(StatusCode::FORBIDDEN, "请求来源无效".into()));
        }
    }
    let mut response = if let Some(error) = blocked {
        error.into_response()
    } else {
        next.run(req).await
    };
    for (name, value) in [
        ("x-content-type-options", "nosniff"),
        ("referrer-policy", "same-origin"),
        ("x-frame-options", "DENY"),
        ("cache-control", if api { "no-store" } else { "no-cache" }),
        (
            "content-security-policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        ),
    ] {
        response
            .headers_mut()
            .insert(name, HeaderValue::from_static(value));
    }
    response
}

async fn read_schedule(State(state): State<AppState>, headers: HeaderMap) -> ApiResult {
    let authenticated = state.authenticated(&headers);
    let result = tokio::task::spawn_blocking(move || -> Result<Value, String> {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let (revision, raw): (i64, String) = db
            .query_row("SELECT revision, body FROM schedule WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .map_err(|e| e.to_string())?;
        let data: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
        Ok(json!({"data":data,"revision":revision,"authenticated":authenticated}))
    })
    .await
    .map_err(internal)?
    .map_err(internal)?;
    Ok(Json(result).into_response())
}

#[derive(Deserialize)]
struct SaveRequest {
    data: Schedule,
    revision: i64,
}
async fn save_schedule(
    State(state): State<AppState>,
    headers: HeaderMap,
    input: Result<Json<SaveRequest>, JsonRejection>,
) -> ApiResult {
    if !state.authenticated(&headers) {
        return Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "编辑登录已过期，请重新进入编辑".into(),
        ));
    }
    let input = body(input)?;
    let clean = input
        .data
        .validate()
        .map_err(|e| ApiError(StatusCode::BAD_REQUEST, e))?;
    tokio::task::spawn_blocking(move || -> ApiResult {
        let mut db = state.db.lock().map_err(internal)?;
        let tx = db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(internal)?;
        let (revision, old): (i64, String) = tx
            .query_row("SELECT revision, body FROM schedule WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .map_err(internal)?;
        if input.revision != revision {
            return Err(ApiError(
                StatusCode::CONFLICT,
                "另一台设备已更新课表。请先复制未保存的内容，再刷新页面后编辑。".into(),
            ));
        }
        tx.execute(
            "INSERT INTO history (revision,body) VALUES (?1,?2)",
            params![revision, old],
        )
        .map_err(internal)?;
        tx.execute(
            "UPDATE schedule SET revision=?1,body=?2 WHERE id=1",
            params![
                revision + 1,
                serde_json::to_string(&clean).map_err(internal)?
            ],
        )
        .map_err(internal)?;
        tx.execute("DELETE FROM history WHERE revision < ?1", [revision - 49])
            .map_err(internal)?;
        tx.commit().map_err(internal)?;
        Ok(Json(json!({"data":clean,"revision":revision+1})).into_response())
    })
    .await
    .map_err(internal)?
}

#[derive(Deserialize)]
struct Login {
    password: String,
}
async fn login(
    State(state): State<AppState>,
    headers: HeaderMap,
    input: Result<Json<Login>, JsonRejection>,
) -> ApiResult {
    let input = body(input)?;
    if input.password.chars().count() > 256 {
        return Err(ApiError(StatusCode::BAD_REQUEST, "密码格式无效".into()));
    }
    let ip = headers
        .get("x-real-ip")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("local")
        .to_owned();
    {
        let mut map = state.attempts.lock().map_err(internal)?;
        let cutoff = now().saturating_sub(900);
        map.retain(|_, values| {
            values.retain(|v| *v > cutoff);
            !values.is_empty()
        });
        let attempts = map.entry(ip.clone()).or_default();
        if attempts.len() >= 10 {
            return Err(ApiError(
                StatusCode::TOO_MANY_REQUESTS,
                "尝试次数过多，请 15 分钟后重试".into(),
            ));
        }
        attempts.push(now());
    }
    let auth = state.auth.clone();
    let valid = tokio::task::spawn_blocking(move || auth.password_matches(&input.password))
        .await
        .map_err(internal)?;
    if !valid {
        return Err(ApiError(StatusCode::UNAUTHORIZED, "密码不正确".into()));
    }
    state.attempts.lock().map_err(internal)?.remove(&ip);
    let mut response = Json(json!({"ok":true})).into_response();
    response
        .headers_mut()
        .insert("set-cookie", state.cookie(&state.auth.token(), 30 * 86400));
    Ok(response)
}
async fn logout(
    State(state): State<AppState>,
    input: Result<Json<Value>, JsonRejection>,
) -> ApiResult {
    body(input)?;
    let mut response = Json(json!({"ok":true})).into_response();
    response
        .headers_mut()
        .insert("set-cookie", state.cookie("", 0));
    Ok(response)
}
async fn health(State(state): State<AppState>) -> Json<Value> {
    Json(json!({"ok":true,"revision":state.revision,"backend":"rust"}))
}

fn app(state: AppState, public: PathBuf) -> Router {
    Router::new()
        .route("/api/schedule", get(read_schedule).put(save_schedule))
        .route("/api/login", post(login))
        .route("/api/logout", post(logout))
        .route("/healthz", get(health))
        .fallback_service(ServeDir::new(public))
        .layer(DefaultBodyLimit::max(512_000))
        .layer(middleware::from_fn_with_state(state.clone(), guard))
        .with_state(state)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut port = 8765u16;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--port" {
            port = args.next().ok_or("Missing port")?.parse()?;
        } else {
            return Err(format!("Unknown argument: {arg}").into());
        }
    }
    let exe = std::env::current_exe()?.canonicalize()?;
    let root = exe.parent().ok_or("Missing executable parent")?;
    let data = PathBuf::from(std::env::var("TIMETABLE_DATA").unwrap_or_else(|_| "data".into()));
    let public = std::env::var_os("TIMETABLE_PUBLIC")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join("public"));
    let revision = std::env::var("TIMETABLE_REVISION").unwrap_or_else(|_| {
        std::fs::read_to_string(root.join("REVISION"))
            .unwrap_or_else(|_| "local".into())
            .trim()
            .to_owned()
    });
    let origin =
        std::env::var("TIMETABLE_ORIGIN").unwrap_or_else(|_| format!("http://127.0.0.1:{port}"));
    let state = AppState::new(data, origin, revision)?;
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await?;
    println!("Rust timetable listening on {}", listener.local_addr()?);
    axum::serve(listener, app(state, public))
        .with_graceful_shutdown(async {
            let mut terminate =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                    .expect("Install SIGTERM handler");
            tokio::select! {
                _ = tokio::signal::ctrl_c() => {},
                _ = terminate.recv() => {},
            }
        })
        .await?;
    Ok(())
}
