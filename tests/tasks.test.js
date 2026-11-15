import { describe, expect, it } from 'vitest';
import { graphLayout, normalizeReminders, removeTask, taskState, validateTaskGraph, wouldCycle } from '../web/src/reminders.mjs';

const diamond = () => [
  { id: 'a', title: '收集资料', completed: true, dependsOn: [] },
  { id: 'b', title: '写初稿', completed: false, dependsOn: ['a'] },
  { id: 'c', title: '画图', completed: false, dependsOn: ['a'] },
  { id: 'd', title: '提交', completed: false, dependsOn: ['b', 'c'] },
];
describe('task dependencies', () => {
  it('migrates reminders without changing their delivery times', () => {
    const config = normalizeReminders({ items: [{ id: 'old', remindAt: '2026-11-01T09:00' }] });
    expect(config.lists).toEqual([]);
    expect(config.items[0]).toEqual({ id: 'old', listId: '', dependsOn: [], remindTimes: ['2026-11-01T09:00'] });
  });
  it('accepts branching and merging across lists and derives readiness', () => {
    const items = diamond(); items[0].listId = 'research'; items[3].listId = 'work';
    expect(() => validateTaskGraph({ lists: [{ id: 'research' }, { id: 'work' }], items })).not.toThrow();
    expect(taskState(items[1], items)).toBe('ready');
    expect(taskState(items[3], items)).toBe('blocked');
    items[1].completed = items[2].completed = true;
    expect(taskState(items[3], items)).toBe('ready');
    items[0].completed = false;
    expect(taskState(items[0], items)).toBe('ready');
  });
  it('rejects indirect cycles, disconnected cycles and dangling references', () => {
    const items = diamond();
    expect(wouldCycle(items, 'a', 'd')).toBe(true);
    items.push({ id: 'x', dependsOn: ['y'] }, { id: 'y', dependsOn: ['x'] });
    expect(() => validateTaskGraph({ items })).toThrow('循环');
    expect(() => validateTaskGraph({ items: [{ id: 'a', dependsOn: ['gone'] }] })).toThrow('不存在');
    expect(() => validateTaskGraph({ items: [{ id: 'a', listId: 'gone' }] })).toThrow('清单不存在');
  });
  it('removes all incoming references when deleting a task', () => {
    const config = removeTask({ lists: [], items: diamond() }, 'a');
    expect(config.items.map(x => x.dependsOn)).toEqual([[], [], ['b', 'c']]);
    expect(() => validateTaskGraph(config)).not.toThrow();
  });
  it('lays out joins after both parents and preserves ancestors in filtered graphs', () => {
    const layout = graphLayout(diamond(), new Set(['d']));
    expect(layout.nodes).toHaveLength(4);
    expect(layout.edges).toHaveLength(4);
    for (const edge of layout.edges) expect(edge.from.x).toBeLessThan(edge.to.x);
    expect(layout.nodes.filter(x => x.context).map(x => x.item.id)).toEqual(['a', 'b', 'c']);
  });
});
