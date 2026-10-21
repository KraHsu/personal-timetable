export function reminderTimes(item) {
  return [...new Set(item.remindTimes ?? (item.remindAt ? [item.remindAt] : []))].sort();
}
export function normalizeReminders(config) {
  return { ...config, items: config.items.map(item => {
    const { remindAt, ...rest } = item;
    return { ...rest, remindTimes: reminderTimes(item) };
  }) };
}
