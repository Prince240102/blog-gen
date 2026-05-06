/**
 * BlogForge — Studio App (Agentic)
 *
 * A ReAct agent decides which tools to call based on conversation.
 * SSE events: token, tool_start, tool_end, blog_content, done.
 */

const API = '/api';

let token = localStorage.getItem('token');
let currentSessionId = localStorage.getItem('last-session-id');
let isStreaming = false;
let hasContent = false;
let currentVersions = [];
let activeVersion = null;

if (!token) window.location.href = '/';
function authHeaders() {
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// ---- DOM ----
const chatMessages    = document.getElementById('chat-messages');
const chatForm        = document.getElementById('chat-form');
const chatInput       = document.getElementById('chat-input');
const sendBtn         = document.getElementById('send-btn');
const topbarTitle     = document.getElementById('topbar-title');
const sessionsList    = document.getElementById('sessions-list');
const sidebar         = document.getElementById('sidebar');
const sidebarToggle   = document.getElementById('sidebar-toggle');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
const newChatBtn      = document.getElementById('new-chat-btn');
const logoutBtn       = document.getElementById('logout-btn');
const statusLine      = document.getElementById('status-line');
const streamMeter     = document.getElementById('stream-meter');
const attachBtn       = document.getElementById('attach-btn');
const fileInput       = document.getElementById('file-input');
const fileChips       = document.getElementById('file-chips');
const themeToggle     = document.getElementById('theme-toggle');

// ---- Theme ----
(function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
})();
if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
    });
}

// ---- Helpers ----
const isMobile = () => window.innerWidth <= 768;

function renderMarkdown(t) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
        return marked.parse(t);
    }
    return t.replace(/\n/g, '<br>');
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function updatePlaceholder() {
    chatInput.placeholder = hasContent
        ? 'Ask for changes, say "publish", or ask me anything…'
        : 'Describe your blog topic, or ask me anything…';
}

function handleAuthFail() {
    localStorage.removeItem('token');
    localStorage.removeItem('last-session-id');
    window.location.href = '/';
}

// ---- Sidebar ----
const shell = document.querySelector('.app-shell');

function syncShell() {
    if (sidebar.classList.contains('collapsed')) shell.classList.add('sidebar-hidden');
    else shell.classList.remove('sidebar-hidden');
}

function openSidebar() {
    sidebar.classList.remove('collapsed');
    syncShell();
    if (isMobile()) sidebarBackdrop.classList.add('visible');
    if (!isMobile()) localStorage.setItem('sidebar-collapsed', 'false');
}
function closeSidebar() {
    sidebar.classList.add('collapsed');
    syncShell();
    sidebarBackdrop.classList.remove('visible');
    if (!isMobile()) localStorage.setItem('sidebar-collapsed', 'true');
}
sidebarToggle.addEventListener('click', () =>
    sidebar.classList.contains('collapsed') ? openSidebar() : closeSidebar());
sidebarBackdrop.addEventListener('click', closeSidebar);

if (isMobile()) sidebar.classList.add('collapsed');
else if (localStorage.getItem('sidebar-collapsed') === 'true') sidebar.classList.add('collapsed');
syncShell();

let wasMobile = isMobile();
window.addEventListener('resize', () => {
    const now = isMobile();
    if (now && !wasMobile) closeSidebar();
    else if (!now && wasMobile) {
        sidebarBackdrop.classList.remove('visible');
        if (localStorage.getItem('sidebar-collapsed') !== 'true') sidebar.classList.remove('collapsed');
        syncShell();
    }
    wasMobile = now;
});

// ---- Textarea ----
const composer = document.getElementById('composer');
function toggleComposerExpand() {
    const val = chatInput.value;
    const expanded = val.length > 80 || val.includes('\n');
    composer.classList.toggle('expanded', expanded);
    sendBtn.classList.toggle('visible', val.trim().length > 0);
}
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    toggleComposerExpand();
});
chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

// ---- Logout / New ----
logoutBtn.addEventListener('click', handleAuthFail);
newChatBtn.addEventListener('click', () => {
    currentSessionId = null; hasContent = false;
    currentVersions = [];
    activeVersion = null;
    localStorage.removeItem('last-session-id');
    chatMessages.innerHTML = '';
    chatMessages.appendChild(createWelcome());
    topbarTitle.textContent = 'New Session';
    loadSessions(); resetPipeline(); updatePlaceholder();
    if (isMobile()) closeSidebar();
});

