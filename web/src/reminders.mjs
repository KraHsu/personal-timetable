export function reminderTimes(item) {
  return [...new Set(item.remindTimes ?? (item.remindAt ? [item.remindAt] : []))].sort();
}
export function normalizeReminders(config) {
  return { ...config, lists: config.lists ?? [], items: config.items.map(item => {
    const { remindAt, ...rest } = item;
    return { ...rest, listId: item.listId ?? '', dependsOn: item.dependsOn ?? [], remindTimes: reminderTimes(item) };
  }) };
}

export function taskState(item, items) {
  if (item.completed) return 'completed';
  return (item.dependsOn ?? []).some(id => !items.find(x => x.id === id)?.completed) ? 'blocked' : 'ready';
}
export const taskStateLabels = { completed: '已完成', blocked: '等待前置', ready: '可开始' };

// A proposed prerequisite must not already depend on this task, even indirectly.
export function wouldCycle(items, taskId, prerequisiteId) {
  const byId = new Map(items.map(x => [x.id, x]));
  const pending = [prerequisiteId], seen = new Set();
  while (pending.length) {
    const id = pending.pop();
    if (id === taskId) return true;
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...(byId.get(id)?.dependsOn ?? []));
  }
  return false;
}

export function validateTaskGraph(config) {
  const ids = new Set(config.items.map(x => x.id));
  const lists = new Set((config.lists ?? []).map(x => x.id));
  const incoming = new Map(), children = new Map(config.items.map(x => [x.id, []]));
  if (ids.size !== config.items.length) throw new Error('任务 ID 重复');
  for (const item of config.items) {
    if (item.listId && !lists.has(item.listId)) throw new Error('任务所属清单不存在');
    const deps = item.dependsOn ?? [];
    if (new Set(deps).size !== deps.length || deps.some(id => !ids.has(id))) throw new Error('前置任务不存在或重复');
    incoming.set(item.id, deps.length);
    for (const id of deps) children.get(id).push(item.id);
  }
  const queue = [...incoming].filter(([, n]) => n === 0).map(([id]) => id);
  let visited = 0;
  while (queue.length) {
    visited++;
    for (const id of children.get(queue.pop())) {
      incoming.set(id, incoming.get(id) - 1);
      if (!incoming.get(id)) queue.push(id);
    }
  }
  if (visited !== config.items.length) throw new Error('任务依赖形成了循环，请移除一条依赖后重试');
}

export function removeTask(config, id) {
  return { ...config, items: config.items.filter(x => x.id !== id).map(x => ({ ...x, dependsOn: (x.dependsOn ?? []).filter(parent => parent !== id) })) };
}

// Include prerequisites in filtered views so no dependency is silently hidden.
export function graphLayout(items, visibleIds) {
  const byId = new Map(items.map(x => [x.id, x]));
  const included = new Set(visibleIds), pending = [...visibleIds];
  while (pending.length) {
    for (const id of byId.get(pending.pop())?.dependsOn ?? []) {
      if (byId.has(id) && !included.has(id)) { included.add(id); pending.push(id); }
    }
  }
  const depths = new Map(), visiting = new Set();
  function depth(id) {
    if (depths.has(id)) return depths.get(id);
    if (visiting.has(id)) throw new Error('任务依赖形成了循环');
    visiting.add(id);
    const parents = (byId.get(id)?.dependsOn ?? []).filter(x => included.has(x));
    const value = parents.length ? 1 + Math.max(...parents.map(depth)) : 0;
    visiting.delete(id); depths.set(id, value); return value;
  }
  const rows = new Map();
  const nodes = items.filter(x => included.has(x.id)).map(item => {
    const column = depth(item.id), row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    return { item, x: 24 + column * 280, y: 24 + row * 124, context: !visibleIds.has(item.id) };
  });
  const positions = new Map(nodes.map(x => [x.item.id, x]));
  const edges = nodes.flatMap(node => (node.item.dependsOn ?? []).filter(id => positions.has(id)).map(id => ({ from: positions.get(id), to: node })));
  return { nodes, edges, width: Math.max(560, ...nodes.map(x => x.x + 244)), height: Math.max(180, ...nodes.map(x => x.y + 116)) };
}
