import { createClient } from '@supabase/supabase-js';
import './style.css';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const days = [
  { id: 1, short: 'Пн', name: 'Понедельник' },
  { id: 2, short: 'Вт', name: 'Вторник' },
  { id: 3, short: 'Ср', name: 'Среда' },
  { id: 4, short: 'Чт', name: 'Четверг' },
  { id: 5, short: 'Пт', name: 'Пятница' },
  { id: 6, short: 'Сб', name: 'Суббота' },
  { id: 7, short: 'Вс', name: 'Воскресенье' },
];

const groupSelect = document.querySelector('#group-select');
const dayTabs = document.querySelector('#day-tabs');
const chatWindow = document.querySelector('#chat-window');
const commandForm = document.querySelector('#command-form');
const commandInput = document.querySelector('#command-input');

let selectedGroup = null;
let selectedDay = new Date().getDay() || 7;

function formatTime(value) {
  return value ? String(value).slice(0, 5) : '--:--';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function addMessage(content, type = 'bot') {
  const message = document.createElement('article');
  message.className = `message ${type}`;
  message.innerHTML = content;
  chatWindow.append(message);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function renderDays() {
  dayTabs.innerHTML = days.map((day) => `
    <button class="day-tab ${day.id === selectedDay ? 'active' : ''}" data-day="${day.id}" type="button">
      <span>${day.short}</span>
      <small>${day.id === (new Date().getDay() || 7) ? 'сегодня' : ''}</small>
    </button>
  `).join('');
  dayTabs.querySelectorAll('[data-day]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedDay = Number(button.dataset.day);
      renderDays();
      showSchedule(selectedDay);
    });
  });
}

async function loadGroups() {
  const { data, error } = await supabase.from('groups').select('id, name').order('name');
  if (error) throw error;
  groupSelect.innerHTML = '<option value="">Выберите группу</option>';
  data.forEach((group) => {
    const option = document.createElement('option');
    option.value = group.id;
    option.textContent = group.name;
    groupSelect.append(option);
  });
}

async function getLessons(day) {
  const { data, error } = await supabase
    .from('schedule')
    .select('lesson_number, subject_name, time_start, time_end')
    .eq('group_id', selectedGroup.id)
    .eq('day_of_week', day)
    .order('lesson_number');
  if (error) throw error;
  return data || [];
}

function lessonMarkup(lesson) {
  return `<div class="lesson-row">
    <span class="lesson-number">${escapeHtml(lesson.lesson_number)}</span>
    <div class="lesson-main">
      <strong>${escapeHtml(lesson.subject_name || 'Без названия')}</strong>
      <span>${formatTime(lesson.time_start)} — ${formatTime(lesson.time_end)}</span>
    </div>
  </div>`;
}

async function showSchedule(day = selectedDay) {
  if (!selectedGroup) {
    addMessage('Сначала выбери группу в списке выше.');
    return;
  }
  const dayInfo = days.find((item) => item.id === day);
  addMessage(`<span class="message-label">/today</span><b>${escapeHtml(selectedGroup.name)}</b><br>${dayInfo.name}`, 'user');
  try {
    const lessons = await getLessons(day);
    if (!lessons.length) {
      addMessage(`<b>${dayInfo.name}</b><p>Занятий нет. Можно выдохнуть.</p>`);
      return;
    }
    addMessage(`<b>${dayInfo.name}</b><div class="lessons-list">${lessons.map(lessonMarkup).join('')}</div>`);
  } catch (error) {
    addMessage(`<b>Не удалось загрузить расписание.</b><p>${escapeHtml(error.message)}</p>`);
  }
}

async function showNow() {
  if (!selectedGroup) {
    addMessage('Сначала выбери группу в списке выше.');
    return;
  }
  addMessage('<span class="message-label">/now</span>', 'user');
  const lessons = await getLessons(new Date().getDay() || 7);
  const current = new Date();
  const currentMinutes = current.getHours() * 60 + current.getMinutes();
  const active = lessons.find((lesson) => {
    const start = formatTime(lesson.time_start).split(':').map(Number);
    const end = formatTime(lesson.time_end).split(':').map(Number);
    const startMinutes = start[0] * 60 + start[1];
    const endMinutes = end[0] * 60 + end[1];
    return currentMinutes >= startMinutes && currentMinutes <= endMinutes;
  });
  const next = lessons.find((lesson) => {
    const start = formatTime(lesson.time_start).split(':').map(Number);
    return currentMinutes < start[0] * 60 + start[1];
  });
  if (active) {
    addMessage(`<b>Сейчас идет ${active.lesson_number} пара</b><p>${escapeHtml(active.subject_name)}<br>${formatTime(active.time_start)} — ${formatTime(active.time_end)}</p>`);
  } else if (next) {
    addMessage(`<b>Сейчас перемена</b><p>Следующая пара: ${escapeHtml(next.subject_name)}<br>Начало в ${formatTime(next.time_start)}</p>`);
  } else {
    addMessage('<b>На сегодня все пары закончились.</b>');
  }
}

groupSelect.addEventListener('change', async () => {
  const { data, error } = await supabase.from('groups').select('id, name').eq('id', groupSelect.value).single();
  if (error) {
    addMessage(`Не удалось выбрать группу: ${escapeHtml(error.message)}`);
    return;
  }
  selectedGroup = data;
  chatWindow.innerHTML = '';
  addMessage(`<b>${escapeHtml(data.name)}</b><p>Группа выбрана. Нажми день недели или введи команду.</p>`);
  showSchedule(selectedDay);
});

document.querySelectorAll('[data-command]').forEach((button) => {
  button.addEventListener('click', () => button.dataset.command === 'today' ? showSchedule() : showNow());
});

commandForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const command = commandInput.value.trim().toLowerCase();
  commandInput.value = '';
  if (command === '/today') showSchedule();
  else if (command === '/now') showNow();
  else if (command) addMessage('Доступные команды: <b>/today</b> и <b>/now</b>.');
});

renderDays();
loadGroups().catch((error) => {
  groupSelect.innerHTML = '<option value="">Ошибка подключения</option>';
  addMessage(`<b>Ошибка подключения к Supabase.</b><p>${escapeHtml(error.message)}</p>`);
});