// ---- Quick prompts ----
document.addEventListener('click', e => {
    const btn = e.target.closest('.quick-btn');
    if (btn) { chatInput.value = btn.dataset.prompt; chatForm.dispatchEvent(new Event('submit')); }
});

// ---- Sessions ----
async function loadSessions() {
    try {
        const r = await fetch(`${API}/sessions`, { headers: authHeaders() });
        if (r.status === 401) { handleAuthFail(); return; }
        renderSessions(await r.json());
    } catch {}
}

function renderSessions(sessions) {
    sessionsList.innerHTML = '';
    sessions.forEach(s => {
        const div = document.createElement('div');
        div.className = 'session-item' + (s.session_id === currentSessionId ? ' active' : '');
        const lastUser = [...s.messages].reverse().find(m => m.role === 'user');
        const title = lastUser ? lastUser.content.slice(0, 50) : 'Empty session';
        const date = s.created_at ? new Date(s.created_at).toLocaleDateString() : '';
        div.innerHTML = `<div>${escapeHtml(title)}</div><div class="session-date">${date}</div>`;
        div.addEventListener('click', () => loadSessionChat(s.session_id));
        sessionsList.appendChild(div);
    });
}

async function loadSessionChat(sid) {
    try {
        const r = await fetch(`${API}/sessions/${sid}`, { headers: authHeaders() });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) {
            currentSessionId = null;
            localStorage.removeItem('last-session-id');
            currentVersions = [];
            activeVersion = null;
            hasContent = false;
            chatMessages.innerHTML = '';
            chatMessages.appendChild(createWelcome());
            topbarTitle.textContent = 'New Session';
            updatePlaceholder();
            return;
        }
        const s = await r.json();
        currentSessionId = sid;
        localStorage.setItem('last-session-id', sid);
        activeVersion = null;
        currentVersions = [];
        chatMessages.innerHTML = '';
        s.messages.forEach(m => appendMessage(m.role, m.content));
        topbarTitle.textContent = s.messages.length ? s.messages[0].content.slice(0, 40) + '…' : 'Session';
        hasContent = s.has_draft || false;
        const isPublished = s.is_published || false;
        const permalink = s.permalink || null;
        const draftTitle = s.messages ? ([...s.messages].reverse().find(m => m.role === 'assistant')?.content || '') : '';
        const titleMatch = draftTitle.match(/^#\s+(.+)$/m);
        const blogTitle = titleMatch ? titleMatch[1].trim() : '';
        updatePlaceholder();

        try {
            const sr = await fetch(`${API}/chat/steps/${sid}`, { headers: authHeaders() });
            if (sr.ok) hydrateSteps(await sr.json());
        } catch {}
        try {
            const vr = await fetch(`${API}/chat/versions/${sid}`, { headers: authHeaders() });
            if (vr.ok) currentVersions = await vr.json();
            else currentVersions = [];
        } catch { currentVersions = []; }
        if (isPublished) {
            addPublishedCard(permalink);
            if (currentVersions.length > 1) addVersionBar();
        } else if (hasContent) {
            addPublishCard(blogTitle);
            if (currentVersions.length > 1) addVersionBar();
        }
        loadSessions();
        if (isMobile()) closeSidebar();
    } catch {
        currentSessionId = null;
        localStorage.removeItem('last-session-id');
    }
}

