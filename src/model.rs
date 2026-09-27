use chrono::{Datelike, NaiveDate, Weekday};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    pub title: String,
    pub start_date: String,
    pub total_weeks: u32,
    pub timezone: String,
    pub day_start: String,
    pub day_end: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Session {
    pub day: u32,
    pub start: String,
    pub end: String,
    pub weeks: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub location: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Course {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub location: String,
    #[serde(default)]
    pub teacher: String,
    #[serde(default)]
    pub notes: String,
    pub color: String,
    pub sessions: Vec<Session>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Schedule {
    pub settings: Settings,
    pub courses: Vec<Course>,
}

fn text(value: &mut String, max: usize, required: bool) -> Result<(), String> {
    if value.chars().count() > max || (required && value.trim().is_empty()) {
        return Err("必填信息为空或文字过长".into());
    }
    *value = value.trim().to_owned();
    Ok(())
}

fn valid_time(value: &str) -> bool {
    let b = value.as_bytes();
    b.len() == 5
        && b[2] == b':'
        && [b[0], b[1], b[3], b[4]].iter().all(u8::is_ascii_digit)
        && value[..2].parse::<u32>().unwrap_or(99) < 24
        && value[3..].parse::<u32>().unwrap_or(99) < 60
}

pub fn weeks(value: &str, total: u32) -> Result<BTreeSet<u32>, String> {
    let error = || "周次格式应为 1-16、1-16单、2-16双 或 1-8,10-16，且不能超过学期周数".to_string();
    if value.chars().count() > 250 {
        return Err(error());
    }
    let normalized: String = value
        .chars()
        .filter(|c| !c.is_whitespace() && *c != '周')
        .map(|c| if c == '，' || c == '、' { ',' } else { c })
        .collect();
    let mut found = BTreeSet::new();
    for token in normalized.split(',') {
        let (range, parity) = if let Some(v) = token.strip_suffix('单') {
            (v, Some(1))
        } else if let Some(v) = token.strip_suffix('双') {
            (v, Some(0))
        } else {
            (token, None)
        };
        let parts: Vec<_> = range.split('-').collect();
        if parts.is_empty()
            || parts.len() > 2
            || parts
                .iter()
                .any(|s| s.is_empty() || !s.bytes().all(|c| c.is_ascii_digit()))
        {
            return Err(error());
        }
        let start = parts[0].parse::<u32>().map_err(|_| error())?;
        let end = parts.last().unwrap().parse::<u32>().map_err(|_| error())?;
        if start < 1 || end < start || end > total {
            return Err(error());
        }
        found.extend((start..=end).filter(|w| parity.is_none_or(|p| w % 2 == p)));
    }
    if found.is_empty() {
        return Err(error());
    }
    Ok(found)
}

impl Schedule {
    pub fn validate(mut self) -> Result<Self, String> {
        let s = &mut self.settings;
        text(&mut s.title, 80, true)?;
        if !(1..=60).contains(&s.total_weeks) {
            return Err("学期周数须在 1–60 之间".into());
        }
        let start =
            NaiveDate::parse_from_str(&s.start_date, "%Y-%m-%d").map_err(|_| "学期日期无效")?;
        if s.start_date != start.format("%Y-%m-%d").to_string()
            || !(2000..=2100).contains(&start.year())
            || start.weekday() != Weekday::Mon
        {
            return Err("学期起始日期须为 2000–2100 年之间的周一".into());
        }
        if ![
            "Asia/Shanghai",
            "America/Los_Angeles",
            "Europe/London",
            "Asia/Tokyo",
            "UTC",
        ]
        .contains(&s.timezone.as_str())
        {
            return Err("请选择支持的课表时区".into());
        }
        if !valid_time(&s.day_start) || !valid_time(&s.day_end) || s.day_start >= s.day_end {
            return Err("课表起止时间无效".into());
        }
        if self.courses.len() > 200 {
            return Err("最多支持 200 门课程".into());
        }
        let mut ids = BTreeSet::new();
        for c in &mut self.courses {
            text(&mut c.id, 80, true)?;
            if !c
                .id
                .bytes()
                .all(|x| x.is_ascii_alphanumeric() || x == b'_' || x == b'-')
                || !ids.insert(c.id.clone())
            {
                return Err("课程 ID 无效或重复".into());
            }
            text(&mut c.name, 80, true)?;
            text(&mut c.location, 120, false)?;
            text(&mut c.teacher, 80, false)?;
            text(&mut c.notes, 2000, false)?;
            if !["green", "blue", "mauve", "peach", "rose"].contains(&c.color.as_str()) {
                return Err("课程标记颜色无效".into());
            }
            if c.sessions.len() > 30 {
                return Err("每门课最多支持 30 个时段".into());
            }
            for session in &mut c.sessions {
                if !(1..=7).contains(&session.day)
                    || !valid_time(&session.start)
                    || !valid_time(&session.end)
                    || session.start >= session.end
                {
                    return Err("上课星期或起止时间无效".into());
                }
                weeks(&session.weeks, s.total_weeks)?;
                session.weeks = session.weeks.trim().to_owned();
                if let Some(location) = &mut session.location {
                    text(location, 120, false)?;
                }
            }
        }
        Ok(self)
    }

    pub fn empty() -> Self {
        let today = chrono::Utc::now().date_naive();
        let monday = today - chrono::Duration::days(today.weekday().num_days_from_monday().into());
        Self {
            settings: Settings {
                title: "我的学期".into(),
                start_date: monday.to_string(),
                total_weeks: 20,
                timezone: "Asia/Shanghai".into(),
                day_start: "08:00".into(),
                day_end: "20:00".into(),
            },
            courses: vec![],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn week_ranges_match_existing_format() {
        assert_eq!(
            weeks("1-8单，10，12-16双", 20)
                .unwrap()
                .into_iter()
                .collect::<Vec<_>>(),
            vec![1, 3, 5, 7, 10, 12, 14, 16]
        );
        for bad in ["0", "5-2", "1-21", "1,,2", "2单", "1-3x"] {
            assert!(weeks(bad, 20).is_err());
        }
    }
    #[test]
    fn validation_supports_pending_and_location_overrides() {
        let mut data = Schedule::empty();
        data.courses.push(Course {
            id: "a".into(),
            name: "待定课".into(),
            location: "教室".into(),
            teacher: "".into(),
            notes: "".into(),
            color: "blue".into(),
            sessions: vec![],
        });
        assert!(data.clone().validate().is_ok());
        data.courses[0].sessions.push(Session {
            day: 1,
            start: "08:00".into(),
            end: "09:35".into(),
            weeks: "1-2".into(),
            location: Some("线上".into()),
        });
        assert!(data.clone().validate().is_ok());
        data.courses[0].sessions[0].end = "07:00".into();
        assert!(data.validate().is_err());
    }
}
