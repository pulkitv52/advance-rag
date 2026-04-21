/// <reference types="vite/client" />
/**
 * Remote Logger: Captures browser console errors and warnings and forwards them 
 * to the backend API to be saved in logs/frontend/app.log.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8081';

type LogLevel = 'error' | 'warn' | 'info';

async function sendLog(level: LogLevel, message: any, stack?: string) {
    try {
        const msgStr = typeof message === 'object' ? JSON.stringify(message) : String(message);
        
        await fetch(`${API_BASE_URL}/logs/frontend`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                level,
                message: msgStr,
                url: window.location.href,
                stack: stack || null,
            }),
        });
    } catch (e) {
        // Fallback: if logging itself fails, just show in local console to avoid infinite loops
        originalConsole.error('Remote logging failed:', e);
    }
}

const originalConsole = {
    error: console.error,
    warn: console.warn,
};

export function initRemoteLogger() {
    // Intercept console.error
    console.error = (...args: any[]) => {
        originalConsole.error(...args);
        const stack = new Error().stack;
        sendLog('error', args.join(' '), stack);
    };

    // Intercept console.warn
    console.warn = (...args: any[]) => {
        originalConsole.warn(...args);
        sendLog('warn', args.join(' '));
    };

    // Intercept unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
        sendLog('error', `Unhandled Promise Rejection: ${event.reason}`, event.reason?.stack);
    });

    // Intercept global errors
    window.addEventListener('error', (event) => {
        sendLog('error', `Global Error: ${event.message}`, event.error?.stack);
    });

    console.info('[RemoteLogger] Initialized. Errors and warnings are being forwarded to the server.');
}
