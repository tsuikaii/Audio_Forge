'use strict';

const $ = id => document.getElementById(id);
const fields = ['title', 'artist', 'album', 'date'];
const supportedLanguages = ['en', 'zh-CN', 'ja'];
const desktopBridge = window.webkit?.messageHandlers?.desktop;
const nativeAction = (action, value='') => desktopBridge?.postMessage({action, value});
if (desktopBridge) document.body.classList.add('native-client');
let translations = {};
let locale = 'en';
let token = new URLSearchParams(location.search).get('token') || '';
try {
  token ||= sessionStorage.getItem('audio-forge-token') || '';
  if (token) sessionStorage.setItem('audio-forge-token', token);
  const preference = localStorage.getItem('audio-forge-language');
  if (supportedLanguages.includes(preference)) locale = preference;
} catch (_) { /* Storage may be disabled in private browsing. */ }
if (location.protocol !== 'file:') history.replaceState(null, '', location.pathname);

let state = {input:'', output:'', source_format:'', target_format:'m4a', mode:'convert', cover:'', cover_action:'keep', has_cover:false, original_artwork:'', artwork:''};
let busy = false, picking = false, stopped = false, timer = null;
let picker = {kind:'input', directory:'', parent:'', selected:'', error:null, request:0};
let statusModel = {key:'ready', detailKey:'ready_detail', type:''};
let overwriteResolver = null;
let activePage = 'conversion';
const replaceExtension = (path, format) => path.replace(/\.(mp4|mp3|flac|m4a)$/i, '') + '.' + format;
const tr = (key, values={}) => {
  const text = translations[locale]?.[key] ?? translations.en?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`);
};
const errorText = error => error.key ? tr(error.key, error.values) : error.message;

class ApiError extends Error {
  constructor(body) {
    super(body.error || 'Operation failed.');
    this.key = body.error_key;
    this.values = body.error_values || {};
  }
}

async function api(path, data) {
  const response = await fetch('/api/' + path, {
    method:data === undefined ? 'GET' : 'POST',
    headers:{'X-M4A-Token':token, 'X-Audio-Language':locale, 'Content-Type':'application/json'},
    body:data === undefined ? undefined : JSON.stringify(data)
  });
  const body = await response.json();
  if (!response.ok && !body.needs_overwrite) throw new ApiError(body);
  return body;
}

function controls() {
  const disconnected = location.protocol === 'file:' || stopped;
  $('editor').disabled = busy || picking || !state.input || disconnected;
  $('chooseInput').disabled = busy || picking || disconnected;
  $('start').disabled = busy || picking || !state.input || disconnected;
  $('quit').disabled = busy || picking || disconnected;
  $('language').disabled = location.protocol === 'file:';
  $('reveal').disabled = busy || picking || stopped;
  document.querySelectorAll('[data-command]').forEach(button => {
    button.disabled = $(button.dataset.command).matches(':disabled');
  });
  $('taskButton').setAttribute('aria-pressed', String(!$('appWindow').hidden));
}

function renderStatus() {
  $('statusTitle').textContent = tr(statusModel.key, statusModel.values);
  $('statusDetail').textContent = statusModel.error ? errorText(statusModel.error) : statusModel.detailKey ? tr(statusModel.detailKey, statusModel.values) : statusModel.detail || '';
  $('footer').className = 'status-panel ' + (statusModel.type || '');
  $('activity').hidden = statusModel.type !== 'running';
}
function setStatus(key, options={}) {
  statusModel = {key, ...options};
  renderStatus();
}

function updateArtwork() {
  const replace = state.cover_action === 'replace';
  const removed = state.cover_action === 'remove';
  $('coverName').textContent = replace ? state.cover.split('/').pop() : tr(removed ? 'artwork_removed' : state.has_cover ? 'artwork_original' : 'no_artwork');
  const image = removed ? '' : replace ? state.artwork : state.original_artwork;
  $('artworkImage').hidden = !image;
  $('artworkPlaceholder').hidden = !!image;
  if (image) $('artworkImage').src = image;
  else $('artworkImage').removeAttribute('src');
  $('restoreCover').hidden = state.cover_action === 'keep';
}

function updateFormat() {
  const target = state.target_format;
  state.mode = state.source_format === target ? 'edit' : 'convert';
  document.querySelectorAll('[data-format]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.format === target)));
  $('mode').textContent = !state.input ? '—' : state.mode === 'edit' ? tr('edit_mode', {format:target.toUpperCase()}) : state.source_format.toUpperCase() + ' → ' + target.toUpperCase();
  $('startLabel').textContent = !state.input ? tr('begin') : tr(state.mode === 'edit' ? 'save_tags' : 'convert_to', {format:target.toUpperCase()});
  $('encoding').hidden = !!state.input && (state.mode === 'edit' || target === 'flac');
  $('codecGroup').hidden = target === 'mp3';
  $('bitrateGroup').hidden = target === 'flac' || (target !== 'mp3' && $('codec').value === 'alac');
  $('useOriginal').hidden = !state.input || state.mode !== 'edit' || state.input === state.output;
  $('formatHint').textContent = tr(!state.input ? 'format_empty' : state.mode === 'edit' ? 'hint_edit' : 'hint_' + target);
  $('outputPath').textContent = state.output || tr('output_empty');
}

function render() {
  document.documentElement.lang = locale;
  $('language').value = locale;
  document.querySelectorAll('[data-i18n]').forEach(element => element.textContent = tr(element.dataset.i18n));
  document.querySelectorAll('[data-i18n-placeholder]').forEach(element => element.placeholder = tr(element.dataset.i18nPlaceholder));
  document.querySelectorAll('[data-i18n-aria]').forEach(element => element.setAttribute('aria-label', tr(element.dataset.i18nAria)));
  if (state.input) {
    $('fileName').textContent = state.input.split('/').pop();
    $('fileName').title = state.input;
    $('fileInfo').textContent = state.description;
    $('inputPath').textContent = state.input;
  }
  $('windowTitle').textContent = 'Audio Forge' + (state.input ? ' - ' + state.input.split('/').pop() : '');
  document.title = $('windowTitle').textContent;
  $('maximize').setAttribute('aria-label', tr($('appWindow').classList.contains('maximized') || $('appWindow').classList.contains('native-maximized') ? 'restore_window' : 'maximize'));
  updateArtwork(); updateFormat(); renderStatus(); renderPickerLabels(); controls();
}

function setLanguage(value) {
  locale = supportedLanguages.includes(value) ? value : 'en';
  try { localStorage.setItem('audio-forge-language', locale); } catch (_) {}
  render();
  nativeAction('language', locale);
}

window.audioForgeOpenFile = async path => {
  if (busy || picking || stopped) { setStatus('selection_failed', {error:new ApiError({error_key:'err_busy'}), type:'error'}); return; }
  try { applySelection('input', await api('select', {kind:'input', path})); }
  catch (error) { setStatus('selection_failed', {error, type:'error'}); }
};

window.audioForgeWindowState = maximized => {
  $('appWindow').classList.toggle('native-maximized', maximized);
  $('maximize').setAttribute('aria-label', tr(maximized ? 'restore_window' : 'maximize'));
};

function applySelection(kind, result) {
  if (kind === 'input') {
    const seconds = Math.round(result.duration);
    const duration = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    state = {input:result.path, output:result.output, source_format:result.source_format, target_format:result.target_format, mode:result.mode, cover:'', cover_action:'keep', has_cover:result.has_cover, original_artwork:result.artwork_data || '', artwork:'', description:result.codec.toUpperCase() + ' / ' + duration};
    fields.forEach(key => $('tag-' + key).value = result.tags[key] || '');
    $('codec').value = 'auto'; $('reveal').hidden = true;
  } else if (kind === 'cover') {
    state.cover = result.path; state.cover_action = 'replace'; state.artwork = result.artwork_data || '';
  } else state.output = result.path;
  setStatus('file_ready', {detailKey:state.mode === 'edit' && state.input === state.output ? 'inplace_detail' : 'file_ready_detail'});
  render();
}

function renderPickerLabels() {
  $('pickerTitle').textContent = tr(picker.kind === 'input' ? 'picker_input' : picker.kind === 'cover' ? 'picker_cover' : 'picker_output', {format:state.target_format.toUpperCase()});
  $('pickerConfirm').textContent = tr(picker.kind === 'output' ? 'use_location' : 'select_this');
  $('pickerError').textContent = picker.error ? errorText(picker.error) : '';
}

async function loadFolder(directory) {
  const request = ++picker.request;
  picker.error = null; renderPickerLabels();
  const loading = document.createElement('p'); loading.className = 'folder-empty'; loading.dataset.i18n = 'loading'; loading.textContent = tr('loading');
  $('fileList').replaceChildren(loading); $('pickerConfirm').disabled = true;
  try {
    const result = await api('files', {kind:picker.kind, directory, target_format:state.target_format});
    if (request !== picker.request || !picking) return;
    picker.directory = result.directory; picker.parent = result.parent; picker.selected = '';
    $('pickerPath').value = result.directory; $('fileList').replaceChildren(); $('shortcuts').replaceChildren();
    for (const [key, path] of Object.entries(result.shortcuts)) {
      const button = document.createElement('button'); button.dataset.i18n = key; button.textContent = tr(key); button.className = 'secondary small';
      button.onclick = () => loadFolder(path); $('shortcuts').append(button);
    }
    if (!result.entries.length) {
      const empty = document.createElement('p'); empty.className = 'folder-empty'; empty.dataset.i18n = 'folder_empty'; empty.textContent = tr('folder_empty'); $('fileList').append(empty);
    }
    for (const entry of result.entries) {
      const button = document.createElement('button'); const icon = document.createElement('span'); const name = document.createElement('span');
      icon.className = 'file-icon ' + (entry.is_dir ? 'folder' : 'audio'); icon.setAttribute('aria-hidden', 'true');
      name.textContent = entry.name; button.append(icon, name);
      button.onclick = () => {
        if (entry.is_dir) { loadFolder(entry.path); return; }
        picker.selected = entry.path;
        $('fileList').querySelectorAll('.selected').forEach(element => element.classList.remove('selected'));
        button.classList.add('selected');
        if (picker.kind === 'output') $('saveName').value = entry.name;
        $('pickerConfirm').disabled = false;
      };
      button.ondblclick = () => { if (!entry.is_dir && picker.kind !== 'output') { picker.selected = entry.path; confirmPicker(); } };
      $('fileList').append(button);
    }
    $('pickerConfirm').disabled = picker.kind !== 'output';
  } catch (error) {
    if (request !== picker.request || !picking) return;
    $('fileList').replaceChildren(); picker.error = error; renderPickerLabels();
  }
}

function closePicker() {
  ++picker.request; picking = false; $('pickerModal').close(); controls();
}
async function browse(kind) {
  picking = true; controls(); picker.kind = kind; picker.selected = ''; picker.error = null;
  renderPickerLabels(); $('saveNameGroup').hidden = kind !== 'output';
  $('saveName').value = replaceExtension((state.output || state.input || 'audio.m4a').split('/').pop(), state.target_format);
  $('pickerModal').showModal();
  const reference = kind === 'output' ? state.output : state.input;
  await loadFolder(reference ? reference.slice(0, reference.lastIndexOf('/')) : '');
}
async function confirmPicker() {
  if ($('pickerConfirm').disabled) return;
  $('pickerConfirm').disabled = true; picker.error = null; renderPickerLabels();
  try {
    let result;
    if (picker.kind === 'output') {
      let name = $('saveName').value.trim();
      if (!name || name.includes('/') || name === '.' || name === '..') throw new ApiError({error_key:'invalid_filename'});
      name = replaceExtension(name, state.target_format);
      result = {path:picker.directory + '/' + name};
    } else result = await api('select', {kind:picker.kind, path:picker.selected});
    if (!picking) return;
    applySelection(picker.kind, result); closePicker();
  } catch (error) { picker.error = error; renderPickerLabels(); $('pickerConfirm').disabled = false; }
}

function askOverwrite(path) {
  $('overwritePath').textContent = path; $('overwriteModal').showModal();
  return new Promise(resolve => overwriteResolver = resolve);
}
function finishOverwrite(accepted) {
  $('overwriteModal').close();
  overwriteResolver?.(accepted); overwriteResolver = null;
}

async function poll() {
  try {
    const result = await api('status');
    if (result.state === 'running') { setStatus('running', {detailKey:'running_detail', type:'running'}); timer = setTimeout(poll, 650); return; }
    timer = null; busy = false; controls();
    const error = result.error ? new ApiError({error_key:result.error.key, error_values:result.error.values}) : null;
    setStatus(result.message_key, {detail:result.output, error, type:result.state === 'done' ? 'success' : 'error'});
    $('reveal').hidden = result.state !== 'done';
  } catch (error) { timer = null; busy = false; controls(); setStatus('connection_lost', {error, type:'error'}); }
}
async function startJob() {
  const tags = {}; fields.forEach(key => tags[key] = $('tag-' + key).value);
  const payload = {...state, tags, language:locale, codec:$('codec').value, bitrate:$('bitrate').value};
  busy = true; controls(); $('reveal').hidden = true; setStatus('preparing', {type:'running'});
  try {
    let result = await api('start', payload);
    if (result.needs_overwrite) {
      if (!await askOverwrite(result.path)) { busy = false; controls(); setStatus('cancelled', {detailKey:'cancelled_detail'}); return; }
      result = await api('start', {...payload, overwrite:true});
    }
    if (!result.started) throw new ApiError({error_key:'err_request'});
    setStatus('running', {detailKey:'running_detail', type:'running'}); timer = setTimeout(poll, 650);
  } catch (error) { busy = false; controls(); setStatus('job_failed', {error, type:'error'}); }
}

$('language').onchange = () => setLanguage($('language').value);
$('chooseInput').onclick = () => browse('input');
$('chooseCover').onclick = () => browse('cover');
$('chooseOutput').onclick = () => browse('output');
$('pickerConfirm').onclick = confirmPicker;
$('pickerClose').onclick = $('pickerCancel').onclick = closePicker;
$('pickerModal').addEventListener('cancel', event => { event.preventDefault(); closePicker(); });
$('parentFolder').onclick = () => loadFolder(picker.parent);
$('goFolder').onclick = () => loadFolder($('pickerPath').value);
$('pickerPath').onkeydown = event => { if (event.key === 'Enter') loadFolder($('pickerPath').value); };
$('overwriteConfirm').onclick = () => finishOverwrite(true);
$('overwriteCancel').onclick = () => finishOverwrite(false);
$('overwriteModal').addEventListener('cancel', event => { event.preventDefault(); finishOverwrite(false); });
$('removeCover').onclick = () => { state.cover_action = 'remove'; state.cover = ''; state.artwork = ''; updateArtwork(); };
$('restoreCover').onclick = () => { state.cover_action = 'keep'; state.cover = ''; state.artwork = ''; updateArtwork(); };
$('useOriginal').onclick = () => { state.output = state.input; updateFormat(); setStatus('file_ready', {detailKey:'inplace_detail'}); };
$('clearTags').onclick = () => { fields.forEach(key => $('tag-' + key).value = ''); setStatus('fields_cleared', {detailKey:'fields_cleared_detail'}); };
$('codec').onchange = updateFormat;
document.querySelectorAll('[data-format]').forEach(button => button.onclick = () => {
  state.target_format = button.dataset.format; state.output = replaceExtension(state.output, state.target_format);
  updateFormat(); $('reveal').hidden = true; setStatus('format_changed', {detailKey:'format_changed_detail', values:{format:state.target_format.toUpperCase()}});
});
$('start').onclick = startJob;
$('reveal').onclick = () => api('reveal', {}).catch(error => setStatus('reveal_failed', {error, type:'error'}));
$('quit').onclick = async () => {
  if (desktopBridge) { nativeAction('quit'); return; }
  try {
    await api('quit', {}); stopped = true; $('reveal').hidden = true; controls(); setStatus('exited', {detailKey:'exited_detail'});
  } catch (error) { setStatus('quit_failed', {error, type:'error'}); }
};
window.addEventListener('beforeunload', event => { if (busy) { event.preventDefault(); event.returnValue = ''; } });

// Property pages and desktop window controls retain the same unsaved form state.
function showPage(page, focus=false) {
  activePage = page;
  document.querySelectorAll('[data-page]').forEach(button => {
    const selected = button.dataset.page === page;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $('page-' + button.dataset.page).hidden = !selected;
    if (selected && focus) button.focus();
  });
}
function closeMenus() { document.querySelectorAll('.menu[open]').forEach(menu => menu.open = false); }
document.querySelectorAll('[data-page]').forEach(button => {
  button.onclick = () => showPage(button.dataset.page);
  button.onkeydown = event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      showPage(event.key === 'Home' ? 'conversion' : event.key === 'End' ? 'metadata' : activePage === 'conversion' ? 'metadata' : 'conversion', true);
    }
  };
});
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => { closeMenus(); showPage(button.dataset.tab, true); });
document.querySelectorAll('[data-command]').forEach(button => button.onclick = () => { closeMenus(); $(button.dataset.command).click(); });
document.querySelectorAll('.menu').forEach(menu => menu.addEventListener('toggle', () => {
  if (menu.open) document.querySelectorAll('.menu').forEach(other => { if (other !== menu) other.open = false; });
}));
document.addEventListener('click', event => { if (!event.target.closest('.menu')) closeMenus(); });
document.querySelectorAll('[data-about]').forEach(button => button.onclick = () => { closeMenus(); $('aboutModal').showModal(); });
$('aboutClose').onclick = $('aboutOK').onclick = () => $('aboutModal').close();
function minimizeWindow() {
  if (desktopBridge) { nativeAction('minimize'); return; }
  $('appWindow').hidden = true; controls(); $('taskButton').focus();
}
$('minimize').onclick = minimizeWindow;
$('taskButton').onclick = () => {
  if (!$('appWindow').hidden) { minimizeWindow(); return; }
  $('appWindow').hidden = false; controls(); $('minimize').focus();
};
$('maximize').onclick = () => {
  if (desktopBridge) { nativeAction('maximize'); return; }
  const maximized = $('appWindow').classList.toggle('maximized');
  $('maximize').setAttribute('aria-label', tr(maximized ? 'restore_window' : 'maximize'));
};
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeMenus();
  if (document.querySelector('dialog[open]')) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'o') {
    event.preventDefault(); $('chooseInput').click();
  } else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault(); $('start').click();
  }
});

async function initialize() {
  if (location.protocol === 'file:') {
    controls(); $('statusTitle').textContent = 'Open the app to continue'; $('statusDetail').textContent = 'Double-click Audio Forge.app. This HTML file is a view-only page.'; return;
  }
  try {
    const response = await fetch('locales.json', {headers:{'X-M4A-Token':token}});
    if (!response.ok) throw new Error('Open Audio Forge.app to start a new session.');
    translations = await response.json(); render(); nativeAction('language', locale);
  } catch (error) {
    stopped = true; controls(); $('statusTitle').textContent = 'Could not start the interface'; $('statusDetail').textContent = error.message;
  }
}
initialize();
