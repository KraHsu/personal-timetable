use crate::{ApiError, ApiResult, AppState, body, internal};
use axum::{
    Json,
    extract::{State, rejection::JsonRejection},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
};
use chrono::{Datelike, NaiveDateTime};
use rusqlite::params;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::BTreeSet;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReminderConfig {
    pub course_enabled: bool,
    #[serde(default = "enabled")]
    pub first_course_enabled: bool,
    #[serde(default = "friday_time")]
    pub first_course_time: String,
    pub items: Vec<Item>,
}
fn enabled() -> bool {
    true
}
fn friday_time() -> String {
    "18:00".into()
}
impl Default for ReminderConfig {
    fn default() -> Self {
        Self {
            course_enabled: true,
            first_course_enabled: true,
            first_course_time: friday_time(),
            items: vec![],
        }
    }
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Item {
    pub id: String,
    pub title: String,
    pub kind: String,
    pub due_at: String,
    pub remind_at: String,
    pub notes: String,
    pub enabled: bool,
    pub completed: bool,
}
impl ReminderConfig {
    fn validate(mut self) -> Result<Self, String> {
        if !chrono::NaiveTime::parse_from_str(&self.first_course_time, "%H:%M")
            .is_ok_and(|t| t.format("%H:%M").to_string() == self.first_course_time)
        {
            return Err("请填写有效的周五提醒时间".into());
        }
        if self.items.len() > 300 {
            return Err("最多支持 300 个事项".into());
        }
        let mut ids = BTreeSet::new();
        for i in &mut self.items {
            i.title = i.title.trim().into();
            i.notes = i.notes.trim().into();
            if i.id.is_empty()
                || i.id.len() > 80
                || !i
                    .id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
                || !ids.insert(i.id.clone())
            {
                return Err("事项 ID 无效或重复".into());
            }
            if i.title.is_empty()
                || i.title.chars().count() > 120
                || i.notes.chars().count() > 2000
                || !["homework", "exam", "other"].contains(&i.kind.as_str())
            {
                return Err("请填写事项名称、有效类型，并检查文字长度".into());
            }
            for (value, required) in [
                (&i.due_at, false),
                (&i.remind_at, i.enabled && !i.completed),
            ] {
                if value.is_empty() && !required {
                    continue;
                }
                let dt = NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M")
                    .map_err(|_| "请填写有效的日期和时间")?;
                if !(2000..=2100).contains(&dt.year())
                    || dt.format("%Y-%m-%dT%H:%M").to_string() != *value
                {
                    return Err("日期须在 2000–2100 年之间".into());
                }
            }
        }
        Ok(self)
    }
}
#[derive(Deserialize)]
pub struct SaveReminders {
    data: ReminderConfig,
    revision: i64,
}

pub async fn read(State(state): State<AppState>, headers: HeaderMap) -> ApiResult {
    if !state.authenticated(&headers) {
        return Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "请先登录编辑以管理事项与提醒".into(),
        ));
    }
    tokio::task::spawn_blocking(move || {
        let db = state.db.lock().map_err(internal)?;
        let (revision, raw): (i64, String) = db.query_row("SELECT revision,body FROM reminders WHERE id=1", [], |r| Ok((r.get(0)?,r.get(1)?))).map_err(internal)?;
        let data: ReminderConfig = serde_json::from_str(&raw).map_err(internal)?;
        let last: Option<(String, String)> = db.query_row("SELECT sent_at,title FROM notification_deliveries WHERE status='sent' ORDER BY sent_at DESC LIMIT 1", [], |r| Ok((r.get(0)?, r.get(1)?))).optional().map_err(internal)?;
        Ok(Json(json!({"data":data,"revision":revision,"lastDelivery":last.map(|(at,title)|json!({"at":at,"title":title}))})).into_response())
    }).await.map_err(internal)?
}
use rusqlite::OptionalExtension;
pub async fn save(
    State(state): State<AppState>,
    headers: HeaderMap,
    input: Result<Json<SaveReminders>, JsonRejection>,
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
    tokio::task::spawn_blocking(move || {
        let db = state.db.lock().map_err(internal)?;
        let n = db
            .execute(
                "UPDATE reminders SET revision=revision+1,body=?1 WHERE id=1 AND revision=?2",
                params![
                    serde_json::to_string(&clean).map_err(internal)?,
                    input.revision
                ],
            )
            .map_err(internal)?;
        if n == 0 {
            return Err(ApiError(
                StatusCode::CONFLICT,
                "另一台设备已更新事项，请重新打开后编辑；当前草稿仍保留在这里。".into(),
            ));
        }
        Ok(Json(json!({"data":clean,"revision":input.revision+1})).into_response())
    })
    .await
    .map_err(internal)?
}
