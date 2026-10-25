//! Preset-based schedule evaluation (daily / weekly / monthly at fixed local
//! times, timezone-aware). Misfire policy is skip: at most one catch-up run.

use chrono::{DateTime, Datelike, Duration, TimeZone, Utc};
use chrono_tz::Tz;

use crate::models::Schedule;

pub fn parse_timezone(name: &str) -> Tz {
    name.parse().unwrap_or(chrono_tz::Asia::Seoul)
}

fn parse_hhmm(value: &str) -> Option<(u32, u32)> {
    let mut parts = value.trim().split(':');
    let hour: u32 = parts.next()?.parse().ok()?;
    let minute: u32 = parts.next()?.parse().ok()?;
    if parts.next().is_some() || hour > 23 || minute > 59 {
        return None;
    }
    Some((hour, minute))
}

/// Earliest occurrence strictly after `after` (UTC), or None when the
/// schedule can never fire (no valid times / no weekdays).
pub fn next_occurrence(schedule: &Schedule, after: DateTime<Utc>) -> Option<DateTime<Utc>> {
    let tz = parse_timezone(&schedule.timezone);
    let times: Vec<(u32, u32)> = schedule.times.iter().filter_map(|t| parse_hhmm(t)).collect();
    if times.is_empty() {
        return None;
    }
    let weekdays: Vec<u8> = match schedule.kind {
        crate::models::ScheduleKind::Weekly => {
            let days: Vec<u8> = schedule.days_of_week.iter().copied().filter(|d| (1..=7).contains(d)).collect();
            if days.is_empty() {
                return None;
            }
            days
        }
        _ => Vec::new(),
    };
    let mut day = after.with_timezone(&tz).date_naive() - Duration::days(1);
    for _ in 0..366 + 31 {
        let include_day = match schedule.kind {
            crate::models::ScheduleKind::Daily => true,
            crate::models::ScheduleKind::Weekly => {
                let iso = day.weekday().number_from_monday() as u8;
                weekdays.contains(&iso)
            }
            crate::models::ScheduleKind::Monthly => {
                let wanted = schedule.day_of_month.unwrap_or(1) as u32;
                let last = last_day_of_month(day.year(), day.month());
                day.day() == wanted.min(last)
            }
        };
        if include_day {
            let mut candidates: Vec<DateTime<Utc>> = times
                .iter()
                .filter_map(|(h, m)| {
                    let naive = day.and_hms_opt(*h, *m, 0)?;
                    tz.from_local_datetime(&naive).single()
                })
                .map(|local| local.with_timezone(&Utc))
                .filter(|moment| *moment > after)
                .collect();
            candidates.sort();
            if let Some(earliest) = candidates.first() {
                return Some(*earliest);
            }
        }
        day += Duration::days(1);
    }
    None
}

fn last_day_of_month(year: i32, month: u32) -> u32 {
    let next = if month == 12 {
        chrono::NaiveDate::from_ymd_opt(year + 1, 1, 1)
    } else {
        chrono::NaiveDate::from_ymd_opt(year, month + 1, 1)
    };
    next.map(|d| d - Duration::days(1))
        .map(|d| d.day())
        .unwrap_or(31)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{ScheduleKind, Schedule as S};

    fn base() -> S {
        S { timezone: "Asia/Seoul".into(), ..Default::default() }
    }

    #[test]
    fn daily_next_run_same_or_next_day() {
        // 2026-10-25 is a Sunday. 10:00 KST == 01:00 UTC.
        let after = DateTime::parse_from_rfc3339("2026-10-25T00:00:00Z").unwrap().with_timezone(&Utc);
        let schedule = S { kind: ScheduleKind::Daily, times: vec!["10:00".into()], ..base() };
        let next = next_occurrence(&schedule, after).unwrap();
        assert_eq!(next.to_rfc3339(), "2026-10-25T01:00:00+00:00");

        let after2 = DateTime::parse_from_rfc3339("2026-10-25T02:00:00Z").unwrap().with_timezone(&Utc);
        let next2 = next_occurrence(&schedule, after2).unwrap();
        assert_eq!(next2.to_rfc3339(), "2026-10-26T01:00:00+00:00");
    }

    #[test]
    fn weekly_respects_weekdays() {
        let schedule = S {
            kind: ScheduleKind::Weekly,
            times: vec!["09:00".into()],
            days_of_week: vec![1, 5], // Mon, Fri
            ..base()
        };
        // 2026-10-25 is Sunday; next Mon is 10-26.
        let after = DateTime::parse_from_rfc3339("2026-10-25T00:00:00Z").unwrap().with_timezone(&Utc);
        let next = next_occurrence(&schedule, after).unwrap();
        assert_eq!(next.to_rfc3339(), "2026-10-26T00:00:00+00:00"); // 09:00 KST
    }

    #[test]
    fn monthly_clamps_short_months() {
        let schedule = S {
            kind: ScheduleKind::Monthly,
            times: vec!["09:00".into()],
            day_of_month: Some(31),
            ..base()
        };
        // From Nov 1: Nov has 30 days → fires Nov 30.
        let after = DateTime::parse_from_rfc3339("2026-11-01T00:00:00Z").unwrap().with_timezone(&Utc);
        let next = next_occurrence(&schedule, after).unwrap();
        assert!(next.to_rfc3339().starts_with("2026-11-30"));
    }

    #[test]
    fn invalid_time_entries_are_ignored() {
        let schedule = S { kind: ScheduleKind::Daily, times: vec!["25:00".into(), "08:30".into()], ..base() };
        let after = DateTime::parse_from_rfc3339("2026-10-25T00:00:00Z").unwrap().with_timezone(&Utc);
        let next = next_occurrence(&schedule, after).unwrap();
        assert!(next.to_rfc3339().contains("T23:30:00")); // 08:30 KST == 23:30 UTC prev day
    }

    #[test]
    fn no_valid_times_yields_none() {
        let schedule = S { kind: ScheduleKind::Daily, times: vec!["bad".into()], ..base() };
        let after = Utc::now();
        assert!(next_occurrence(&schedule, after).is_none());
    }
}