// ---- Messages ----
function createWelcome() {
    const d = document.createElement('div');
    d.className = 'welcome'; d.id = 'welcome';
    d.innerHTML = `
        <div class="welcome-panel">
            <p class="welcome-eyebrow">Editorial control room</p>
            <h2>Prompt it. Research it. Publish it.</h2>
            <p>BlogForge turns a rough topic into a sourced, SEO-aware draft with a human finish.</p>
            <div class="welcome-stats">
                <div class="welcome-stat">
                    <span>01</span>
                    <strong>Research</strong>
                    <small>Find the angle</small>
                </div>
                <div class="welcome-stat">
                    <span>02</span>
                    <strong>Draft</strong>
                    <small>Shape the argument</small>
                </div>
                <div class="welcome-stat">
                    <span>03</span>
                    <strong>Finish</strong>
                    <small>Humanize and publish</small>
                </div>
            </div>
        </div>
        <div class="welcome-rail">
            <div class="welcome-rail-label">Starter prompts</div>
            <div class="quick-prompts">
                <button class="quick-btn" data-prompt="Write a blog about the future of AI in healthcare">AI in Healthcare</button>
                <button class="quick-btn" data-prompt="Write a comprehensive guide to building with LangGraph">LangGraph Guide</button>
                <button class="quick-btn" data-prompt="Write a blog comparing FastAPI vs Django in 2026">FastAPI vs Django</button>
            </div>
        </div>`;
    return d;
}

function removeWelcome() {
    const w = document.getElementById('welcome');
    if (w) w.remove();
}

