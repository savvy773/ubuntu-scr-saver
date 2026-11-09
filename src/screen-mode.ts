export {};

const overrideKey = 'screensaver-night-override';
let restoredNight: string | null = null;
try { restoredNight = sessionStorage.getItem(overrideKey); } catch { /* In-memory fallback. */ }
let black = false;
let ready = false;
const wakeKeys = new Set<string>();
setTimeout(() => { ready = true; }, 800);

// A night belongs to its starting date, including the hours after midnight.
function nightId(now: Date): string | null {
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes >= 360 && minutes < 1090) return null;
  const start = new Date(now);
  if (minutes < 360) start.setDate(start.getDate() - 1);
  return `${start.getFullYear()}-${start.getMonth() + 1}-${start.getDate()}`;
}

function updateScreenMode(): string | null {
  const night = nightId(new Date());
  if (restoredNight !== null && restoredNight !== night) {
    restoredNight = null;
    try { sessionStorage.removeItem(overrideKey); } catch { /* In-memory fallback. */ }
  }
  black = night !== null && restoredNight !== night;
  document.documentElement.classList.toggle('night-black', black);
  return night;
}

updateScreenMode();
setInterval(updateScreenMode, 1000);
window.addEventListener('focus', updateScreenMode);
document.addEventListener('visibilitychange', updateScreenMode);

function consume(event: KeyboardEvent) {
  event.preventDefault();
  event.stopImmediatePropagation();
}

window.addEventListener('keydown', (event: KeyboardEvent) => {
  const night = updateScreenMode();
  // Holding the wake key must never count as the second press.
  if (event.repeat || wakeKeys.has(event.code)) {
    if (black || wakeKeys.has(event.code)) consume(event);
    return;
  }
  if (black) {
    consume(event);
    wakeKeys.add(event.code);
    restoredNight = night;
    try { sessionStorage.setItem(overrideKey, night!); } catch { /* In-memory fallback. */ }
    updateScreenMode();
    return;
  }
  if (!ready || document.querySelector('dialog[open]')) return;
  window.close();
}, { capture: true });

window.addEventListener('keyup', (event: KeyboardEvent) => {
  // Prevent Space/Enter release from activating a previously focused control.
  if (wakeKeys.delete(event.code)) consume(event);
}, { capture: true });
window.addEventListener('blur', () => wakeKeys.clear());
