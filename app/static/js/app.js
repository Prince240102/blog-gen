/**
 * BlogForge — Studio App
 *
 * Flow:
 *   1. User sends topic → Research → SEO → Blog streams in
 *   2. "Happy with this?" card appears with Publish button
 *   3. User types feedback → blog revises → back to step 2
 *   4. User clicks Publish → pushed to WordPress as draft
 */

const API = '/api';

let token = localStorage.getItem('token');
let currentSessionId = null;
let isStreaming = false;
let hasContent = false;

if (!token) window.location.href = '/';
function authHeaders() {
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// ---- DOM ----
const chatMessages    = document.getElementById('chat-messages');
const chatForm        = document.getElementById('chat-form');
const chatInput       = document.getElementById('chat-input');
const sendBtn         = document.getElementById('send-btn');
const pipeline        = document.getElementById('pipeline');
const topbarTitle     = document.getElementById('topbar-title');
const sessionsList    = document.getElementById('sessions-list');
const sidebar         = document.getElementById('sidebar');
const sidebarToggle   = document.getElementById('sidebar-toggle');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
const newChatBtn      = document.getElementById('new-chat-btn');
const logoutBtn       = document.getElementById('logout-btn');
const statusLine      = document.getElementById('status-line');

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
        ? 'Tell me what to change, or click Publish below…'
        : 'Describe your blog topic…';
}

// ---- Sidebar ----
function openSidebar() {
    sidebar.classList.remove('collapsed');
    if (isMobile()) sidebarBackdrop.classList.add('visible');
    if (!isMobile()) localStorage.setItem('sidebar-collapsed', 'false');
}
function closeSidebar() {
    sidebar.classList.add('collapsed');
    sidebarBackdrop.classList.remove('visible');
    if (!isMobile()) localStorage.setItem('sidebar-collapsed', 'true');
}
sidebarToggle.addEventListener('click', () =>
    sidebar.classList.contains('collapsed') ? openSidebar() : closeSidebar());
sidebarBackdrop.addEventListener('click', closeSidebar);

if (isMobile()) sidebar.classList.add('collapsed');
else if (localStorage.getItem('sidebar-collapsed') === 'true') sidebar.classList.add('collapsed');

let wasMobile = isMobile();
window.addEventListener('resize', () => {
    const now = isMobile();
    if (now && !wasMobile) closeSidebar();
    else if (!now && wasMobile) {
        sidebarBackdrop.classList.remove('visible');
        if (localStorage.getItem('sidebar-collapsed') !== 'true') sidebar.classList.remove('collapsed');
    }
    wasMobile = now;
});

// ---- Textarea ----
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
});

// ---- Logout / New ----
logoutBtn.addEventListener('click', () => { localStorage.removeItem('token'); window.location.href = '/'; });
newChatBtn.addEventListener('click', () => {
    currentSessionId = null; hasContent = false;
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
        if (r.status === 401) { window.location.href = '/'; return; }
        renderSessions(await r.json());
    } catch {}
}