function appendMessage(role, content) {
    removeWelcome();
    const wrapper = document.createElement('div');
    wrapper.className = `msg msg-${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.dataset.role = role;
    bubble.innerHTML = role === 'assistant' ? renderMarkdown(content) : '';
    if (role !== 'assistant') bubble.textContent = content;
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

// ---- Tool badges / step trail ----
let badgeCounter = 0;
let currentStepEl = null;
let thinkingText = '';

function addToolBadge(toolName, label, icon) {
    removeWelcome();
    thinkingText = '';
    const key = `${toolName}-${badgeCounter++}`;
    const el = document.createElement('div');
    el.className = 'step-item';
    el.setAttribute('data-badge-key', key);
    el.innerHTML = `
        <div class="step-row">
            <div class="step-left">
                <span class="dot dot-run"></span>
                <span class="connector"></span>
            </div>
            <div class="step-content">
                <div class="step-header">
                    <div class="step-label">${escapeHtml(label)}</div>
                    <span class="badge b-run">Running</span>
                </div>
                <div class="stream-body" style="display:none">
                    <div class="stream-text" data-step-progress></div>
                    <button class="et" type="button" data-step-toggle>
                        <span class="ch">›</span> Details
                    </button>
                    <div class="stream-text" data-step-detail style="display:none"></div>
                </div>
            </div>
        </div>`;

    const toggleBtn = el.querySelector('[data-step-toggle]');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const detail = el.querySelector('[data-step-detail]');
            const ch = toggleBtn.querySelector('.ch');
            const open = detail && detail.style.display !== 'none';
            if (detail) detail.style.display = open ? 'none' : 'block';
            if (ch) ch.classList.toggle('o', !open);
        });
    }
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    currentStepEl = el;
    return key;
}

function appendThinking(text) {
    if (!currentStepEl) return;
    // Intentionally ignored for this design; we show progress/output instead.
}

function setStepProgress(text) {
    const el = currentStepEl || document.querySelector('.step-item:last-child');
    if (!el) return;
    const wrap = el.querySelector('.stream-body');
    if (wrap) wrap.style.display = 'block';
    const progEl = el.querySelector('[data-step-progress]');
    if (progEl) progEl.textContent = (text || '').trim() || 'Working…';
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function completeToolBadge(key, label, icon, status) {
    const el = document.querySelector(`[data-badge-key="${key}"]`);
    if (el) {
        const dot = el.querySelector('.dot');
        const st = status || 'done';
        if (dot) {
            dot.classList.remove('dot-run', 'dot-done', 'dot-err');
            dot.classList.add(st === 'error' ? 'dot-err' : 'dot-done');
        }
        const badge = el.querySelector('.badge');
        if (badge) {
            badge.classList.remove('b-run', 'b-done', 'b-err');
            if (st === 'error') {
                badge.classList.add('b-err');
                badge.textContent = 'Error';
            } else {
                badge.classList.add('b-done');
                badge.textContent = 'Done';
            }
        }
    }
    if (currentStepEl && currentStepEl.getAttribute('data-badge-key') === key) {
        currentStepEl = null;
        thinkingText = '';
    }
}

function setToolDetail(toolName, content) {
    const el = [...document.querySelectorAll('.step-item')]
        .reverse()
        .find(x => (x.getAttribute('data-badge-key') || '').startsWith(toolName + '-'));
    if (!el) return;
    const wrap = el.querySelector('.stream-body');
    if (wrap) wrap.style.display = 'block';
    const detailEl = el.querySelector('[data-step-detail]');
    if (!detailEl) return;
    detailEl.innerHTML = renderMarkdown(content || '');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hydrateSteps(steps) {
    if (!Array.isArray(steps) || steps.length === 0) return;
    // Remove any existing step cards before hydrating.
    document.querySelectorAll('.step-item').forEach(el => el.remove());
    steps.forEach(s => {
        const key = addToolBadge(s.tool, s.label || s.tool, s.icon || '⚙️');
        const el = document.querySelector(`[data-badge-key="${key}"]`);
        if (el) {
            if (s.status === 'done') {
                completeToolBadge(key, '', '', 'done');
            } else if (s.status === 'error') {
                completeToolBadge(key, '', '', 'error');
            }
            if (s.progress) setStepProgress(s.progress);
            if (s.output) setToolDetail(s.tool, s.output);
        }
    });
}

// ---- Pipeline ----
const TOOL_LABELS = {
    web_search: 'Searching web', research_topic: 'Researching topic',
    analyze_seo: 'Analyzing SEO', write_blog: 'Writing blog',
    humanize: 'Humanizing content', revise: 'Revising content',
    request_publish_approval: 'Preparing preview', publish_to_wordpress: 'Publishing',
    convert_to_vlog: 'Creating video script',
};
const TOOL_ICONS = {
    web_search: '🔍', research_topic: '🔬', analyze_seo: '⭐',
    write_blog: '✍️', humanize: '✨', revise: '✏️',
    request_publish_approval: '📋', publish_to_wordpress: '📤', convert_to_vlog: '🎬',
};

function resetPipeline() {
    if (statusLine) { statusLine.textContent = ''; statusLine.classList.remove('visible'); }
    if (streamMeter) streamMeter.classList.remove('active');
}

function finishPipeline() {
    if (statusLine) { statusLine.textContent = ''; statusLine.classList.remove('visible'); }
}

// ---- Publish card ----
function addPublishCard(blogTitle) {
    document.querySelectorAll('.msg-action').forEach(el => el.remove());
    const w = document.createElement('div');
    w.className = 'msg msg-action';
    const titleDisplay = blogTitle ? escapeHtml(blogTitle) : 'your blog post';
    w.innerHTML = `
        <div class="publish-card">
            <div class="publish-card-text">
                <strong>Ready to publish "${titleDisplay}"?</strong>
                <p>Publish as draft to WordPress, export as DOCX, or type changes below.</p>
            </div>
            <div class="publish-card-actions">
                <button class="btn-publish" id="publish-btn" onclick="handlePublish()">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/>
                        <polyline points="16,6 12,2 8,6"/><line x1="12" y1="2" x2="12" y2="15"/>
                    </svg>
                    Publish
                </button>
                <button class="btn-export" id="export-btn" onclick="handleExport()">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7,10 12,15 17,10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Export DOCX
                </button>
            </div>
        </div>`;
    chatMessages.appendChild(w);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addPublishedCard(permalink) {
    document.querySelectorAll('.msg-action').forEach(el => el.remove());
    const w = document.createElement('div');
    w.className = 'msg msg-action';
    const linkHtml = permalink ? `<a href="${escapeHtml(permalink)}" target="_blank" rel="noopener" class="published-link">${escapeHtml(permalink)}</a>` : '';
    w.innerHTML = `
        <div class="publish-card published">
            <div class="publish-card-text">
                <strong>✅ Published to WordPress</strong>
                <p>This post is live as a draft on your site.${linkHtml ? ' ' + linkHtml : ''}</p>
            </div>
            <div class="publish-card-actions">
                <button class="btn-export" id="export-btn" onclick="handleExport()">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7,10 12,15 17,10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Export DOCX
                </button>
            </div>
        </div>`;
    chatMessages.appendChild(w);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function handlePublish() {
    const btn = document.getElementById('publish-btn');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Publishing…';
    try {
        const r = await fetch(`${API}/chat/publish`, {
            method: 'POST', headers: authHeaders(),
            body: JSON.stringify({ message: '', session_id: currentSessionId }),
        });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || 'Publish failed');
        const d = await r.json();
        if (d.success) {
            addPublishedCard(d.permalink);
            appendMessage('assistant', `### ✅ Published to WordPress as draft${d.permalink ? '\n**Link:** ' + d.permalink : ''}\nPost ID: ${d.post_id}`);
        } else throw new Error(d.error || 'Unknown error');
    } catch (err) {
        btn.disabled = false; btn.innerHTML = 'Retry Publish';
        appendMessage('assistant', `**❌ Publish failed:** ${err.message}`);
    }
}
window.handlePublish = handlePublish;

