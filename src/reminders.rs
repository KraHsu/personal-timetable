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
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TaskList {
    pub id: String,
    pub name: String,
}

fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 80
        && id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReminderConfig {
    pub course_enabled: bool,
    #[serde(default = "enabled")]
    pub first_course_enabled: bool,
    #[serde(default = "friday_time")]
    pub first_course_time: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub lists: Vec<TaskList>,
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
            lists: vec![],
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
    #[serde(default)]
    pub remind_times: Vec<String>,
    #[serde(default, skip_serializing)]
    pub remind_at: String,
    pub notes: String,
    pub enabled: bool,
    pub completed: bool,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub list_id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub depends_on: Vec<String>,
}
impl Item {
    fn normalize(&mut self) {
        if self.remind_times.is_empty() && !self.remind_at.is_empty() {
            self.remind_times.push(self.remind_at.clone());
        }
        self.remind_at.clear();
        self.remind_times.sort();
        self.remind_times.dedup();
    }
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
        if self.lists.len() > 50 {
            return Err("最多支持 50 个清单".into());
        }
        let mut list_ids = BTreeSet::new();
        for list in &mut self.lists {
            list.name = list.name.trim().into();
            if !valid_id(&list.id) || !list_ids.insert(list.id.clone()) {
                return Err("清单 ID 无效或重复".into());
            }
            if list.name.is_empty() || list.name.chars().count() > 60 {
                return Err("清单名称须为 1–60 个字符".into());
            }
        }
        let mut ids = BTreeSet::new();
        for i in &mut self.items {
            i.normalize();
            if !i.list_id.is_empty() && !list_ids.contains(&i.list_id) {
                return Err("任务所属清单不存在".into());
            }
            if i.remind_times.len() > 20 || (i.enabled && !i.completed && i.remind_times.is_empty())
            {
                return Err("启用提醒的待办事项须设置 1–20 个提醒时间".into());
            }
            i.title = i.title.trim().into();
            i.notes = i.notes.trim().into();
            if !valid_id(&i.id) || !ids.insert(i.id.clone()) {
                return Err("事项 ID 无效或重复".into());
            }
            if i.title.is_empty()
                || i.title.chars().count() > 120
                || i.notes.chars().count() > 2000
                || !["homework", "exam", "other"].contains(&i.kind.as_str())
            {
                return Err("请填写事项名称、有效类型，并检查文字长度".into());
            }
            for value in i
                .remind_times
                .iter()
                .chain((!i.due_at.is_empty()).then_some(&i.due_at))
            {
                let dt = NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M")
                    .map_err(|_| "请填写有效的日期和时间")?;
                if !(2000..=2100).contains(&dt.year())
                    || dt.format("%Y-%m-%dT%H:%M").to_string() != *value
                {
                    return Err("日期须在 2000–2100 年之间".into());
                }
            }
        }
        // Kahn's algorithm validates the whole graph, including disconnected components.
        let mut incoming = BTreeMap::new();
        let mut children: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for item in &self.items {
            let mut seen = BTreeSet::new();
            for parent in &item.depends_on {
                if parent == &item.id || !ids.contains(parent) || !seen.insert(parent) {
                    return Err("前置任务无效：不能引用自身、不存在或重复的任务".into());
                }
                children.entry(parent).or_default().push(&item.id);
            }
            incoming.insert(item.id.as_str(), item.depends_on.len());
        }
        let mut queue: VecDeque<&str> = incoming
            .iter()
            .filter_map(|(&id, &n)| (n == 0).then_some(id))
            .collect();
        let mut visited = 0;
        while let Some(id) = queue.pop_front() {
            visited += 1;
            for child in children.get(id).into_iter().flatten() {
                let n = incoming.get_mut(child).expect("Validated task reference");
                *n -= 1;
                if *n == 0 {
                    queue.push_back(child);
                }
            }
        }
        if visited != self.items.len() {
            return Err("任务依赖形成了循环，请移除一条依赖后重试".into());
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
        let mut data: ReminderConfig = serde_json::from_str(&raw).map_err(internal)?;
        for item in &mut data.items { item.normalize(); }
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