function renderSessions(sessions) {
    sessionsList.innerHTML = '';
    sessions.reverse().forEach(s => {
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
        if (!r.ok) return;
        const s = await r.json();
        currentSessionId = sid;
        chatMessages.innerHTML = '';
        s.messages.forEach(m => appendMessage(m.role, m.content));
        topbarTitle.textContent = s.messages.length ? s.messages[0].content.slice(0, 40) + '…' : 'Session';
        const lastA = [...s.messages].reverse().find(m => m.role === 'assistant');
        hasContent = lastA && lastA.content.length > 200;
        updatePlaceholder();
        if (hasContent) addPublishCard();
        loadSessions();
        if (isMobile()) closeSidebar();
    } catch {}
}

// ---- Messages ----
function createWelcome() {
    const d = document.createElement('div');
    d.className = 'welcome'; d.id = 'welcome';
    d.innerHTML = `
        <h2>What shall we write today?</h2>
        <p>Describe your blog topic. The AI will research, optimize for SEO, and write a publish-ready post.</p>
        <div class="quick-prompts">
            <button class="quick-btn" data-prompt="Write a blog about the future of AI in healthcare">AI in Healthcare</button>
            <button class="quick-btn" data-prompt="Write a comprehensive guide to building with LangGraph">LangGraph Guide</button>
            <button class="quick-btn" data-prompt="Write a blog comparing FastAPI vs Django in 2026">FastAPI vs Django</button>
        </div>`;
    return d;
}

function appendMessage(role, content) {
    const w = document.getElementById('welcome'); if (w) w.remove();
    const wrapper = document.createElement('div');
    wrapper.className = `msg msg-${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = role === 'assistant' ? renderMarkdown(content) : '';
    if (role !== 'assistant') bubble.textContent = content;
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

// ---- Agent cards (collapsible) ----
function addAgentCard(step, title, output) {
    const w = document.getElementById('welcome'); if (w) w.remove();
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.setAttribute('data-step', step);
    const icon = { research: '🔍', seo: '⭐', content: '✍️' }[step] || '⚙️';
    card.innerHTML = `
        <div class="agent-card-header" onclick="this.parentElement.classList.toggle('open')">
            <span class="agent-card-icon">${icon}</span>
            <span class="agent-card-title">${escapeHtml(title)}</span>
            <span class="agent-card-badge">done</span>
            <svg class="agent-card-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>
        </div>
        <div class="agent-card-body">
            <div class="agent-card-content">${renderMarkdown(output)}</div>
        </div>`;
    chatMessages.appendChild(card);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ---- Pipeline ----
const STEPS = ['research', 'seo', 'content'];
const LABELS = { research: '🔍 Researching…', seo: '⭐ SEO Analysis…', content: '✍️ Writing blog…' };

function resetPipeline() {
    pipeline.classList.remove('active');
    STEPS.forEach(n => { const e = pipeline.querySelector(`[data-step="${n}"]`); if (e) e.classList.remove('running', 'done'); });
    if (statusLine) { statusLine.textContent = ''; statusLine.classList.remove('visible'); }
}

function setPipelineRunning(step) {
    pipeline.classList.add('active');
    STEPS.forEach(n => {
        const e = pipeline.querySelector(`[data-step="${n}"]`);
        if (!e) return;
        e.classList.remove('running', 'done');
        if (n === step) e.classList.add('running');
        else if (STEPS.indexOf(n) < STEPS.indexOf(step)) e.classList.add('done');
    });
    if (statusLine) { statusLine.textContent = LABELS[step] || ''; statusLine.classList.add('visible'); }
}

function setPipelineDone(step) {
    const e = pipeline.querySelector(`[data-step="${step}"]`);
    if (e) { e.classList.remove('running'); e.classList.add('done'); }
}

function finishPipeline() {
    STEPS.forEach(n => { const e = pipeline.querySelector(`[data-step="${n}"]`); if (e) { e.classList.remove('running'); e.classList.add('done'); } });
    if (statusLine) { statusLine.textContent = ''; statusLine.classList.remove('visible'); }
}

// ---- Publish ----
function addPublishCard() {
    document.querySelectorAll('.msg-action').forEach(el => el.remove());
    const w = document.createElement('div');
    w.className = 'msg msg-action';
    w.innerHTML = `
        <div class="publish-card">
            <div class="publish-card-text">
                <strong>Happy with this blog?</strong>
                <p>Want changes? Just type below. Otherwise publish as a draft to WordPress.</p>
            </div>
            <button class="btn-publish" id="publish-btn" onclick="handlePublish()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/>
                    <polyline points="16,6 12,2 8,6"/><line x1="12" y1="2" x2="12" y2="15"/>
                </svg>
                Publish to WordPress
            </button>
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
        if (!r.ok) throw new Error((await r.json()).detail || 'Publish failed');
        const d = await r.json();
        if (d.success) {
            btn.innerHTML = '✅ Published!'; btn.classList.add('published');
            appendMessage('assistant', `### ✅ Published to WordPress as draft${d.permalink ? '\n**Link:** ' + d.permalink : ''}\nPost ID: ${d.post_id}`);
        } else throw new Error(d.error || 'Unknown error');
    } catch (err) {
        btn.disabled = false; btn.innerHTML = 'Retry Publish';
        appendMessage('assistant', `**❌ Publish failed:** ${err.message}`);
    }
}
window.handlePublish = handlePublish;

// ---- Chat submit ----
chatForm.addEventListener('submit', async e => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message || isStreaming) return;

    appendMessage('user', message);
    chatInput.value = ''; chatInput.style.height = 'auto';
    sendBtn.disabled = true; isStreaming = true; resetPipeline();

    if (statusLine) {
        statusLine.textContent = hasContent ? '✍️ Revising blog…' : '🔍 Starting research…';
        statusLine.classList.add('visible');
    }

    try {
        const res = await fetch(`${API}/chat/stream`, {
            method: 'POST', headers: authHeaders(),
            body: JSON.stringify({ message, session_id: currentSessionId || null, word_count: 1500 }),
        });

        if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/'; return; }
        if (!res.ok) { let d = 'Request failed'; try { d = (await res.json()).detail || d; } catch {} throw new Error(d); }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', blogBubble = null, blogText = '', canPublish = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                const payload = line.slice(6).trim();
                if (!payload) continue;

                let p; try { p = JSON.parse(payload); } catch { continue; }

                // Pipeline running
                if (p.step && p.status === 'running') { setPipelineRunning(p.step); continue; }

                // Agent output (not content — that streams below)
                if (p.step && p.output !== undefined && !p.token && p.step !== 'content') {
                    setPipelineDone(p.step);
                    addAgentCard(p.step, p.title || p.step, p.output);
                    continue;
                }

                // Blog start
                if (p.title !== undefined && p.word_count !== undefined) {
                    setPipelineDone('content');
                    blogBubble = appendMessage('assistant', '');
                    blogText = '';
                    continue;
                }

                // Blog token
                if (p.token && blogBubble) {
                    blogText += p.token;
                    blogBubble.innerHTML = renderMarkdown(blogText);
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                    continue;
                }

                // Error
                if (p.error) { appendMessage('assistant', `**Error:** ${p.error}`); continue; }

                // Done
                if (p.session_id) {
                    currentSessionId = p.session_id;
                    canPublish = p.can_publish;
                    if (canPublish) hasContent = true;
                    continue;
                }
            }
        }

        finishPipeline();
        if (canPublish) addPublishCard();
        updatePlaceholder();

    } catch (err) {
        appendMessage('assistant', `**Error:** ${err.message}`);
        resetPipeline();
    } finally {
        sendBtn.disabled = false; isStreaming = false;
        loadSessions();
    }
});

// ---- Init ----
loadSessions();
updatePlaceholder();