async function handleExport() {
    const btn = document.getElementById('export-btn');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Exporting…';
    try {
        const r = await fetch(`${API}/chat/export-docx?session_id=${encodeURIComponent(currentSessionId)}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || 'Export failed');
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        let filename = 'blog.docx';
        const match = cd.match(/filename="?(.+?)"?$/);
        if (match) filename = match[1];
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        document.body.appendChild(a); a.click();
        document.body.removeChild(a); URL.revokeObjectURL(url);
        btn.innerHTML = '✅ Downloaded!';
        setTimeout(() => { btn.disabled = false; btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Export DOCX'; }, 2000);
    } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Retry';
        appendMessage('assistant', `**❌ Export failed:** ${err.message}`);
    }
}
window.handleExport = handleExport;

// ---- Version bar ----
function addVersionBar() {
    document.querySelectorAll('.version-bar').forEach(el => el.remove());
    if (currentVersions.length <= 1) return;
    const bar = document.createElement('div');
    bar.className = 'version-bar';
    bar.id = 'version-bar';
    const total = currentVersions.length;
    let html = `<div class="version-bar-label">${total} versions</div><div class="version-bar-items">`;
    currentVersions.forEach(v => {
        const label = v.is_current ? `v${v.version} (current)` : `v${v.version}`;
        const cls = v.is_current ? 'version-item active' : 'version-item';
        const title = v.title ? escapeHtml(v.title.slice(0, 40)) : 'Untitled';
        const wc = v.word_count ? `${v.word_count}w` : '';
        html += `<button class="${cls}" data-version="${v.version}" data-current="${v.is_current}" onclick="switchVersion(${v.version})" title="${title}">
            <span class="version-num">${label}</span>
            ${wc ? `<span class="version-wc">${wc}</span>` : ''}
        </button>`;
    });
    html += '</div>';
    bar.innerHTML = html;
    // Insert before the publish card
    const publishCard = document.querySelector('.msg-action');
    if (publishCard) chatMessages.insertBefore(bar, publishCard);
    else chatMessages.appendChild(bar);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function viewVersion(ver) {
    if (!currentSessionId) return;
    const v = currentVersions.find(x => x.version === ver);
    if (!v) return;

    if (v.is_current) {
        activeVersion = null;
        await loadSessionChat(currentSessionId);
        return;
    }

    activeVersion = ver;
    document.querySelectorAll('.version-item').forEach(el => el.classList.remove('active'));
    const btn = document.querySelector(`.version-item[data-version="${ver}"]`);
    if (btn) btn.classList.add('active');

    // Need version content from API
    try {
        const r = await fetch(`${API}/chat/version-content/${currentSessionId}?version=${ver}`, { headers: authHeaders() });
        if (!r.ok) return;
        const data = await r.json();
        // Reload the session messages
        const sr = await fetch(`${API}/sessions/${currentSessionId}`, { headers: authHeaders() });
        if (!sr.ok) return;
        const s = await sr.json();
        chatMessages.innerHTML = '';
        s.messages.forEach(m => appendMessage(m.role, m.content));
        // Show the version content
        const bb = appendMessage('assistant', data.content);
        const wc = document.createElement('div');
        wc.className = 'word-count-tag'; wc.textContent = `${data.word_count} words`;
        bb.appendChild(wc);
        addVersionBar();
        addRestoreCard(ver, data.title);
    } catch {}
}
window.switchVersion = viewVersion;

function addRestoreCard(ver, title) {
    document.querySelectorAll('.msg-action').forEach(el => el.remove());
    const w = document.createElement('div');
    w.className = 'msg msg-action';
    const titleDisplay = title ? escapeHtml(title) : 'this version';
    w.innerHTML = `
        <div class="publish-card">
            <div class="publish-card-text">
                <strong>Viewing v${ver} — "${titleDisplay}"</strong>
                <p>Restore this version as the current draft, or export it.</p>
            </div>
            <div class="publish-card-actions">
                <button class="btn-publish" onclick="handleRestore(${ver})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="1,4 1,10 7,10"/><path d="M3.51 15a9 9 0 105.64-12.36L1 10"/>
                    </svg>
                    Restore v${ver}
                </button>
                <button class="btn-export" onclick="handleExportVersion(${ver})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7,10 12,15 17,10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Export
                </button>
            </div>
        </div>`;
    chatMessages.appendChild(w);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function handleRestore(ver) {
    if (!currentSessionId) return;
    try {
        const r = await fetch(`${API}/chat/restore-version`, {
            method: 'POST', headers: authHeaders(),
            body: JSON.stringify({ message: String(ver), session_id: currentSessionId }),
        });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || 'Restore failed');
        const d = await r.json();
        appendMessage('assistant', `### ✅ Restored v${ver} as v${d.version}\n**${d.title}** is now the current draft.`);
        hasContent = true;
        activeVersion = null;
        // Reload
        await loadSessionChat(currentSessionId);
    } catch (err) {
        appendMessage('assistant', `**❌ Restore failed:** ${err.message}`);
    }
}
window.handleRestore = handleRestore;

async function handleExportVersion(ver) {
    if (!currentSessionId) return;
    try {
        const r = await fetch(`${API}/chat/export-docx?session_id=${encodeURIComponent(currentSessionId)}&version=${ver}`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) throw new Error('Export failed');
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        let filename = `blog-v${ver}.docx`;
        const match = cd.match(/filename="?(.+?)"?$/);
        if (match) filename = match[1];
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = filename;
        document.body.appendChild(a); a.click();
        document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err) {
        appendMessage('assistant', `**❌ Export failed:** ${err.message}`);
    }
}
window.handleExportVersion = handleExportVersion;

// ---- File attach ----
let attachedFiles = [];

attachBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'docx'].includes(ext)) {
        alert('Only .pdf and .docx files are supported');
        fileInput.value = ''; return;
    }
    attachBtn.disabled = true;
    attachBtn.innerHTML = '<span class="spinner"></span>';
    try {
        const formData = new FormData();
        formData.append('file', file);
        const r = await fetch(`${API}/chat/upload`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData,
        });
        if (r.status === 401) { handleAuthFail(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || 'Upload failed');
        const data = await r.json();
        attachedFiles.push({ name: data.filename, text: data.text });
        renderFileChips();
    } catch (err) { alert(err.message); }
    finally {
        attachBtn.disabled = false;
        attachBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
        fileInput.value = '';
    }
});

