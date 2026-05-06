/**
 * BlogForge — Login / Register page logic
 */

// Theme toggle
(function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
})();
const themeToggle = document.getElementById('theme-toggle');
if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
    });
}

const API = '/api';

// DOM
const loginForm  = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const loginError  = document.getElementById('login-error');
const registerError = document.getElementById('register-error');
const tabs = document.querySelectorAll('.login-tabs .tab');

// ---- Tabs ----
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        loginForm.classList.toggle('active', target === 'login');
        registerForm.classList.toggle('active', target === 'register');
        loginError.textContent = '';
        registerError.textContent = '';
    });
});

// ---- Login ----
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.textContent = '';

    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    // FastAPI OAuth2PasswordRequestForm expects form-encoded body
    const body = new URLSearchParams();
    body.append('username', email);
    body.append('password', password);

    try {
        const res = await fetch(`${API}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body,
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Login failed');
        }

        const { access_token } = await res.json();
        localStorage.setItem('token', access_token);
        window.location.href = '/app';
    } catch (err) {
        loginError.textContent = err.message;
    }
});

// ---- Register ----
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    registerError.textContent = '';

    const username = document.getElementById('reg-username').value;
    const email    = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;

    try {
        // 1. Create account
        const res = await fetch(`${API}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password }),
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Registration failed');
        }

        // 2. Auto-login
        const body = new URLSearchParams();
        body.append('username', email);
        body.append('password', password);

        const loginRes = await fetch(`${API}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body,
        });

        if (!loginRes.ok) throw new Error('Account created but auto-login failed');

        const { access_token } = await loginRes.json();
        localStorage.setItem('token', access_token);
        window.location.href = '/app';
    } catch (err) {
        registerError.textContent = err.message;
    }
});

// ---- Redirect if already logged in ----
if (localStorage.getItem('token')) {
    window.location.href = '/app';
}
