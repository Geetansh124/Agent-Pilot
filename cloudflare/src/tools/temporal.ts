/**
 * Live Date and Time Grounding Tool
 */

export function getCurrentDateTime(timezoneName: string = 'UTC'): Record<string, any> {
  const now = new Date();
  const tz = timezoneName.trim() || 'UTC';

  let localizedDate = '';
  let localizedTime = '';
  let dayOfWeek = '';
  let year = now.getUTCFullYear();

  try {
    const formatterDate = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const formatterTime = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    const formatterWeekday = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      weekday: 'long',
    });
    const formatterYear = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      year: 'numeric',
    });

    localizedDate = formatterDate.format(now);
    localizedTime = formatterTime.format(now);
    dayOfWeek = formatterWeekday.format(now);
    year = parseInt(formatterYear.format(now), 10);
  } catch {
    localizedDate = now.toISOString().split('T')[0];
    localizedTime = now.toISOString().split('T')[1].slice(0, 8);
    dayOfWeek = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][now.getUTCDay()];
  }

  return {
    utc_iso: now.toISOString(),
    date: localizedDate,
    time: localizedTime,
    day_of_week: dayOfWeek,
    year,
    timezone: tz,
    timestamp_ms: now.getTime(),
  };
}
