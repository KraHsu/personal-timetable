import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import App from '../web/src/App.vue';
const fixture = () => ({ settings: { title: '测试学期', startDate: '2026-09-21', totalWeeks: 20, timezone: 'Asia/Shanghai', dayStart: '08:00', dayEnd: '20:00' }, courses: [{ id: 'one', name: '<img src=x onerror=alert(1)>', location: 'A201', teacher: '老师', notes: 'https://example.com 备忘', color: 'blue', sessions: [{ day: 1, start: '08:00', end: '09:35', weeks: '1-20', location: '线上' }] }, { id: 'pending', name: '待定课程', location: '', teacher: '', notes: '', color: 'green', sessions: [] }] });
let wrapper, saved, authenticated, revision, reminders, reminderRevision;
function button(text) { return wrapper.findAll('button').find(x => x.text() === text); }
async function start(auth = false) { authenticated = auth; wrapper = mount(App, { attachTo: document.body }); await flushPromises(); }
beforeEach(() => {
  saved = fixture(); authenticated = false; revision = 3; reminders = { courseEnabled: true, firstCourseEnabled: true, firstCourseTime: '18:00', items: [] }; reminderRevision = 1;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  vi.stubGlobal('confirm', vi.fn(() => true));
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    if (url === '/api/reminders') {
      if (options.method === 'PUT') { const payload = JSON.parse(options.body); expect(payload.revision).toBe(reminderRevision); reminders = payload.data; reminderRevision++; }
      return { ok: true, json: async () => ({ data: structuredClone(reminders), revision: reminderRevision, lastDelivery: null }) };
    }
    if (url === '/api/login') { authenticated = true; return { ok: true, json: async () => ({ ok: true }) }; }
    if (url === '/api/logout') { authenticated = false; return { ok: true, json: async () => ({ ok: true }) }; }
    if (options.method === 'PUT') { const payload = JSON.parse(options.body); expect(payload.revision).toBe(revision); saved = payload.data; revision++; }
    return { ok: true, json: async () => ({ data: structuredClone(saved), revision, authenticated }) };
  }));
});
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.unstubAllGlobals(); });
describe('Vue timetable', () => {
  it('logs in, configures course alerts and manages arbitrary homework reminders', async () => {
    await start();
    await wrapper.find('#reminders-button').trigger('click');
    expect(wrapper.find('#login-form').exists()).toBe(true);
    await wrapper.find('input[type=password]').setValue('secret');
    await wrapper.find('#login-form').trigger('submit'); await flushPromises();
    expect(wrapper.find('dialog').attributes('aria-label')).toBe('事项与提醒');
    await wrapper.find('#course-reminders').setValue(false); await flushPromises();
    expect(reminders.courseEnabled).toBe(false);
    await wrapper.find('#first-course-time').setValue('17:30'); await flushPromises();
    expect(reminders.firstCourseTime).toBe('17:30');
    await wrapper.find('#first-course-reminders').setValue(false); await flushPromises();
    expect(reminders.firstCourseEnabled).toBe(false);
    await wrapper.find('#add-reminder').trigger('click');
    await wrapper.find('[name=title]').setValue('期中考试');
    await wrapper.find('[name=kind]').setValue('exam');
    await wrapper.find('[name=dueAt]').setValue('2026-11-10T09:00');
    await wrapper.find('[name=remindAt]').setValue('2026-11-08T20:15');
    await wrapper.find('[name=notes]').setValue('带计算器');
    await wrapper.find('#reminder-form').trigger('submit'); await flushPromises();
    expect(reminders.items[0]).toMatchObject({ title: '期中考试', kind: 'exam', remindAt: '2026-11-08T20:15', dueAt: '2026-11-10T09:00', enabled: true });
    expect(wrapper.text()).toContain('带计算器');
    await button('完成').trigger('click'); await flushPromises();
    expect(reminders.items[0].completed).toBe(true);
    await button('恢复待办').trigger('click'); await flushPromises();
    expect(reminders.items[0].completed).toBe(false);
    await button('删除').trigger('click'); await flushPromises();
    expect(reminders.items).toEqual([]);
  });
  it('keeps reminder drafts when another device changes the configuration', async () => {
    await start(true); await wrapper.find('#reminders-button').trigger('click'); await flushPromises();
    await wrapper.find('#add-reminder').trigger('click');
    await wrapper.find('[name=title]').setValue('保留提醒草稿');
    await wrapper.find('[name=remindAt]').setValue('2026-11-01T12:15');
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ error: '另一台设备已更新事项' }) })));
    await wrapper.find('#reminder-form').trigger('submit'); await flushPromises();
    expect(wrapper.find('[name=title]').element.value).toBe('保留提醒草稿');
    expect(wrapper.find('[role=alert]').text()).toContain('另一台设备');
  });
  it('opens the map without login, zooms it and returns to the course details', async () => {
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback) { this.callback = callback; }
      observe(element) {
        Object.defineProperties(element, { clientWidth: { value: 600 }, clientHeight: { value: 400 } });
        this.callback();
      }
      disconnect() {}
    });
    await start();
    expect(wrapper.find('.map-viewport').exists()).toBe(false);
    await wrapper.find('#map-button').trigger('click');
    expect(wrapper.find('dialog').attributes('aria-label')).toBe('校园地图');
    expect(wrapper.find('#login-form').exists()).toBe(false);
    expect(wrapper.find('.map-tools a').attributes('href')).toMatch(/campus-map\.pdf$/);
    const width = parseFloat(wrapper.find('.map-stage img').element.style.width);
    await wrapper.find('[aria-label="放大地图"]').trigger('click');
    expect(parseFloat(wrapper.find('.map-stage img').element.style.width)).toBeCloseTo(width * 1.5);
    await button('全图').trigger('click');
    expect(parseFloat(wrapper.find('.map-stage img').element.style.width)).toBeCloseTo(width);
    await wrapper.find('[aria-label="关闭地图"]').trigger('click');
    expect(wrapper.find('dialog').exists()).toBe(false);
    await wrapper.find('.course-index-item').trigger('click');
    await button('查看校园地图').trigger('click');
    await wrapper.find('dialog').trigger('cancel');
    expect(wrapper.find('dialog').attributes('aria-label')).toBe('课程详情');
    expect(wrapper.find('dialog').text()).toContain('A201');
    expect(authenticated).toBe(false);
    expect(saved).toEqual(fixture());
  });
  it('renders escaped course names, pending courses and location overrides in both views', async () => {
    await start();
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>');
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.text()).toContain('时间待定');
    expect(wrapper.find('.course-block').text()).toContain('线上');
    await button('日程').trigger('click');
    expect(wrapper.find('.agenda-item').text()).toContain('线上');
    await wrapper.find('.agenda-item').trigger('click');
    expect(wrapper.find('dialog').text()).toContain('线上');
    expect(wrapper.find('dialog a').attributes('href')).toBe('https://example.com');
  });
  it('requires password then saves a reactive editor with odd weeks and separate location', async () => {
    await start();
    await wrapper.find('#add-course').trigger('click');
    expect(wrapper.find('#login-form').exists()).toBe(true);
    await wrapper.find('input[type=password]').setValue('secret');
    await wrapper.find('#login-form').trigger('submit'); await flushPromises();
    await wrapper.find('input[name=name]').setValue('新课');
    await button('单周').trigger('click');
    const inputs = wrapper.findAll('.session input');
    await inputs[2].setValue('另一间教室');
    await wrapper.find('#course-form').trigger('submit'); await flushPromises();
    expect(saved.courses.at(-1).sessions[0]).toMatchObject({ weeks: '1-20单', location: '另一间教室' });
    expect(wrapper.find('dialog').exists()).toBe(false);
    expect(wrapper.text()).toContain('新课');
  });
  it('keeps the editor and unsaved content when another device changed the revision', async () => {
    await start(true); await wrapper.find('#add-course').trigger('click');
    await wrapper.find('input[name=name]').setValue('保留草稿');
    const originalFetch = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn((url, options) => options?.method === 'PUT' ? Promise.resolve({ ok: false, status: 409, json: async () => ({ error: '另一台设备已更新课表' }) }) : originalFetch(url, options)));
    await wrapper.find('#course-form').trigger('submit'); await flushPromises();
    expect(wrapper.find('input[name=name]').element.value).toBe('保留草稿');
    expect(wrapper.find('[role=alert]').text()).toContain('另一台设备');
    expect(saved.courses).toHaveLength(2);
  });
  it('saves a pending course without fabricated sessions and deletes it', async () => {
    await start(true); await wrapper.find('#add-course').trigger('click');
    await wrapper.find('input[name=name]').setValue('未排课'); await button('移除').trigger('click');
    await wrapper.find('#course-form').trigger('submit'); await flushPromises();
    expect(saved.courses.at(-1).sessions).toEqual([]);
    await wrapper.findAll('.course-index-item').at(-1).trigger('click'); await button('编辑课程').trigger('click');
    await button('删除课程').trigger('click'); await flushPromises();
    expect(saved.courses).toHaveLength(2);
  });
  it('validates semester dates, changes weeks and keeps preview read only', async () => {
    await start(true); await wrapper.find('#settings-button').trigger('click');
    await wrapper.find('input[type=date]').setValue('2026-09-22');
    await wrapper.find('#settings-form').trigger('submit'); await flushPromises();
    expect(wrapper.find('[role=alert]').text()).toContain('周一');
    await wrapper.find('input[type=date]').setValue('2026-09-28');
    await wrapper.find('#settings-form').trigger('submit'); await flushPromises();
    expect(saved.settings.startDate).toBe('2026-09-28');
    await wrapper.find('[aria-label="选择周次"]').trigger('click'); await button('第 3 周').trigger('click');
    expect(wrapper.find('.week-title').text()).toContain('03');
    await wrapper.find('#preview-button').trigger('click'); await wrapper.find('#add-course').trigger('click');
    expect(wrapper.find('dialog').exists()).toBe(false); expect(wrapper.text()).toContain('先返回我的课表');
    await wrapper.find('#preview-button').trigger('click'); await flushPromises();
    expect(saved.courses).toEqual(fixture().courses);
  });
});