function renderFileChips() {
    fileChips.innerHTML = '';
    attachedFiles.forEach((f, i) => {
        const chip = document.createElement('span');
        chip.className = 'file-chip';
        chip.innerHTML = `${escapeHtml(f.name)} <button class="file-chip-remove" onclick="removeFile(${i})">✕</button>`;
        fileChips.appendChild(chip);
    });
}
window.removeFile = function(i) { attachedFiles.splice(i, 1); renderFileChips(); };

function addToolOutputCard(toolName, content) {
    removeWelcome();
    const card = document.createElement('div');
    card.className = 'agent-card';
    const label = TOOL_LABELS[toolName] || toolName;
    const icon = TOOL_ICONS[toolName] || '⚙️';
    card.innerHTML = `
        <div class="agent-card-header">
            <span class="agent-card-icon">${icon}</span>
            <span class="agent-card-title">${escapeHtml(label)}</span>
            <span class="agent-card-badge">Output</span>
            <span class="agent-card-chevron">⌄</span>
        </div>
        <div class="agent-card-body">
            <div class="agent-card-content">${renderMarkdown(content)}</div>
        </div>`;
    card.querySelector('.agent-card-header').addEventListener('click', () => {
        card.classList.toggle('open');
    });
    chatMessages.appendChild(card);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Tool output is now shown inside each step item.

// ---- Chat submit ----
chatForm.addEventListener('submit', async e => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message || isStreaming) return;

    appendMessage('user', message);
    chatInput.value = ''; chatInput.style.height = 'auto';
    composer.classList.remove('expanded');
    sendBtn.classList.remove('visible');

    let fullMessage = message;
    if (attachedFiles.length > 0) {
        const fileContext = attachedFiles.map(f => `[Attached file: ${f.name}]\n\n${f.text}`).join('\n\n---\n\n');
        fullMessage = fileContext + '\n\n' + message;
        attachedFiles = []; renderFileChips();
    }

    sendBtn.disabled = true; isStreaming = true; resetPipeline();
    badgeCounter = 0;
    const pendingBadges = {};

    if (statusLine) { statusLine.textContent = '🤔 Thinking…'; statusLine.classList.add('visible'); }
    if (streamMeter) streamMeter.classList.add('active');

    try {
        const res = await fetch(`${API}/chat/stream`, {
            method: 'POST', headers: authHeaders(),
            body: JSON.stringify({ message: fullMessage, session_id: currentSessionId || null, word_count: 1500 }),
        });
        if (res.status === 401) { handleAuthFail(); return; }
        if (!res.ok) { let d = 'Request failed'; try { d = (await res.json()).detail || d; } catch {} throw new Error(d); }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', agentBubble = null, agentText = '';
        let canPublish = false, needsApproval = false, blogTitle = '';
        let lastEventType = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('event:')) { lastEventType = line.slice(6).trim(); continue; }
                if (!line.startsWith('data:')) continue;
                const payload = line.slice(6).trim();
                if (!payload) continue;
                let p; try { p = JSON.parse(payload); } catch { continue; }

                if (lastEventType === 'token') {
                    // If a step trail item is active, capture short thinking text
                    const text = p.token || '';
                    if (currentStepEl && text && !text.startsWith('#') && thinkingText.length < 200) {
                        appendThinking(text);
                    }
                    if (!agentBubble) agentBubble = appendMessage('assistant', '');
                    agentText += text;
                    agentBubble.innerHTML = renderMarkdown(agentText);
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                } else if (lastEventType === 'blog_content') {
                    blogTitle = p.title;
                    const bb = appendMessage('assistant', p.content);
                    const wc = document.createElement('div');
                    wc.className = 'word-count-tag'; wc.textContent = `${p.word_count} words`;
                    bb.appendChild(wc);
                } else if (lastEventType === 'tool_start') {
                    const key = addToolBadge(p.tool, p.label, p.icon);
                    pendingBadges[key] = { tool: p.tool, label: p.label, icon: p.icon };
                } else if (lastEventType === 'tool_output') {
                    setToolDetail(p.tool, p.content || '');
                } else if (lastEventType === 'tool_end') {
                    for (const [key, info] of Object.entries(pendingBadges)) {
                        if (info.tool === p.tool) {
                            completeToolBadge(key, info.label, info.icon, p.status);
                            delete pendingBadges[key]; break;
                        }
                    }
                } else if (lastEventType === 'step_progress') {
                    setStepProgress(p.text || '');
                } else if (lastEventType === 'done') {
                    if (p.session_id) currentSessionId = p.session_id;
                    if (p.session_id) localStorage.setItem('last-session-id', p.session_id);
                    if (p.can_publish) canPublish = p.can_publish;
                    if (p.needs_approval) needsApproval = p.needs_approval;
                    if (p.blog_title) blogTitle = p.blog_title;
                    if (p.versions && p.versions.length) currentVersions = p.versions;
                }
            }
        }

        // Complete any stragglers
        for (const [key, info] of Object.entries(pendingBadges)) {
            completeToolBadge(key, info.label, info.icon);
        }

        finishPipeline();
        if (canPublish) {
            hasContent = true;
            addPublishCard(needsApproval ? blogTitle : (blogTitle || ''));
            if (currentVersions.length > 1) addVersionBar();
        }
        updatePlaceholder();
    } catch (err) {
        appendMessage('assistant', `**Error:** ${err.message}`);
        resetPipeline();
    } finally {
        sendBtn.disabled = false; isStreaming = false;
        if (streamMeter) streamMeter.classList.remove('active');
        loadSessions();
    }
});

// ---- Init ----
loadSessions().finally(() => {
    if (currentSessionId) loadSessionChat(currentSessionId);
});
updatePlaceholder();
